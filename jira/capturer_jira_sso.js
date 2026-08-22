
// Compatibilité CDP : certains runtimes Node ne fournissent pas WebSocket global.
// On utilise le WebSocket natif si disponible, sinon le module npm "ws".
(function ensureWebSocketForCDP() {
  if (typeof globalThis.WebSocket === "function") {
    return;
  }

  try {
    const wsModule = require("ws");
    globalThis.WebSocket = wsModule.WebSocket || wsModule;
  } catch (error) {
    // Le constructeur CDP affichera une erreur explicite si WebSocket reste absent.
  }
})();

const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const readline = require('readline');

const ROOT = __dirname;
const CONFIG_FILE = path.join(ROOT, 'jira_config.json');
const LEGACY_URLS_FILE = path.join(ROOT, 'jira_urls.txt');
const OUT = path.join(ROOT, 'jira_brut.json');
const DIAGNOSTIC_OUT = path.join(ROOT, 'jira_diagnostic.json');

const PROFILE = path.join(ROOT, '.jira_sso_profile_manuel');
const PORT = 9231;
const PAGE_SIZE = 100;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function cleanBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function jqlFromValue(value, name) {
  if (typeof value === 'string') return value.trim();
  if (!value || value.active === false || value.enabled === false) return '';

  if (value.jql || value.query) {
    return String(value.jql || value.query).trim();
  }

  if (value.filter_id || value.filterId) {
    return `filter = ${value.filter_id || value.filterId}`;
  }

  if (value.url) {
    const parsed = new URL(value.url);
    const jql = parsed.searchParams.get('jql');
    if (jql) return jql.trim();

    const filterId = parsed.searchParams.get('filter');
    if (filterId) return `filter = ${filterId}`;
  }

  throw new Error(
    `La requête "${name}" ne contient ni jql, ni filter_id, ni URL avec ?jql=`
  );
}


function extractProjectKeyFromJql(items) {
  for (const item of (items || [])) {
    const jql = typeof item === 'string' ? item : String(item.jql || '');
    const match = jql.match(/\bproject\s*=\s*"?([A-Z][A-Z0-9_]+)"?/i);
    if (match) return match[1];
  }
  return '';
}

function quoteJqlProject(value) {
  const text = String(value || '').trim();
  if (!text) return 'AERL_GIL';
  return /^[A-Z][A-Z0-9_]*$/.test(text) ? text : '"' + text.replace(/"/g, '\\"') + '"';
}

function readConfiguration() {
  if (fs.existsSync(CONFIG_FILE)) {
    const config = JSON.parse(
      fs.readFileSync(CONFIG_FILE, 'utf8').replace(/^\uFEFF/, '')
    );

    const baseUrl = cleanBaseUrl(config.jira_base_url);
    const rawQueries = config.queries || config.requetes || {};

    const queries = Array.isArray(rawQueries)
      ? rawQueries.map((item, index) => ({
          name: item.name || `requete_${index + 1}`,
          jql: jqlFromValue(item, item.name || `requete_${index + 1}`)
        }))
      : Object.entries(rawQueries).map(([name, value]) => ({
          name,
          jql: jqlFromValue(value, name)
        }));

    const activeQueries = queries
      .map(item => ({
        name: item.name,
        jql: String(item.jql || '').trim()
      }))
      .filter(item => item.jql);

    if (!baseUrl) {
      throw new Error('jira_base_url est absent de jira_config.json');
    }

    if (!activeQueries.length) {
      throw new Error('Aucune requête JQL active dans jira_config.json');
    }

    return {
      baseUrl,
      queries: activeQueries
    };
  }

  if (!fs.existsSync(LEGACY_URLS_FILE)) {
    throw new Error('jira_config.json est introuvable');
  }

  const urls = fs
    .readFileSync(LEGACY_URLS_FILE, 'utf8')
    .split(/\r?\n/)
    .map(value => value.trim())
    .filter(value => value && !value.startsWith('#'));

  if (!urls.length) {
    throw new Error(
      'Créez jira_config.json ou ajoutez une URL active dans jira_urls.txt'
    );
  }

  const parsed = urls.map((value, index) => {
    const url = new URL(value);
    const jql = url.searchParams.get('jql');

    if (!jql) {
      throw new Error(`Paramètre jql absent de l'URL ${index + 1}`);
    }

    return {
      baseUrl: `${url.protocol}//${url.host}`,
      name: `requete_${index + 1}`,
      jql
    };
  });

  return {
    baseUrl: parsed[0].baseUrl,
    queries: parsed.map(({ name, jql }) => ({ name, jql }))
  };
}

function browserPath() {
  const candidates = [
    process.env.JIRA_CHROME,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
  ].filter(Boolean);

  const found = candidates.find(fs.existsSync);

  if (!found) {
    throw new Error(
      'Chrome/Edge introuvable. Définissez la variable JIRA_CHROME.'
    );
  }

  return found;
}

async function getJson(url, tries = 60) {
  for (let index = 0; index < tries; index++) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return await response.json();
      }
    } catch (_) {}

    await sleep(500);
  }

  throw new Error(
    'Le navigateur SSO ne répond pas sur le port de débogage.'
  );
}

function ask(message) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise(resolve =>
    rl.question(message, () => {
      rl.close();
      resolve();
    })
  );
}

class CDP {
  constructor(wsUrl) {
    if (typeof WebSocket === 'undefined') {
      throw new Error(
        'WebSocket indisponible. Lancez Importer_JIRA.cmd avec Node.js 20.'
      );
    }

    this.id = 0;
    this.pending = new Map();
    this.ws = new WebSocket(wsUrl);
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });

    this.ws.onmessage = event => {
      const message = JSON.parse(event.data);
      const pending = this.pending.get(message.id);

      if (!pending) return;

      this.pending.delete(message.id);

      if (message.error) {
        pending.reject(new Error(message.error.message));
      } else {
        pending.resolve(message.result || {});
      }
    };
  }

  send(method, params = {}) {
    const id = ++this.id;

    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    try {
      this.ws.close();
    } catch (_) {}
  }
}
async function attachToAuthenticatedJira(baseUrl) {
  const expected = new URL(baseUrl);
  const expectedOrigin = expected.origin;
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

  async function readPageState(cdp) {
    const state = await cdp.send('Runtime.evaluate', {
      expression: '({href: location.href, origin: location.origin, title: document.title, readyState: document.readyState})',
      returnByValue: true
    });

    return state.result && state.result.value ? state.result.value : {};
  }

  function scoreTarget(target) {
    try {
      const url = new URL(target.url || 'about:blank');
      const title = String(target.title || '').toLowerCase();
      const path = url.pathname || '';

      let score = 0;

      if (url.origin === expectedOrigin) score += 100;
      if (String(target.url || '').startsWith('chrome-error://')) score += 70;
      if (String(target.title || '').includes(expected.host)) score += 60;
      if (path === '/' || path.includes('/secure') || path.includes('/browse') || path.includes('/projects')) score += 20;
      if (path.startsWith('/rest/')) score -= 20;
      if (title.includes('error') || title.includes('erreur')) score -= 20;
      if (String(target.url || '').includes('127.0.0.1')) score -= 1000;
      if (String(target.url || '').includes('dashboard_gil')) score -= 1000;

      return score;
    } catch (_) {
      return -1000;
    }
  }

  async function waitForRealJiraPage(cdp, targetUrl) {
    let page = await readPageState(cdp).catch(() => ({}));

    if (page.origin === expectedOrigin) {
      return page;
    }

    console.log(`[CDP_NAVIGATE_TO_JIRA] actuel=${page.href || targetUrl || '(inconnu)'}`);
    await cdp.send('Page.navigate', {url: baseUrl}).catch(() => {});

    for (let i = 0; i < 90; i++) {
      await delay(1000);

      page = await readPageState(cdp).catch(() => ({}));

      if (page.origin === expectedOrigin && page.readyState !== 'loading') {
        return page;
      }
    }

    throw new Error(
      '[CDP_CONTEXT_ERROR] Onglet CDP non Jira apres navigation. ' +
      'Attendu=' + expectedOrigin +
      ' | Actuel=' + (page.href || page.origin || '(inconnu)')
    );
  }

  const targets = await getJson(
    `http://127.0.0.1:${PORT}/json/list`,
    10
  );

  const pages = targets
    .filter(target => target.type === 'page' && target.webSocketDebuggerUrl)
    .sort((a, b) => scoreTarget(b) - scoreTarget(a));

  if (!pages.length) {
    throw new Error('Aucun onglet Chrome CDP disponible.');
  }

  let lastError = null;

  for (const target of pages) {
    if (scoreTarget(target) <= -500) {
      continue;
    }

    const cdp = new CDP(target.webSocketDebuggerUrl);

    try {
      await cdp.open();
      await cdp.send('Runtime.enable');
      await cdp.send('Page.enable').catch(() => {});
      await cdp.send('Page.bringToFront').catch(() => {});

      const page = await waitForRealJiraPage(cdp, target.url);

      console.log(`Session Jira reutilisee : ${page.title || page.href || baseUrl}`);
      console.log(`[CDP_TARGET_SELECTED] ${page.href || target.url || baseUrl}`);

      return cdp;
    } catch (error) {
      lastError = error;
      cdp.close();
    }
  }

  console.log('[CDP_TARGETS_FOUND]');
  for (const page of pages) {
    console.log(`- ${page.title || '(sans titre)'} | ${page.url || '(sans url)'} | score=${scoreTarget(page)}`);
  }

  throw lastError || new Error('Aucun onglet Jira CDP utilisable.');
}


async function executeJql(cdp, baseUrl, jql) {
  const expression = `
    (async () => {
      const jql = ${JSON.stringify(jql)};
      const apiUrl = ${JSON.stringify(
        `${baseUrl}/rest/api/2/search`
      )};

      const apiParsed = new URL(apiUrl);

      if (location.origin !== apiParsed.origin) {

        throw new Error(

          '[CDP_CONTEXT_ERROR] JQL origin invalide : actuel=' +

          location.href +

          ' attendu=' +

          apiParsed.origin

        );

      }

      const apiPath = apiParsed.pathname + apiParsed.search;

      // CDP_JQL_RELATIVE_FETCH


      const pageSize = ${PAGE_SIZE};

      let startAt = 0;
      let total = null;
      let issues = [];
      let names = {};

      // Le endpoint search?expand=names ne retourne pas toujours
      // tous les champs personnalisés visibles dans Jira.
      // On complète donc le mapping avec /rest/api/2/field,
      // notamment pour retrouver le champ "Reference".
      try {
        const fieldsResponse = await fetch(
          ${JSON.stringify(baseUrl)} + '/rest/api/2/field',
          {
            credentials: 'include',
            headers: {
              'Accept': 'application/json'
            }
          }
        );

        if (fieldsResponse.ok) {
          const jiraFields = await fieldsResponse.json();

          for (const field of (jiraFields || [])) {
            if (field && field.id && field.name) {
              names[field.id] = field.name;
            }
          }
        }
      } catch (fieldError) {
        console.warn(
          '[JIRA_FIELDS] Impossible de charger /rest/api/2/field :',
          String(fieldError && fieldError.message || fieldError)
        );
      }

      while (total === null || startAt < total) {
        const payload = {
          jql,
          startAt,
          maxResults: pageSize,
          fields: ['*all'],
          expand: ['names']
        };

        let response = await fetch(apiPath, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });

        if (
          response.status === 404 ||
          response.status === 405
        ) {
          const apiGet =
            apiUrl +
            '?jql=' + encodeURIComponent(jql) +
            '&startAt=' + startAt +
            '&maxResults=' + pageSize +
            '&expand=names&fields=*all';

          response = await fetch(apiGet, {
            credentials: 'include',
            headers: {
              'Accept': 'application/json'
            }
          });
        }

        if (!response.ok) {
          throw new Error(
            'API JIRA ' +
            response.status +
            ' : ' +
            (await response.text()).slice(0, 500)
          );
        }

        const page = await response.json();

        names = Object.assign(
          names,
          page.names || {}
        );

        issues.push(...(page.issues || []));

        total = Number(page.total || 0);

        if (!(page.issues || []).length) {
          break;
        }

        startAt += page.issues.length;
      }

      return {
        jqlEnvoyee: jql,
        total,
        names,
        issues
      };
    })()
  `;

  const result = await cdp.send(
    'Runtime.evaluate',
    {
      expression,
      awaitPromise: true,
      returnByValue: true
    }
  );

  if (result.exceptionDetails) {
    const detail =
      result.exceptionDetails.exception?.description ||
      result.exceptionDetails.text;

    throw new Error(
      detail ||
      'Erreur JavaScript dans la page Jira'
    );
  }

  if (
    !result.result ||
    !result.result.value
  ) {
    throw new Error(
      'Jira n’a retourné aucune donnée exploitable'
    );
  }

  return result.result.value;
}

function escapeJqlString(value) {
  return String(value || '')
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"');
}

async function fetchEpicChildren(
  cdp,
  baseUrl,
  epicKeys
) {
  const children = [];
  const errors = [];
  const names = {};

  for (const epicKey of epicKeys) {
    console.log(
      `\n[DETAIL EPIC] ${epicKey}`
    );

    /*
     * Selon la version/configuration Jira,
     * une fiche peut être liée :
     * - par parent
     * - par "Epic Link"
     *
     * On essaie les deux.
     */
    const queries = [
      `parent = "${escapeJqlString(epicKey)}"`,
      `"Epic Link" = "${escapeJqlString(epicKey)}"`
    ];

    const issueMap = new Map();

    for (const jql of queries) {
      try {
        const value = await executeJql(
          cdp,
          baseUrl,
          jql
        );

        Object.assign(
          names,
          value.names || {}
        );

        for (const issue of value.issues || []) {
          if (issue.key) {
            issueMap.set(
              issue.key,
              issue
            );
          }
        }
      } catch (error) {
        errors.push({
          epic: epicKey,
          jql,
          erreur: String(
            error.message || error
          )
        });
      }
    }

    const epicChildren = [
      ...issueMap.values()
    ];

    console.log(
      `[DETAIL EPIC] ${epicKey} : ` +
      `${epicChildren.length} fiche(s) rattachée(s)`
    );

    children.push({
      epic_key: epicKey,
      issues: epicChildren
    });
  }

  return {
    children,
    errors,
    names
  };
}


function normalizeList(value) {
  if (value === null || value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

function parseSprintString(text) {
  const s = String(text || '');
  if (!s) return null;

  function get(key) {
    const m = s.match(new RegExp(key + '=([^,\\]]*)'));
    return m ? String(m[1] || '').trim() : '';
  }

  const name = get('name');
  if (!name && !/Sprint/i.test(s)) return null;

  return {
    id: get('id'),
    name: name || s,
    state: get('state'),
    startDate: get('startDate'),
    endDate: get('endDate'),
    completeDate: get('completeDate')
  };
}

function parseSprintEntry(value) {
  if (!value) return null;

  if (typeof value === 'string') {
    return parseSprintString(value);
  }

  if (typeof value === 'object') {
    const name = value.name || value.nom || value.sprintName;
    if (!name && !value.id) return null;

    return {
      id: value.id || value.sprintId || '',
      name: name || String(value.id || ''),
      state: value.state || value.etat || '',
      startDate: value.startDate || value.start_date || '',
      endDate: value.endDate || value.end_date || '',
      completeDate: value.completeDate || value.complete_date || ''
    };
  }

  return null;
}

function sprintFieldIds(names) {
  const ids = [];
  for (const [id, label] of Object.entries(names || {})) {
    const text = String(label || '').toLowerCase();
    if (text === 'sprint' || text.includes('sprint')) ids.push(id);
  }
  return ids;
}

function issueSprints(issue, names) {
  const fields = issue.fields || {};
  const candidates = [];

  for (const id of sprintFieldIds(names)) {
    candidates.push(fields[id]);
  }

  // Fallback : certains Jira exposent le champ Sprint sans nom clair.
  for (const [id, value] of Object.entries(fields)) {
    if (!/^customfield_/.test(id)) continue;
    const list = normalizeList(value);
    if (list.some(v => String(JSON.stringify(v || '')).includes('Sprint'))) {
      candidates.push(value);
    }
  }

  const sprints = [];
  for (const candidate of candidates) {
    for (const item of normalizeList(candidate)) {
      const sprint = parseSprintEntry(item);
      if (sprint && sprint.name) sprints.push(sprint);
    }
  }

  const seen = new Set();
  return sprints.filter(s => {
    const key = String(s.id || s.name);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function issueTypeName(issue) {
  return String(issue?.fields?.issuetype?.name || issue?.fields?.issuetype || '').trim();
}

function issueKind(issue) {
  const type = issueTypeName(issue).toLowerCase();
  return /bug|anomal/i.test(type) ? 'anomalie' : 'flux';
}

function sprintSortValue(sprint) {
  const dateValue = Date.parse(sprint.endDate || sprint.completeDate || sprint.startDate || '');
  if (!Number.isNaN(dateValue)) return dateValue;
  const numericId = Number(sprint.id || 0);
  return Number.isNaN(numericId) ? 0 : numericId;
}

function aggregateSprintIssues(label, result) {
  const names = result.names || {};
  const buckets = new Map();

  for (const issue of (result.issues || [])) {
    const sprints = issueSprints(issue, names);
    const kind = issueKind(issue);

    const effectiveSprints = sprints.length ? sprints : [{
      id: '',
      name: 'Sans sprint',
      state: '',
      startDate: '',
      endDate: '',
      completeDate: ''
    }];

    for (const sprint of effectiveSprints) {
      const key = String(sprint.id || sprint.name);
      if (!buckets.has(key)) {
        buckets.set(key, {
          id: sprint.id || '',
          nom: sprint.name || 'Sans sprint',
          etat: sprint.state || '',
          startDate: sprint.startDate || '',
          endDate: sprint.endDate || '',
          completeDate: sprint.completeDate || '',
          source: label,
          total: 0,
          flux: 0,
          anomalies: 0,
          cles: [],
          clesFlux: [],
          clesAnomalies: []
        });
      }

      const bucket = buckets.get(key);
      bucket.total += 1;
      bucket.cles.push(issue.key);

      if (kind === 'anomalie') {
        bucket.anomalies += 1;
        bucket.clesAnomalies.push(issue.key);
      } else {
        bucket.flux += 1;
        bucket.clesFlux.push(issue.key);
      }
    }
  }

  return Array.from(buckets.values()).sort((a, b) => sprintSortValue(b) - sprintSortValue(a));
}

function pickCurrentSprint(buckets) {
  return buckets.find(s => /active|open|ouvert/i.test(String(s.etat || ''))) || buckets[0] || null;
}

function pickPreviousSprint(buckets, current) {
  const currentName = current ? String(current.nom || '') : '';
  return buckets.find(s => String(s.nom || '') !== currentName) || buckets[0] || null;
}

async function collectSprintDiagnostics(cdp, baseUrl, projectKey) {
  const project = quoteJqlProject(projectKey);

  const jqlCourant = `project = ${project} AND Sprint in openSprints() ORDER BY updated DESC`;
  const jqlFermes = `project = ${project} AND Sprint in closedSprints() ORDER BY updated DESC`;

  console.log(`\n[sprints_courants] JQL envoyée : ${jqlCourant}`);
  const courantResult = await executeJql(cdp, baseUrl, jqlCourant);
  console.log(`[sprints_courants] ${courantResult.issues.length}/${courantResult.total || 0} tickets récupérés`);

  console.log(`\n[sprints_fermes] JQL envoyée : ${jqlFermes}`);
  const fermesResult = await executeJql(cdp, baseUrl, jqlFermes);
  console.log(`[sprints_fermes] ${fermesResult.issues.length}/${fermesResult.total || 0} tickets récupérés`);

  const bucketsCourants = aggregateSprintIssues('openSprints', courantResult);
  const bucketsFermes = aggregateSprintIssues('closedSprints', fermesResult);

  const courant = pickCurrentSprint(bucketsCourants);
  const precedent = pickPreviousSprint(bucketsFermes, courant);

  console.log(`[diagnostic_sprints] Sprint courant détecté : ${courant ? courant.nom : '(non trouvé)'}`);
  console.log(`[diagnostic_sprints] Sprint précédent détecté : ${precedent ? precedent.nom : '(non trouvé)'}`);

  return {
    projectKey,
    generated_at: new Date().toISOString(),
    courant,
    precedent,
    sprintsCourants: bucketsCourants,
    sprintsFermes: bucketsFermes.slice(0, 20),
    requetes: {
      courant: {
        nom: 'sprints_courants',
        jql: jqlCourant,
        total_api: Number(courantResult.total || 0),
        tickets_recuperes: courantResult.issues.length
      },
      fermes: {
        nom: 'sprints_fermes',
        jql: jqlFermes,
        total_api: Number(fermesResult.total || 0),
        tickets_recuperes: fermesResult.issues.length
      }
    }
  };
}


function officialProjectKeyFromQueries(queries) {
  for (const item of (queries || [])) {
    const jql = String(item.jql || item.query || item || '');
    const m = jql.match(/\bproject\s*=\s*"?([A-Z][A-Z0-9_]+)"?/i);
    if (m) return m[1];
  }
  return 'AERL_GIL';
}

async function executeJiraGet(cdp, url) {
  const expression = `
    (async () => {
      const url = ${JSON.stringify(url)};
      const apiParsed = new URL(url);
      if (location.origin !== apiParsed.origin) {
        throw new Error(
          '[CDP_CONTEXT_ERROR] API Agile origin invalide : actuel=' +
          location.href +
          ' attendu=' +
          apiParsed.origin
        );
      }
      const apiPath = apiParsed.pathname + apiParsed.search;
      // CDP_AGILE_RELATIVE_FETCH
      const response = await fetch(apiPath, {
        method: 'GET',
        credentials: 'include',
        headers: {'Accept': 'application/json'}
      });
      const text = await response.text();
      if (!response.ok) {
        throw new Error('API JIRA GET ' + response.status + ' : ' + text.slice(0, 300));
      }
      return JSON.parse(text);
    })()
  `;
  const result = await cdp.send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) {
    const detail = result.exceptionDetails.exception?.description || result.exceptionDetails.text;
    throw new Error(detail || 'Erreur JavaScript API Jira');
  }
  if (!result.result || !result.result.value) throw new Error('Réponse Jira vide');
  return result.result.value;
}

async function agilePaged(cdp, baseUrl, path, itemKey) {
  const items = [];
  let names = {};
  let startAt = 0;
  const maxResults = 100;

  while (true) {
    const sep = path.includes('?') ? '&' : '?';
    const url = `${baseUrl}${path}${sep}startAt=${startAt}&maxResults=${maxResults}`;
    const page = await executeJiraGet(cdp, url);

    const pageItems = page[itemKey] || page.values || page.issues || [];
    items.push(...pageItems);
    names = Object.assign(names, page.names || {});

    const total = Number(page.total ?? items.length);
    const isLast = page.isLast === true;

    if (!pageItems.length || isLast || items.length >= total) break;
    startAt += pageItems.length;
  }

  return {items, names};
}

function sprintDateValue(sprint) {
  const d = Date.parse(sprint.endDate || sprint.completeDate || sprint.startDate || '');
  if (!Number.isNaN(d)) return d;
  return Number(sprint.id || 0);
}

function officialIssueType(issue) {
  const v = issue?.fields?.issuetype;
  return String((v && typeof v === 'object' ? v.name : v) || '');
}

function officialIsAnomaly(issue) {
  return /bug|anomal/i.test(officialIssueType(issue));
}

function filterProjectIssues(issues, projectKey) {
  const prefix = String(projectKey || '').trim() + '-';
  return (issues || []).filter(issue => {
    const key = String(issue.key || '');
    const pkey = String(issue?.fields?.project?.key || '');
    return !projectKey || key.startsWith(prefix) || pkey === projectKey;
  });
}

function summarizeSprint(sprint, issues, projectKey) {
  const projectIssues = filterProjectIssues(issues, projectKey);
  const flux = projectIssues.filter(issue => !officialIsAnomaly(issue));
  const anomalies = projectIssues.filter(issue => officialIsAnomaly(issue));

  return {
    id: sprint.id,
    nom: sprint.name,
    etat: sprint.state,
    startDate: sprint.startDate || '',
    endDate: sprint.endDate || '',
    completeDate: sprint.completeDate || '',
    total: projectIssues.length,
    flux: flux.length,
    anomalies: anomalies.length,
    cles: projectIssues.map(issue => issue.key).filter(Boolean),
    clesFlux: flux.map(issue => issue.key).filter(Boolean),
    clesAnomalies: anomalies.map(issue => issue.key).filter(Boolean)
  };
}

async function collectOfficialSprintDiagnostics(cdp, baseUrl, projectKey) {
  projectKey = projectKey || 'AERL_GIL';

  console.log('');
  console.log('[diagnostic_sprints_officiel] Recherche des boards Jira du projet...');
  const boardsResult = await agilePaged(
    cdp,
    baseUrl,
    `/rest/agile/1.0/board?projectKeyOrId=${encodeURIComponent(projectKey)}`,
    'values'
  );

  const boards = boardsResult.items || [];
  if (!boards.length) {
    throw new Error(`Aucun board Jira trouvé pour le projet ${projectKey}`);
  }

  const preferredBoards = boards
    .filter(board => {
      const type = String(board.type || '').toLowerCase();
      const name = String(board.name || '').toLowerCase();
      return type === 'scrum' || name.includes(String(projectKey || '').toLowerCase()) || name.includes('gil');
    })
    .concat(boards.filter(board => {
      const type = String(board.type || '').toLowerCase();
      const name = String(board.name || '').toLowerCase();
      return !(type === 'scrum' || name.includes(String(projectKey || '').toLowerCase()) || name.includes('gil'));
    }));

  let selected = null;

  for (const board of preferredBoards) {
    try {
      const sprintResult = await agilePaged(
        cdp,
        baseUrl,
        `/rest/agile/1.0/board/${board.id}/sprint?state=active,closed`,
        'values'
      );

      const sprints = sprintResult.items || [];
      const active = sprints.filter(s => String(s.state || '').toLowerCase() === 'active')
        .sort((a, b) => sprintDateValue(b) - sprintDateValue(a))[0];
      const closed = sprints.filter(s => String(s.state || '').toLowerCase() === 'closed')
        .sort((a, b) => sprintDateValue(b) - sprintDateValue(a));

      if (active && closed.length) {
        selected = {board, sprints, active, previous: closed[0]};
        break;
      }

      if (!selected && active) selected = {board, sprints, active, previous: closed[0] || null};
    } catch (error) {
      const msg = String(error.message || error);
      if (msg.includes('ne prend pas en charge les sprints')) {
        console.log(`[diagnostic_sprints_officiel][INFO] Board ${board.id} ignoré : tableau sans sprint`);
      } else {
        console.log(`[diagnostic_sprints_officiel][INFO] Board ${board.id} ignoré : ${msg}`);
      }
    }
  }

  if (!selected || !selected.active || !selected.previous) {
    throw new Error('Impossible de trouver un sprint actif et un sprint fermé via les boards Jira.');
  }

  console.log(`[diagnostic_sprints_officiel] Board détecté : ${selected.board.id} - ${selected.board.name}`);
  console.log(`[diagnostic_sprints_officiel] Sprint courant officiel : ${selected.active.id} - ${selected.active.name}`);
  console.log(`[diagnostic_sprints_officiel] Sprint précédent officiel : ${selected.previous.id} - ${selected.previous.name}`);

  const currentIssuesResult = await agilePaged(
    cdp,
    baseUrl,
    `/rest/agile/1.0/sprint/${selected.active.id}/issue?fields=*all&expand=names`,
    'issues'
  );

  const previousIssuesResult = await agilePaged(
    cdp,
    baseUrl,
    `/rest/agile/1.0/sprint/${selected.previous.id}/issue?fields=*all&expand=names`,
    'issues'
  );

  const currentIssues = filterProjectIssues(currentIssuesResult.items || [], projectKey);
  const previousIssues = filterProjectIssues(previousIssuesResult.items || [], projectKey);

  const names = Object.assign({}, currentIssuesResult.names || {}, previousIssuesResult.names || {});

  const courant = summarizeSprint(selected.active, currentIssues, projectKey);
  const precedent = summarizeSprint(selected.previous, previousIssues, projectKey);

  console.log(`[diagnostic_sprints_officiel] Tickets sprint courant : ${courant.total} | flux: ${courant.flux} | anomalies: ${courant.anomalies}`);
  console.log(`[diagnostic_sprints_officiel] Tickets sprint précédent : ${precedent.total} | flux: ${precedent.flux} | anomalies: ${precedent.anomalies}`);

  return {
    methode: 'agile_api',
    reliable: true,
    generated_at: new Date().toISOString(),
    projectKey,
    board: {
      id: selected.board.id,
      name: selected.board.name,
      type: selected.board.type || ''
    },
    courant,
    precedent,
    sprints: selected.sprints.map(s => ({
      id: s.id,
      nom: s.name,
      etat: s.state,
      startDate: s.startDate || '',
      endDate: s.endDate || '',
      completeDate: s.completeDate || ''
    })),
    issuesCourant: currentIssues,
    issuesPrecedent: previousIssues,
    names
  };
}

async function main() {
  const config = readConfiguration();
  if (!config.projectKey) config.projectKey = officialProjectKeyFromQueries(config.queries);
  const executable = browserPath();

  fs.mkdirSync(
    PROFILE,
    { recursive: true }
  );

const startUrl = config.baseUrl;

console.log(`Ouverture de JIRA : ${startUrl}`);

const browser = cp.spawn(
  executable,
  [
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${PROFILE}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--new-window',
    startUrl
  ],
  { stdio: 'ignore' }
);

  await getJson(
    `http://127.0.0.1:${PORT}/json/version`
  );

console.log('\nUne fenêtre JIRA vient de s’ouvrir.');
console.log(`URL JIRA : ${config.baseUrl}`);
console.log('Connectez-vous avec le SSO, puis attendez que la page JIRA soit complètement chargée.');

  await ask(
    'Revenez ici et appuyez sur Entrée pour exécuter les requêtes JQL... '
  );

  const searches = [];
  const errors = [];

  let epicDetails = [];
  let childErrors = [];
  let childNames = {};

  let cdp;
  let sprintDiagnostic = null;

  try {
    cdp = await attachToAuthenticatedJira(
      config.baseUrl
    );

    console.log('');
    console.log('============================================================');
    console.log('[SPRINTS] DETECTION OFFICIELLE VIA API AGILE JIRA');
    console.log('============================================================');
    console.log(`[SPRINTS] Projet Jira : ${config.projectKey || '(non renseigné)'}`);

    try {
      if (typeof collectOfficialSprintDiagnostics !== 'function') {
        throw new Error('collectOfficialSprintDiagnostics est absente du fichier capturer_jira_sso.js');
      }

      sprintDiagnostic = await collectOfficialSprintDiagnostics(cdp, config.baseUrl, config.projectKey);

      console.log('[SPRINTS] Diagnostic officiel OK.');
      console.log(`[SPRINTS] Board : ${sprintDiagnostic.board?.id || '?'} - ${sprintDiagnostic.board?.name || '?'}`);
      console.log(`[SPRINTS] Sprint courant : ${sprintDiagnostic.courant?.id || '?'} - ${sprintDiagnostic.courant?.nom || '?'}`);
      console.log(`[SPRINTS] Sprint précédent : ${sprintDiagnostic.precedent?.id || '?'} - ${sprintDiagnostic.precedent?.nom || '?'}`);
    } catch (error) {
      const message = String(error && error.message ? error.message : error);

      sprintDiagnostic = {
        methode: 'agile_api',
        reliable: false,
        erreur: message,
        warnings: [message],
        generated_at: new Date().toISOString(),
        projectKey: config.projectKey || ''
      };

      errors.push({
        name: 'diagnostic_sprints_officiel',
        jql: 'API Agile board/sprint/issue',
        erreur: message
      });

      console.log('[SPRINTS][ATTENTION] Diagnostic officiel KO.');
      console.log('[SPRINTS][CAUSE] ' + message);
      console.log('[SPRINTS][ACTION] La publication stable continue sans comparaison dynamique.');
    }

    console.log('');
    console.log('============================================================');
    console.log('[JQL] EXTRACTION DES REQUETES CONFIGUREES');
    console.log('============================================================');

    for (const query of config.queries) {
      try {
        const url =
          `${config.baseUrl}/issues/?jql=` +
          encodeURIComponent(query.jql);

        console.log(
          `\n[${query.name}] JQL envoyée : ${query.jql}`
        );

        const value = await executeJql(
          cdp,
          config.baseUrl,
          query.jql
        );

        const issues =
          value.issues || [];

        const keys = issues
          .map(issue => issue.key)
          .filter(Boolean);

        searches.push({
          name: query.name,
          url,
          jql: query.jql,
          jql_envoyee: value.jqlEnvoyee,
          total_api: Number(
            value.total || 0
          ),
          names: value.names || {},
          issues
        });

        console.log(
          `[${query.name}] ` +
          `${issues.length}/${value.total || 0} tickets récupérés`
        );

        console.log(
          `[${query.name}] Exemples : ` +
          `${keys.slice(0, 10).join(', ') || '(aucun)'}`
        );
      } catch (error) {
        errors.push({
          name: query.name,
          jql: query.jql,
          erreur: String(
            error.message || error
          )
        });

        console.error(
          `${query.name} : ${error.message || error}`
        );
      }
    }

    /*
     * 2. Les Epics sélectionnés par la requête
     * "epics" deviennent la racine des flux.
     */
    const epicSearch =
      searches.find(
        search =>
          String(search.name)
            .toLowerCase() === 'epics'
      ) ||
      searches.find(search =>
        (search.issues || []).some(issue => {
          const type =
            issue.fields?.issuetype?.name ||
            issue.fields?.issuetype?.value ||
            '';

          return String(type)
            .toLowerCase() === 'epic';
        })
      );

    const epicKeys = [
      ...new Set(
        (epicSearch?.issues || [])
          .filter(issue => {
            const type =
              issue.fields?.issuetype?.name ||
              issue.fields?.issuetype?.value ||
              '';

            return (
              String(type)
                .toLowerCase() === 'epic'
            );
          })
          .map(issue => issue.key)
          .filter(Boolean)
      )
    ];

    console.log(
      `\nEpics d'arrimage sélectionnés : ${epicKeys.length}`
    );

    /*
     * 3. Pour chaque Epic, récupération
     * des Stories / Tasks / sous-tâches.
     */
    if (epicKeys.length) {
      const detailResult =
        await fetchEpicChildren(
          cdp,
          config.baseUrl,
          epicKeys
        );

      epicDetails =
        detailResult.children;

      childErrors =
        detailResult.errors;

      childNames =
        detailResult.names;
    }
  } finally {
    if (cdp) {
      cdp.close();
    }
  }

  const mergedNames = {};

  for (const search of searches) {
    Object.assign(
      mergedNames,
      search.names || {}
    );
  }

  Object.assign(
    mergedNames,
    childNames || {}
  );

  const uniqueKeys = new Set();

  for (const search of searches) {
    for (const issue of search.issues || []) {
      if (issue.key) {
        uniqueKeys.add(issue.key);
      }
    }
  }

  for (const detail of epicDetails) {
    for (const issue of detail.issues || []) {
      if (issue.key) {
        uniqueKeys.add(issue.key);
      }
    }
  }

  const output = {
    schema_version: '2.0',
    generated_at: new Date().toISOString(),
    source_type: 'jira_sso',

    jira_base_url:
      config.baseUrl, diagnostic_sprints: sprintDiagnostic,

    /*
     * Résultat brut des deux requêtes
     * configurées.
     */
    recherches:
      searches,

    /*
     * Détail supplémentaire :
     * Epic -> fiches rattachées.
     */
    epic_details:
      epicDetails,

    names:
      mergedNames,

    erreurs_source: [
      ...errors,
      ...childErrors
    ]
  };

  fs.writeFileSync(
    OUT,
    JSON.stringify(
      output,
      null,
      2
    ),
    'utf8'
  );

  fs.writeFileSync(
    DIAGNOSTIC_OUT,
    JSON.stringify(
      {
        generated_at:
          output.generated_at,

        requetes:
          searches.map(search => ({
            name:
              search.name,

            jql_envoyee:
              search.jql_envoyee,

            total_api:
              search.total_api,

            tickets_recuperes:
              search.issues.length,

            exemples_cles:
              search.issues
                .slice(0, 20)
                .map(issue => issue.key)
          })),

        epics_details:
          epicDetails.map(detail => ({
            epic:
              detail.epic_key,

            fiches:
              detail.issues.length,

            cles:
              detail.issues
                .map(issue => issue.key)
          })),

        erreurs:
          output.erreurs_source
      },
      null,
      2
    ),
    'utf8'
  );

  try {
    browser.kill();
  } catch (_) {}

  console.log(
    `\nJSON JIRA produit : ${OUT}`
  );

  console.log(
    `Diagnostic : ${DIAGNOSTIC_OUT}`
  );

  console.log(
    `Tickets uniques récupérés : ${uniqueKeys.size}`
  );

  console.log(
    `Epics détaillés : ${epicDetails.length}`
  );

  console.log(
    `Erreurs : ${output.erreurs_source.length}`
  );

  
if (errors.length) {
  console.error(
    `\n${errors.length} requête(s) principale(s) JIRA ont échoué.`
  );

  process.exitCode = 1;
} else if (childErrors.length) {
  console.warn(
    `\nATTENTION : ${childErrors.length} erreur(s) lors de la récupération détaillée des tâches des Epics.`
  );

  console.warn(
    'Les données disponibles seront néanmoins utilisées.'
  );
}
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});