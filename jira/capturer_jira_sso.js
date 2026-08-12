const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const readline = require('readline');

const ROOT = __dirname;
const CONFIG_FILE = path.join(ROOT, 'jira_config.json');
const LEGACY_URLS_FILE = path.join(ROOT, 'jira_urls.txt');
const OUT = path.join(ROOT, 'jira_brut.json');
const DIAGNOSTIC_OUT = path.join(ROOT, 'jira_diagnostic.json');
const PROFILE = path.join(ROOT, '.jira_sso_profile');
const PORT = 9231;
const PAGE_SIZE = 100;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function cleanBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function jqlFromValue(value, name) {
  if (typeof value === 'string') return value.trim();
  if (!value || value.active === false || value.enabled === false) return '';
  if (value.jql || value.query) return String(value.jql || value.query).trim();
  if (value.filter_id || value.filterId) return `filter = ${value.filter_id || value.filterId}`;
  if (value.url) {
    const parsed = new URL(value.url);
    const jql = parsed.searchParams.get('jql');
    if (jql) return jql.trim();
    const filterId = parsed.searchParams.get('filter');
    if (filterId) return `filter = ${filterId}`;
  }
  throw new Error(`La requête "${name}" ne contient ni jql, ni filter_id, ni URL avec ?jql=`);
}

function readConfiguration() {
  if (fs.existsSync(CONFIG_FILE)) {
    const config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8').replace(/^\uFEFF/, ''));
    const baseUrl = cleanBaseUrl(config.jira_base_url);
    const rawQueries = config.queries || config.requetes || {};
    const queries = Array.isArray(rawQueries)
      ? rawQueries.map((item, index) => ({name: item.name || `requete_${index + 1}`, jql: jqlFromValue(item, item.name || `requete_${index + 1}`)}))
      : Object.entries(rawQueries).map(([name, value]) => ({name, jql: jqlFromValue(value, name)}));
    const activeQueries = queries.map(item => ({name: item.name, jql: String(item.jql || '').trim()})).filter(item => item.jql);
    if (!baseUrl) throw new Error('jira_base_url est absent de jira_config.json');
    if (!activeQueries.length) throw new Error('Aucune requête JQL active dans jira_config.json');
    return {baseUrl, queries: activeQueries};
  }

  // Compatibilité avec l'ancienne version : une URL de recherche avec ?jql= par ligne.
  if (!fs.existsSync(LEGACY_URLS_FILE)) throw new Error('jira_config.json est introuvable');
  const urls = fs.readFileSync(LEGACY_URLS_FILE, 'utf8').split(/\r?\n/)
    .map(value => value.trim()).filter(value => value && !value.startsWith('#'));
  if (!urls.length) throw new Error('Créez jira_config.json ou ajoutez une URL active dans jira_urls.txt');
  const parsed = urls.map((value, index) => {
    const url = new URL(value);
    const jql = url.searchParams.get('jql');
    if (!jql) throw new Error(`Paramètre jql absent de l'URL ${index + 1}`);
    return {baseUrl: `${url.protocol}//${url.host}`, name: `requete_${index + 1}`, jql};
  });
  return {baseUrl: parsed[0].baseUrl, queries: parsed.map(({name, jql}) => ({name, jql}))};
}

function browserPath() {
  const candidates = [
    process.env.JIRA_CHROME,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
  ].filter(Boolean);
  const found = candidates.find(fs.existsSync);
  if (!found) throw new Error('Chrome/Edge introuvable. Définissez la variable JIRA_CHROME.');
  return found;
}

async function getJson(url, tries = 60) {
  for (let index = 0; index < tries; index++) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch (_) {}
    await sleep(500);
  }
  throw new Error('Le navigateur SSO ne répond pas sur le port de débogage.');
}

function ask(message) {
  const rl = readline.createInterface({input: process.stdin, output: process.stdout});
  return new Promise(resolve => rl.question(message, () => { rl.close(); resolve(); }));
}

class CDP {
  constructor(wsUrl) {
    if (typeof WebSocket === 'undefined') {
      throw new Error('WebSocket indisponible. Lancez Importer_JIRA.cmd (il active automatiquement cette fonction sous Node.js 20).');
    }
    this.id = 0;
    this.pending = new Map();
    this.ws = new WebSocket(wsUrl);
  }
  async open() {
    await new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = event => {
      const message = JSON.parse(event.data);
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result || {});
    };
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, {resolve, reject});
      this.ws.send(JSON.stringify({id, method, params}));
    });
  }
  close() { try { this.ws.close(); } catch (_) {} }
}

async function openTarget(url) {
  const response = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, {method: 'PUT'});
  if (!response.ok) throw new Error(`Impossible d'ouvrir Jira dans le navigateur (${response.status})`);
  const target = await response.json();
  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  await cdp.send('Page.navigate', {url});
  await sleep(2500);
  return cdp;
}

async function executeJql(cdp, baseUrl, jql) {
  // La requête est exécutée dans l'onglet Jira authentifié : les cookies SSO restent dans le navigateur.
  const expression = `
    (async () => {
      const jql = ${JSON.stringify(jql)};
      const apiUrl = ${JSON.stringify(`${baseUrl}/rest/api/2/search`)};
      const pageSize = ${PAGE_SIZE};
      let startAt = 0;
      let total = null;
      let issues = [];
      let names = {};
      while (total === null || startAt < total) {
        const payload = {jql, startAt, maxResults: pageSize, fields: ['*all'], expand: ['names']};
        let response = await fetch(apiUrl, {
          method: 'POST', credentials: 'include',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        if (response.status === 404 || response.status === 405) {
          const apiGet = apiUrl + '?jql=' + encodeURIComponent(jql)
            + '&startAt=' + startAt + '&maxResults=' + pageSize
            + '&expand=names&fields=*all';
          response = await fetch(apiGet, {credentials: 'include', headers: {'Accept': 'application/json'}});
        }
        if (!response.ok) throw new Error('API JIRA ' + response.status + ' : ' + (await response.text()).slice(0, 300));
        const page = await response.json();
        names = Object.assign(names, page.names || {});
        issues.push(...(page.issues || []));
        total = Number(page.total || 0);
        if (!(page.issues || []).length) break;
        startAt += page.issues.length;
      }
      return {jqlEnvoyee: jql, total, names, issues};
    })()
  `;
  const result = await cdp.send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) {
    const detail = result.exceptionDetails.exception?.description || result.exceptionDetails.text;
    throw new Error(detail || 'Erreur JavaScript dans la page Jira');
  }
  if (!result.result || !result.result.value) throw new Error('Jira n’a retourné aucune donnée exploitable');
  return result.result.value;
}

async function main() {
  const config = readConfiguration();
  const executable = browserPath();
  fs.mkdirSync(PROFILE, {recursive: true});
  const searchUrl = `${config.baseUrl}/issues/?jql=${encodeURIComponent(config.queries[0].jql)}`;
  const browser = cp.spawn(executable, [
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`,
    '--no-first-run', '--no-default-browser-check', searchUrl
  ], {stdio: 'ignore'});

  await getJson(`http://127.0.0.1:${PORT}/json/version`);
  console.log('\nConnectez-vous avec le SSO BNP si nécessaire et attendez l’affichage de Jira.');
  await ask('Puis appuyez sur Entrée pour exécuter toutes les requêtes JQL... ');

  const searches = [];
  const errors = [];
  for (const query of config.queries) {
    let cdp;
    try {
      const url = `${config.baseUrl}/issues/?jql=${encodeURIComponent(query.jql)}`;
      cdp = await openTarget(url);
      console.log(`\n[${query.name}] JQL envoyée : ${query.jql}`);
      const value = await executeJql(cdp, config.baseUrl, query.jql);
      const issues = value.issues || [];
      const keys = issues.map(issue => issue.key).filter(Boolean);
      searches.push({name: query.name, url, jql: query.jql, jql_envoyee: value.jqlEnvoyee,
        total_api: Number(value.total || 0), names: value.names || {}, issues});
      console.log(`[${query.name}] ${issues.length}/${value.total || 0} tickets récupérés`);
      console.log(`[${query.name}] Exemples : ${keys.slice(0, 10).join(', ') || '(aucun)'}`);
    } catch (error) {
      errors.push({name: query.name, jql: query.jql, erreur: String(error.message || error)});
      console.error(`${query.name} : ${error.message || error}`);
    } finally {
      if (cdp) cdp.close();
    }
  }

  const uniqueKeys = new Set(searches.flatMap(search => search.issues.map(issue => issue.key).filter(Boolean)));
  const output = {
    schema_version: '1.0', generated_at: new Date().toISOString(), source_type: 'jira_sso',
    jira_base_url: config.baseUrl, recherches: searches, erreurs_source: errors
  };
  fs.writeFileSync(OUT, JSON.stringify(output, null, 2), 'utf8');
  fs.writeFileSync(DIAGNOSTIC_OUT, JSON.stringify({
    generated_at: output.generated_at,
    remarque: 'Le dashboard utilise l’union des requêtes actives. Utilisez active:false pour exclure une requête.',
    requetes: searches.map(search => ({name: search.name, jql_envoyee: search.jql_envoyee,
      total_api: search.total_api, tickets_recuperes: search.issues.length,
      exemples_cles: search.issues.slice(0, 20).map(issue => issue.key)})),
    erreurs: errors
  }, null, 2), 'utf8');
  try { browser.kill(); } catch (_) {}
  console.log(`JSON JIRA produit : ${OUT}`);
  console.log(`Diagnostic des sélections : ${DIAGNOSTIC_OUT}`);
  console.log(`Requêtes : ${searches.length}/${config.queries.length} | Tickets uniques : ${uniqueKeys.size} | Erreurs : ${errors.length}`);
  if (errors.length) process.exitCode = 1;
}

main().catch(error => { console.error(error); process.exit(1); });
