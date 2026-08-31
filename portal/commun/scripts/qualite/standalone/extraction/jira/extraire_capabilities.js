const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const readline = require('readline');


// ============================================================
// CHEMINS STANDALONE
// ============================================================

const ROOT = __dirname;

const STANDALONE_ROOT = path.resolve(
  ROOT,
  '..',
  '..'
);

const SCRIPTS_DIR = path.resolve(
  STANDALONE_ROOT,
  '..',
  '..'
);

const COMMUN_DIR = path.resolve(
  SCRIPTS_DIR,
  '..'
);

const DATA_DIR = path.resolve(
  COMMUN_DIR,
  'data',
  'standalone',
  'jira'
);

const CONFIG_FILE = path.join(
  ROOT,
  'jira_config_standalone.json'
);

const OUT = path.join(
  DATA_DIR,
  'capabilities_brut.json'
);


// ============================================================
// CONFIGURATION TECHNIQUE
// ============================================================

const PORT = 9231;
const PAGE_SIZE = 100;

const PROFILE = path.resolve(
  ROOT,
  '.jira_sso_profile_standalone'
);

const sleep = ms =>
  new Promise(resolve => setTimeout(resolve, ms));


// ============================================================
// WEBSOCKET CDP
// ============================================================

(function ensureWebSocketForCDP() {

  if (
    typeof globalThis.WebSocket === 'function'
  ) {
    return;
  }

  try {

    const wsModule = require('ws');

    globalThis.WebSocket =
      wsModule.WebSocket ||
      wsModule;

  } catch (_) {
  }

})();


// ============================================================
// OUTILS
// ============================================================

function cleanBaseUrl(value) {

  return String(
    value || ''
  )
    .trim()
    .replace(/\/+$/, '');

}


function readConfiguration() {

  if (!fs.existsSync(CONFIG_FILE)) {

    throw new Error(
      `Configuration Standalone absente : ${CONFIG_FILE}`
    );

  }

  const config = JSON.parse(
    fs.readFileSync(
      CONFIG_FILE,
      'utf8'
    ).replace(/^\uFEFF/, '')
  );

  const baseUrl = cleanBaseUrl(
    config.jira_base_url
  );

  const jql = String(
    config.jql || ''
  ).trim();

  const queryName = String(
    config.query_name ||
    'capabilities_gil'
  ).trim();

  if (!baseUrl) {

    throw new Error(
      'jira_base_url absent'
    );

  }

  if (!jql) {

    throw new Error(
      'jql Standalone absent'
    );

  }

  return {
    baseUrl,
    queryName,
    jql,
    businessRules:
      config.business_rules || {}
  };

}


function browserPath() {

  const candidates = [
    process.env.JIRA_CHROME,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
  ].filter(Boolean);

  const found = candidates.find(
    fs.existsSync
  );

  if (!found) {

    throw new Error(
      'Chrome/Edge introuvable.'
    );

  }

  return found;
}


function ask(message) {

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise(resolve =>

    rl.question(
      message,
      () => {
        rl.close();
        resolve();
      }
    )

  );

}


async function getJson(
  url,
  tries = 60
) {

  for (
    let index = 0;
    index < tries;
    index++
  ) {

    try {

      const response = await fetch(url);

      if (response.ok) {

        return await response.json();

      }

    } catch (_) {
    }

    await sleep(500);

  }

  throw new Error(
    'Le navigateur SSO ne répond pas.'
  );

}


// ============================================================
// CLIENT CDP
// ============================================================

class CDP {

  constructor(wsUrl) {

    if (
      typeof WebSocket === 'undefined'
    ) {

      throw new Error(
        'WebSocket indisponible.'
      );

    }

    this.id = 0;
    this.pending = new Map();

    this.ws = new WebSocket(
      wsUrl
    );

  }


  async open() {

    await new Promise(
      (resolve, reject) => {

        this.ws.onopen = resolve;
        this.ws.onerror = reject;

      }
    );

    this.ws.onmessage = event => {

      const message = JSON.parse(
        event.data
      );

      const pending =
        this.pending.get(
          message.id
        );

      if (!pending) {
        return;
      }

      this.pending.delete(
        message.id
      );

      if (message.error) {

        pending.reject(
          new Error(
            message.error.message
          )
        );

      } else {

        pending.resolve(
          message.result || {}
        );

      }

    };

  }


  send(
    method,
    params = {}
  ) {

    const id = ++this.id;

    return new Promise(
      (resolve, reject) => {

        this.pending.set(
          id,
          {
            resolve,
            reject
          }
        );

        this.ws.send(
          JSON.stringify({
            id,
            method,
            params
          })
        );

      }
    );

  }


  close() {

    try {
      this.ws.close();
    } catch (_) {
    }

  }

}


// ============================================================
// ATTACHEMENT SESSION JIRA
// ============================================================

async function attachToAuthenticatedJira(
  baseUrl
) {

  const expectedOrigin =
    new URL(
      baseUrl
    ).origin;

  const targets = await getJson(
    `http://127.0.0.1:${PORT}/json/list`,
    10
  );

  const pages = targets
    .filter(
      target =>
        target.type === 'page' &&
        target.webSocketDebuggerUrl
    )
    .filter(target => {

      try {

        return (
          new URL(
            target.url || 'about:blank'
          ).origin === expectedOrigin
        );

      } catch (_) {

        return false;

      }

    });

  if (!pages.length) {

    throw new Error(
      'Aucun onglet Jira authentifié disponible.'
    );

  }

  const target = pages[0];

  const cdp = new CDP(
    target.webSocketDebuggerUrl
  );

  await cdp.open();

  await cdp.send(
    'Runtime.enable'
  );

  await cdp.send(
    'Page.enable'
  ).catch(() => {});

  await cdp.send(
    'Page.bringToFront'
  ).catch(() => {});

  console.log(
    'Session Jira utilisée :',
    target.url
  );

  return cdp;

}


// ============================================================
// EXECUTION JQL
// ============================================================

async function executeJql(
  cdp,
  baseUrl,
  jql
) {

  const expression = `
    (async () => {

      const jql =
        ${JSON.stringify(jql)};

      const apiUrl =
        ${JSON.stringify(
          `${baseUrl}/rest/api/2/search`
        )};

      const pageSize =
        ${PAGE_SIZE};

      let startAt = 0;
      let total = null;

      let issues = [];
      let names = {};

      try {

        const fieldsResponse =
          await fetch(
            ${JSON.stringify(baseUrl)}
            + '/rest/api/2/field',
            {
              credentials: 'include',
              headers: {
                'Accept':
                  'application/json'
              }
            }
          );

        if (fieldsResponse.ok) {

          const jiraFields =
            await fieldsResponse.json();

          for (
            const field
            of (jiraFields || [])
          ) {

            if (
              field &&
              field.id &&
              field.name
            ) {

              names[field.id] =
                field.name;

            }

          }

        }

      } catch (_) {
      }

      while (
        total === null ||
        startAt < total
      ) {

        const payload = {
          jql,
          startAt,
          maxResults: pageSize,
          fields: ['*all'],
          expand: ['names']
        };

        const response =
          await fetch(
            '/rest/api/2/search',
            {
              method: 'POST',
              credentials: 'include',
              headers: {
                'Accept':
                  'application/json',
                'Content-Type':
                  'application/json'
              },
              body:
                JSON.stringify(
                  payload
                )
            }
          );

        if (!response.ok) {

          throw new Error(
            'API JIRA '
            + response.status
            + ' : '
            + (
              await response.text()
            ).slice(0, 500)
          );

        }

        const page =
          await response.json();

        names =
          Object.assign(
            names,
            page.names || {}
          );

        issues.push(
          ...(page.issues || [])
        );

        total =
          Number(
            page.total || 0
          );

        if (
          !(page.issues || []).length
        ) {
          break;
        }

        startAt +=
          page.issues.length;

      }

      return {
        jql,
        total,
        names,
        issues
      };

    })()
  `;

  const result =
    await cdp.send(
      'Runtime.evaluate',
      {
        expression,
        awaitPromise: true,
        returnByValue: true
      }
    );

  if (result.exceptionDetails) {

    const detail =
      result.exceptionDetails
        .exception
        ?.description ||
      result.exceptionDetails.text;

    throw new Error(
      detail ||
      'Erreur JavaScript Jira'
    );

  }

  if (
    !result.result ||
    !result.result.value
  ) {

    throw new Error(
      'Réponse Jira vide'
    );

  }

  return result.result.value;

}


// ============================================================
// ENFANTS EPIC
// ============================================================

function escapeJqlString(value) {

  return String(
    value || ''
  )
    .replace(
      /\\/g,
      '\\\\'
    )
    .replace(
      /"/g,
      '\\"'
    );

}


async function fetchEpicChildren(
  cdp,
  baseUrl,
  epicKey
) {

  const issueMap =
    new Map();

  const errors = [];

  const queries = [
    `parent = "${escapeJqlString(epicKey)}"`,
    `"Epic Link" = "${escapeJqlString(epicKey)}"`
  ];

  let names = {};

  for (
    const childJql
    of queries
  ) {

    try {

      const value =
        await executeJql(
          cdp,
          baseUrl,
          childJql
        );

      names =
        Object.assign(
          names,
          value.names || {}
        );

      for (
        const issue
        of value.issues || []
      ) {

        if (issue.key) {

          issueMap.set(
            issue.key,
            issue
          );

        }

      }

    } catch (error) {

      errors.push({
        epicKey,
        jql: childJql,
        error:
          String(
            error.message || error
          )
      });

    }

  }

  return {
    issues: [
      ...issueMap.values()
    ],
    names,
    errors
  };

}


// ============================================================
// FILTRE STRICT FEATURE GIL
// ============================================================

function isFeatureGil(
  issue,
  regexText
) {

  const summary =
    String(
      issue?.fields?.summary || ''
    );

  if (!regexText) {

    return /\[\s*FEATURE\s+GIL\s*\]/i
      .test(summary);

  }

  try {

    return new RegExp(
      regexText,
      'i'
    ).test(summary);

  } catch (_) {

    return /\[\s*FEATURE\s+GIL\s*\]/i
      .test(summary);

  }

}


// ============================================================
// MAIN
// ============================================================

async function main() {

  const config =
    readConfiguration();

  fs.mkdirSync(
    DATA_DIR,
    {
      recursive: true
    }
  );

  fs.mkdirSync(
    PROFILE,
    {
      recursive: true
    }
  );

  const chrome =
    browserPath();

  console.log();
  console.log(
    '='.repeat(70)
  );
  console.log(
    'GIL STANDALONE - EXTRACTION JIRA CAPABILITIES'
  );
  console.log(
    '='.repeat(70)
  );

  console.log();
  console.log(
    'JQL :',
    config.jql
  );

  console.log();
  console.log(
    'Ouverture Jira SSO...'
  );

  const browser =
    cp.spawn(
      chrome,
      [
        `--remote-debugging-port=${PORT}`,
        `--user-data-dir=${PROFILE}`,
        config.baseUrl
      ],
      {
        detached: true,
        stdio: 'ignore'
      }
    );

  browser.unref();

  await ask(
    '\nConnecte-toi à Jira si nécessaire puis appuie sur Entrée... '
  );

  const cdp =
    await attachToAuthenticatedJira(
      config.baseUrl
    );

  try {

    console.log();
    console.log(
      '[CAPABILITIES] Extraction des Epics...'
    );

    const epicResult =
      await executeJql(
        cdp,
        config.baseUrl,
        config.jql
      );

    const regexText =
      config.businessRules
        ?.summary_regex ||
      '';

    const capabilities =
      (
        epicResult.issues || []
      )
        .filter(
          issue =>
            isFeatureGil(
              issue,
              regexText
            )
        );

    console.log(
      '[CAPABILITIES]',
      capabilities.length,
      'Epic(s) [FEATURE GIL]'
    );

    const detailed = [];

    let globalNames =
      Object.assign(
        {},
        epicResult.names || {}
      );

    const errors = [];

    for (
      const epic
      of capabilities
    ) {

      console.log();
      console.log(
        '[CAPABILITY]',
        epic.key,
        '-',
        epic.fields?.summary || ''
      );

      const children =
        await fetchEpicChildren(
          cdp,
          config.baseUrl,
          epic.key
        );

      globalNames =
        Object.assign(
          globalNames,
          children.names || {}
        );

      errors.push(
        ...(children.errors || [])
      );

      detailed.push({
        epic,
        children:
          children.issues || []
      });

      console.log(
        '  ->',
        (children.issues || []).length,
        'tâche(s) / issue(s) liée(s)'
      );

    }

    const output = {
      schemaVersion: 1,

      generatedAt:
        new Date().toISOString(),

      source: {
        type: 'JIRA SSO',
        baseUrl:
          config.baseUrl,
        queryName:
          config.queryName,
        jql:
          config.jql
      },

      businessRules:
        config.businessRules,

      fields:
        globalNames,

      capabilities:
        detailed,

      diagnostic: {
        epicsApi:
          Number(
            epicResult.total || 0
          ),

        featureGil:
          capabilities.length,

        children:
          detailed.reduce(
            (
              total,
              row
            ) =>
              total +
              (
                row.children || []
              ).length,
            0
          ),

        errors
      }
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

    console.log();
    console.log(
      'OK - fichier produit :',
      OUT
    );

    console.log(
      'Capabilities :',
      capabilities.length
    );

    console.log(
      'Issues enfants :',
      output.diagnostic.children
    );

  } finally {

    cdp.close();

  }

}


main()
  .catch(error => {

    console.error();
    console.error(
      '[ERREUR STANDALONE JIRA]'
    );

    console.error(
      error &&
      (
        error.stack ||
        error.message
      )
      ||
      error
    );

    process.exitCode = 1;

  });
