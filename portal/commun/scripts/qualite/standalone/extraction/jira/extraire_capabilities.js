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
  // N2 JIRA - source principale
  //
  // Jira BNP n'expose pas les tickets de l'Epic via :
  //   parent = EPIC
  //   Epic Link = EPIC
  //
  // L'interface Jira utilise le panneau GreenHopper :
  //   greenhopper-epics-issue-web-panel
  //
  // On reproduit donc le même parcours dynamique :
  //
  // N1 Epic
  //   -> AjaxIssueAction!default.jsp
  // N2 Tickets dans l'Epic
  //   -> extraction des data-issuekey
  // N3 détail REST de chaque ticket
  // ==========================================================

  const expression = `
    (async () => {

      const baseUrl =
        ${JSON.stringify(baseUrl)};

      const epicKey =
        ${JSON.stringify(epicKey)};

      const diagnostics = [];

      const errors = [];

      const issueMap = {};

      // -------------------------------------------------------
      // 1. Charger le panneau Jira de l'Epic.
      // -------------------------------------------------------

      const body =
        new URLSearchParams();

      body.append(
        'issueKey',
        epicKey
      );

      body.append(
        'decorator',
        'none'
      );

      body.append(
        'prefetch',
        'false'
      );

      body.append(
        'shouldUpdateCurrentProject',
        'false'
      );

      body.append(
        'lastReadTime',
        String(Date.now())
      );

      let ajaxData = null;

      try {

        const response =
          await fetch(
            baseUrl
            + '/secure/AjaxIssueAction!default.jsp',
            {
              method: 'POST',
              credentials: 'include',
              headers: {
                'Accept':
                  'application/json, text/javascript, */*; q=0.01',
                'Content-Type':
                  'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With':
                  'XMLHttpRequest'
              },
              body:
                body.toString()
            }
          );

        const text =
          await response.text();

        if (!response.ok) {

          throw new Error(
            'HTTP '
            + response.status
            + ' : '
            + text.slice(0, 800)
          );

        }

        try {

          ajaxData =
            JSON.parse(text);

        } catch (error) {

          throw new Error(
            'Réponse AjaxIssueAction non JSON : '
            + text.slice(0, 800)
          );

        }

      } catch (error) {

        errors.push({
          source:
            'greenhopper-epics-issue-web-panel',
          epicKey,
          error:
            String(
              error?.message ||
              error
            )
        });

      }

      // -------------------------------------------------------
      // 2. Trouver le HTML du panneau
      //    "Tickets dans l'epic".
      // -------------------------------------------------------

      let panelHtml = '';

      if (ajaxData) {

        const candidates = [];

        const visit = value => {

          if (!value) {
            return;
          }

          if (Array.isArray(value)) {

            for (const item of value) {
              visit(item);
            }

            return;
          }

          if (
            typeof value === 'object'
          ) {

            const completeKey =
              String(
                value.completeKey ||
                value.key ||
                value.id ||
                ''
              );

            const html =
              String(
                value.html ||
                value.content ||
                ''
              );

            if (
              completeKey.includes(
                'greenhopper-epics-issue-web-panel'
              )
              || html.includes(
                'ghx-issues-in-epic-table'
              )
              || html.includes(
                'data-issuekey='
              )
            ) {

              candidates.push({
                completeKey,
                html
              });

            }

            for (
              const child
              of Object.values(value)
            ) {

              visit(child);

            }

          }

        };

        visit(ajaxData);

        candidates.sort(
          (a, b) =>
            b.html.length
            - a.html.length
        );

        panelHtml =
          candidates[0]?.html || '';

        diagnostics.push({
          source:
            'greenhopper-panel',
          epicKey,
          candidates:
            candidates.length,
          htmlLength:
            panelHtml.length
        });

      }

      // -------------------------------------------------------
      // 3. Extraire toutes les clés N2 depuis le HTML.
      // -------------------------------------------------------

      const childKeys = [];

      if (panelHtml) {

        const parser =
          new DOMParser();

        const document =
          parser.parseFromString(
            panelHtml,
            'text/html'
          );

        const rows =
          document.querySelectorAll(
            '[data-issuekey]'
          );

        for (const row of rows) {

          const key =
            String(
              row.getAttribute(
                'data-issuekey'
              )
              || ''
            ).trim();

          if (
            key
            && key !== epicKey
            && !childKeys.includes(key)
          ) {

            childKeys.push(key);

          }

        }

      }

      diagnostics.push({
        source:
          'greenhopper-children',
        epicKey,
        count:
          childKeys.length,
        keys:
          childKeys
      });

      // -------------------------------------------------------
      // 4. N3 : pour chaque ticket découvert,
      //    récupérer le vrai détail Jira.
      // -------------------------------------------------------

      for (
        const childKey
        of childKeys
      ) {

        try {

          const response =
            await fetch(
              baseUrl
              + '/rest/api/2/issue/'
              + encodeURIComponent(
                  childKey
                )
              + '?expand=names',
              {
                method: 'GET',
                credentials: 'include',
                headers: {
                  'Accept':
                    'application/json'
                }
              }
            );

          const text =
            await response.text();

          if (!response.ok) {

            throw new Error(
              'HTTP '
              + response.status
              + ' : '
              + text.slice(0, 500)
            );

          }

          const issue =
            JSON.parse(text);

          issueMap[childKey] =
            issue;

        } catch (error) {

          errors.push({
            source:
              'issue-detail',
            epicKey,
            childKey,
            error:
              String(
                error?.message ||
                error
              )
          });

          // On conserve au minimum la clé découverte
          // même si le détail REST échoue.
          issueMap[childKey] = {
            key:
              childKey,
            fields: {}
          };

        }

      }

      return {
        issues:
          Object.values(
            issueMap
          ),
        names: {},
        errors,
        diagnostics,
        source:
          'greenhopper'
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
        ?.description
      || result.exceptionDetails.text;

    throw new Error(
      detail
      || 'Erreur extraction dynamique enfants Jira'
    );

  }

  const dynamicResult =
    result.result?.value
    || {
      issues: [],
      names: {},
      errors: [],
      diagnostics: []
    };

  console.log(
    '  [JIRA][N2][GREENHOPPER]',
    epicKey,
    '=>',
    (
      dynamicResult.issues
      || []
    ).length,
    'ticket(s)'
  );

  for (
    const diagnostic
    of dynamicResult.diagnostics || []
  ) {

    console.log(
      '  [JIRA][N2][DIAG]',
      JSON.stringify(
        diagnostic
      )
    );

  }

  for (
    const issue
    of dynamicResult.issues || []
  ) {

    console.log(
      '  [JIRA][N3]',
      issue.key || '',
      '|',
      issue.fields?.summary || '',
      '| status =',
      issue.fields?.status?.name || '',
      '| type =',
      issue.fields?.issuetype?.name || ''
    );

  }

  // ==========================================================
  // Fallback diagnostic.
  //
  // On ne l'utilise que si le panneau GreenHopper
  // ne retourne réellement aucun ticket.
  // ==========================================================

  if (
    (
      dynamicResult.issues
      || []
    ).length > 0
  ) {

    return dynamicResult;

  }

  console.log(
    '  [JIRA][N2][FALLBACK]',
    epicKey,
    '- panneau GreenHopper vide, fallback parent'
  );

  try {

    const fallback =
      await executeJql(
        cdp,
        baseUrl,
        `parent = "${escapeJqlString(epicKey)}"`
      );

    const issues =
      fallback.issues || [];

    return {
      issues,
      names:
        fallback.names || {},
      errors:
        dynamicResult.errors || [],
      diagnostics: [
        ...(
          dynamicResult.diagnostics
          || []
        ),
        {
          source:
            'parent-fallback',
          epicKey,
          count:
            issues.length
        }
      ],
      source:
        'parent-fallback'
    };

  } catch (error) {

    return {
      issues: [],
      names: {},
      errors: [
        ...(
          dynamicResult.errors
          || []
        ),
        {
          source:
            'parent-fallback',
          epicKey,
          error:
            String(
              error?.message ||
              error
            )
        }
      ],
      diagnostics:
        dynamicResult.diagnostics
        || [],
      source:
        'none'
    };

  }

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
