const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const readline = require('readline');

const ROOT = __dirname;
const URL_FILE = path.join(ROOT, 'confluence_urls.txt');
const OUT_DIR = path.join(ROOT, 'captures_confluence');
const PROFILE = path.join(ROOT, '.confluence_sso_profile');
const PORT = 9227;

function readUrls() {
  return fs.readFileSync(URL_FILE, 'utf8').split(/\r?\n/)
    .map(x => x.trim()).filter(x => x && !x.startsWith('#'));
}
function browserPath() {
  const candidates = [process.env.CONFLUENCE_CHROME,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'].filter(Boolean);
  const found = candidates.find(fs.existsSync);
  if (!found) throw new Error('Chrome/Edge introuvable. Définissez CONFLUENCE_CHROME.');
  return found;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function getJson(url, tries = 40) {
  for (let i = 0; i < tries; i++) {
    try { const r = await fetch(url); if (r.ok) return await r.json(); } catch (_) {}
    await sleep(500);
  }
  throw new Error('Le navigateur de capture ne répond pas.');
}
function ask(message) {
  const rl = readline.createInterface({input: process.stdin, output: process.stdout});
  return new Promise(resolve => rl.question(message, () => { rl.close(); resolve(); }));
}
class CDP {
  constructor(wsUrl) { this.id = 0; this.pending = new Map(); this.ws = new WebSocket(wsUrl); }
  async open() {
    await new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = ev => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const p = this.pending.get(msg.id); this.pending.delete(msg.id);
        msg.error ? p.reject(new Error(msg.error.message)) : p.resolve(msg.result || {});
      }
    };
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, {resolve, reject});
      this.ws.send(JSON.stringify({id, method, params}));
    });
  }
  close() { this.ws.close(); }
}

async function main() {
  const list = readUrls();
  if (!list.length) throw new Error('Aucune URL active dans confluence_urls.txt');
  fs.mkdirSync(OUT_DIR, {recursive: true});
  fs.mkdirSync(PROFILE, {recursive: true});
  const browser = cp.spawn(browserPath(), [`--remote-debugging-port=${PORT}`,
    `--user-data-dir=${PROFILE}`, '--no-first-run', '--no-default-browser-check', list[0]],
    {stdio: 'ignore'});
  await getJson(`http://127.0.0.1:${PORT}/json/version`);
  console.log('\nConnectez-vous avec le SSO BNP si nécessaire et attendez le tableau Confluence.');
  await ask('Puis appuyez sur Entrée pour capturer toutes les pages... ');

  const manifest = {captured_at: new Date().toISOString(), pages: []};
  for (let i = 0; i < list.length; i++) {
    const url = list[i];
    const response = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, {method: 'PUT'});
    if (!response.ok) throw new Error(`Impossible d'ouvrir ${url}`);
    const target = await response.json();
    const cdp = new CDP(target.webSocketDebuggerUrl); await cdp.open();
    await cdp.send('Page.enable'); await cdp.send('Page.navigate', {url});
    for (let n = 0; n < 60; n++) {
      await sleep(500);
      const state = await cdp.send('Runtime.evaluate', {expression: 'document.readyState', returnByValue: true});
      if (state.result?.value === 'complete') break;
    }
    await sleep(3000);
    const result = await cdp.send('Runtime.evaluate', {
      expression: 'JSON.stringify({title:document.title,html:document.documentElement.outerHTML,url:location.href})',
      returnByValue: true});
    const page = JSON.parse(result.result.value);
    if (/login|connexion|auth/i.test(page.url) || !/<table/i.test(page.html))
      throw new Error(`Page non exploitable (SSO ou tableau absent) : ${url}`);
    const file = `page_${i + 1}.html`;
    fs.writeFileSync(path.join(OUT_DIR, file), page.html, 'utf8');
    manifest.pages.push({url, final_url: page.url, title: page.title, file});
    console.log(`Capture ${i + 1}/${list.length} : ${page.title}`); cdp.close();
  }
  fs.writeFileSync(path.join(OUT_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf8');
  console.log('Captures terminées. Vous pouvez fermer le navigateur de capture.');
  browser.unref();
}
main().catch(e => { console.error('\nERREUR : ' + e.message); process.exit(1); });
