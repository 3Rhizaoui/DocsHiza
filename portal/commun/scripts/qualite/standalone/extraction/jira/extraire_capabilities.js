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



async function discoverEpicRelationFields(
  cdp,
  baseUrl
) {

  const expression = `
    (async () => {

      const response =
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

      if (!response.ok) {

        throw new Error(
          'API JIRA FIELD '
          + response.status
          + ' : '
          + (
            await response.text()
          ).slice(0, 500)
        );

      }

      const fields =
        await response.json();

      return (
        fields || []
      )
        .filter(field => {

          const name =
            String(
              field?.name || ''
            )
              .trim()
              .toLowerCase();

          return (
            name === 'epic link'
            || name === 'parent link'
            || name.includes('epic link')
            || name.includes('parent link')
          );

        })
        .map(field => ({
          id:
            String(
              field?.id || ''
            ),
          name:
            String(
              field?.name || ''
            )
        }));

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
      'Erreur découverte champs Jira'
    );

  }

  return (
    result.result?.value
    || []
  );
}


async function fetchEpicChildren(
  cdp,
  baseUrl,
  epicKey
) {

  // ==========================================================
  // JIRA STANDALONE - N2/N3 DYNAMIQUE
  //
  // N1 :
  //   Epic [FEATURE GIL]
  //
  // N2 :
  //   ouverture native de /browse/<EPIC>
  //   puis lecture du panneau GreenHopper
  //   "Tickets dans l'Epic"
  //
  // N3 :
  //   récupération REST de chaque ticket découvert.
  //
  // IMPORTANT :
  //   on ne reconstruit PLUS manuellement
  //   AjaxIssueAction!default.jsp.
  //
  // Jira charge lui-même :
  //   ViewIssueManager
  //   GreenHopper
  //   panels
  //   fields
  //   hashes internes
  // ==========================================================

  const errors = [];

  const diagnostics = [];

  let names = {};

  const issueMap =
    new Map();


  // ==========================================================
  // 1. Charger l'Epic avec le moteur Jira natif
  // ==========================================================

  const expression = `
    (async () => {

      const baseUrl =
        ${JSON.stringify(baseUrl)};

      const epicKey =
        ${JSON.stringify(epicKey)};

      const sleep = ms =>
        new Promise(
          resolve =>
            setTimeout(
              resolve,
              ms
            )
        );

      const wantedPath =
        '/browse/'
        + encodeURIComponent(
          epicKey
        );

      const currentPath =
        String(
          window.location.pathname
          || ''
        );

      if (
        !currentPath.endsWith(
          '/browse/' + epicKey
        )
      ) {

        window.location.href =
          baseUrl
          + wantedPath;

        return {
          navigating: true,
          epicKey
        };
      }

      return {
        navigating: false,
        epicKey
      };

    })()
  `;

  let navigationStarted = false;

  try {

    const result =
      await cdp.send(
        'Runtime.evaluate',
        {
          expression,
          awaitPromise: true,
          returnByValue: true
        }
      );

    if (
      result.exceptionDetails
    ) {

      const detail =
        result.exceptionDetails
          .exception
          ?.description
        || result.exceptionDetails.text;

      throw new Error(
        detail
        || 'Erreur navigation Epic Jira'
      );

    }

    navigationStarted =
      Boolean(
        result.result
          ?.value
          ?.navigating
      );

  } catch (error) {

    errors.push({
      source:
        'jira-native-navigation',
      epicKey,
      error:
        String(
          error?.message
          || error
        )
    });

  }


  // ==========================================================
  // 2. Si navigation déclenchée :
  //    attendre que le nouveau document soit réellement chargé.
  // ==========================================================

  if (navigationStarted) {

    const deadline =
      Date.now()
      + 30000;

    let loaded = false;

    while (
      Date.now()
      < deadline
    ) {

      await new Promise(
        resolve =>
          setTimeout(
            resolve,
            500
          )
      );

      try {

        const state =
          await cdp.send(
            'Runtime.evaluate',
            {
              expression: `
                ({
                  readyState:
                    document.readyState,
                  pathname:
                    window.location.pathname,
                  href:
                    window.location.href
                })
              `,
              returnByValue: true
            }
          );

        const value =
          state.result?.value
          || {};

        if (
          (
            value.readyState
            === 'complete'
            ||
            value.readyState
            === 'interactive'
          )
          &&
          String(
            value.pathname
            || ''
          ).endsWith(
            '/browse/'
            + epicKey
          )
        ) {

          loaded = true;
          break;

        }

      } catch (_) {
        // Le contexte JS peut être momentanément détruit
        // pendant la navigation. On continue d'attendre.
      }

    }

    diagnostics.push({
      source:
        'jira-native-navigation',
      epicKey,
      loaded
    });

  }


  // ==========================================================
  // 3. Laisser Jira / GreenHopper charger le panneau N2.
  //
  // On cherche directement dans le DOM réel produit par Jira.
  //
  // Signatures observées BNP :
  //
  //   #ghx-issues-in-epic-table
  //   tr[data-issuekey]
  //   [data-issuekey]
  //
  // ==========================================================

  let panelResult = {
    keys: [],
    diagnostics: {}
  };

  try {

    const panelExpression = `
      (async () => {

        const epicKey =
          ${JSON.stringify(epicKey)};

        const sleep = ms =>
          new Promise(
            resolve =>
              setTimeout(
                resolve,
                ms
              )
          );

        const started =
          Date.now();

        const timeoutMs =
          30000;

        let keys = [];

        let tableFound =
          false;

        let panelFound =
          false;

        let iteration =
          0;

        while (
          Date.now()
          - started
          < timeoutMs
        ) {

          iteration += 1;

          const table =
            document.querySelector(
              '#ghx-issues-in-epic-table'
            );

          if (table) {
            tableFound = true;
          }

          const panel =
            document.querySelector(
              '#greenhopper-epics-issue-web-panel'
            )
            ||
            document.querySelector(
              '[id*="greenhopper-epics"]'
            )
            ||
            document.querySelector(
              '[class*="ghx-issuetable"]'
            );

          if (panel) {
            panelFound = true;
          }

          const nodes =
            [
              ...document.querySelectorAll(
                '#ghx-issues-in-epic-table [data-issuekey]'
              ),
              ...document.querySelectorAll(
                'tr[data-issuekey]'
              )
            ];

          const found =
            [];

          for (
            const node
            of nodes
          ) {

            const key =
              String(
                node.getAttribute(
                  'data-issuekey'
                )
                || ''
              ).trim();

            if (
              key
              &&
              key !== epicKey
              &&
              !found.includes(key)
            ) {

              found.push(key);

            }

          }

          keys = found;

          if (
            keys.length > 0
          ) {
            break;
          }

          await sleep(500);

        }

        return {
          keys,
          diagnostics: {
            epicKey,
            pathname:
              window.location.pathname,
            title:
              document.title,
            tableFound,
            panelFound,
            iterations:
              iteration,
            elapsedMs:
              Date.now()
              - started
          }
        };

      })()
    `;

    const result =
      await cdp.send(
        'Runtime.evaluate',
        {
          expression:
            panelExpression,
          awaitPromise: true,
          returnByValue: true
        }
      );

    if (
      result.exceptionDetails
    ) {

      const detail =
        result.exceptionDetails
          .exception
          ?.description
        || result.exceptionDetails.text;

      throw new Error(
        detail
        || 'Erreur lecture panneau GreenHopper'
      );

    }

    panelResult =
      result.result?.value
      || panelResult;

    diagnostics.push({
      source:
        'greenhopper-native-dom',
      epicKey,
      count:
        (
          panelResult.keys
          || []
        ).length,
      ...(
        panelResult.diagnostics
        || {}
      )
    });

    console.log(
      '  [JIRA][N2][GREENHOPPER]',
      epicKey,
      '=>',
      (
        panelResult.keys
        || []
      ).length,
      'ticket(s)'
    );

  } catch (error) {

    errors.push({
      source:
        'greenhopper-native-dom',
      epicKey,
      error:
        String(
          error?.message
          || error
        )
    });

    console.log(
      '  [JIRA][N2][ERROR]',
      epicKey,
      '=>',
      String(
        error?.message
        || error
      )
    );

  }


  // ==========================================================
  // 4. N3 : récupérer le détail REST de chaque enfant.
  //
  // On utilise la session SSO déjà ouverte dans Jira.
  // ==========================================================

  const childKeys =
    Array.isArray(
      panelResult.keys
    )
      ? panelResult.keys
      : [];

  for (
    const childKey
    of childKeys
  ) {

    try {

      const childExpression = `
        (async () => {

          const baseUrl =
            ${JSON.stringify(baseUrl)};

          const childKey =
            ${JSON.stringify(childKey)};

          const url =
            baseUrl
            + '/rest/api/2/issue/'
            + encodeURIComponent(
                childKey
              )
            + '?expand=names,schema,renderedFields';

          const response =
            await fetch(
              url,
              {
                method:
                  'GET',
                credentials:
                  'include',
                headers: {
                  'Accept':
                    'application/json'
                }
              }
            );

          const text =
            await response.text();

          if (
            !response.ok
          ) {

            throw new Error(
              'HTTP '
              + response.status
              + ' sur '
              + childKey
              + ' : '
              + text.slice(
                  0,
                  800
                )
            );

          }

          const data =
            JSON.parse(
              text
            );

          return {
            issue:
              data,
            names:
              data.names
              || {}
          };

        })()
      `;

      const result =
        await cdp.send(
          'Runtime.evaluate',
          {
            expression:
              childExpression,
            awaitPromise: true,
            returnByValue: true
          }
        );

      if (
        result.exceptionDetails
      ) {

        const detail =
          result.exceptionDetails
            .exception
            ?.description
          || result.exceptionDetails.text;

        throw new Error(
          detail
          || (
            'Erreur REST N3 '
            + childKey
          )
        );

      }

      const value =
        result.result?.value
        || {};

      const issue =
        value.issue
        || null;

      names =
        Object.assign(
          names,
          value.names
          || {}
        );

      if (
        issue
        &&
        issue.key
      ) {

        issueMap.set(
          issue.key,
          issue
        );

        console.log(
          '  [JIRA][N3]',
          issue.key,
          '|',
          issue.fields?.summary
            || '',
          '| status =',
          issue.fields?.status
            ?.name
            || '',
          '| type =',
          issue.fields?.issuetype
            ?.name
            || ''
        );

      }

    } catch (error) {

      errors.push({
        source:
          'jira-rest-n3',
        epicKey,
        childKey,
        error:
          String(
            error?.message
            || error
          )
      });

      console.log(
        '  [JIRA][N3][ERROR]',
        childKey,
        '=>',
        String(
          error?.message
          || error
        )
      );

    }

  }


  // ==========================================================
  // 5. Fallback diagnostic.
  //
  // On garde parent = Epic uniquement comme filet de sécurité.
  // Ce n'est PLUS la source métier principale.
  // ==========================================================

  if (
    issueMap.size === 0
  ) {

    try {

      const fallbackJql =
        `parent = "${escapeJqlString(epicKey)}"`;

      const value =
        await executeJql(
          cdp,
          baseUrl,
          fallbackJql
        );

      names =
        Object.assign(
          names,
          value.names
          || {}
        );

      const found =
        value.issues
        || [];

      diagnostics.push({
        source:
          'parent-fallback',
        epicKey,
        count:
          found.length
      });

      for (
        const issue
        of found
      ) {

        if (
          issue?.key
        ) {

          issueMap.set(
            issue.key,
            issue
          );

        }

      }

      console.log(
        '  [JIRA][N2][FALLBACK]',
        epicKey,
        '=>',
        found.length,
        'ticket(s)'
      );

    } catch (error) {

      errors.push({
        source:
          'parent-fallback',
        epicKey,
        error:
          String(
            error?.message
            || error
          )
      });

    }

  }


  // ==========================================================
  // 6. Retour normalisé
  // ==========================================================

  const issues =
    [
      ...issueMap.values()
    ];

  diagnostics.push({
    source:
      'jira-n2-n3-summary',
    epicKey,
    count:
      issues.length,
    keys:
      issues.map(
        issue =>
          issue.key
      )
  });

  console.log(
    '  [JIRA][N2/N3][SUMMARY]',
    epicKey,
    '=>',
    issues.length,
    'ticket(s)'
  );

  return {
    issues,
    names,
    errors,
    diagnostics
  };

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

      for (
        const childError
        of children.errors || []
      ) {

        console.log(
          '  [JIRA CHILD QUERY ERROR]',
          childError.jql,
          '=>',
          childError.error
        );

      }

      detailed.push({
        epic,
        children:
          children.issues || [],
        childrenDiagnostics:
          children.diagnostics || []
      });

      console.log(
        '  ->',
        (children.issues || []).length,
        'tâche(s) / issue(s) liée(s)'
      );

      console.log(
        '  [JIRA][FIELDS]',
        JSON.stringify(
          epic.fields || {},
          null,
          2
        )
      );

      for (
        const child
        of children.issues || []
      ) {

        console.log(
          '  [JIRA][CHILD]',
          child.key || '',
          '|',
          child.fields?.summary || '',
          '| status =',
          child.fields?.status?.name || ''
        );
      }

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

    console.log();
    console.log(
      '[JIRA][SUMMARY]',
      'capabilities =',
      capabilities.length,
      '| enfants =',
      output.diagnostic.children,
      '| erreurs =',
      errors.length
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
