const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const readline = require('readline');

const ROOT = __dirname;

const DATA_DIR = path.resolve(
  ROOT,
  '../../../../../data/standalone/octane'
);

const CONFIG_FILE = path.join(
  ROOT,
  'octane_config_standalone.json'
);

const OUTPUT = path.join(
  DATA_DIR,
  'octane_hierarchy_diagnostic.json'
);

const PORT = 9232;

const PROFILE = path.resolve(
  ROOT,
  '.octane_sso_profile_standalone'
);

const sleep = ms =>
  new Promise(resolve => setTimeout(resolve, ms));


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


function cleanBaseUrl(value) {

  return String(value || '')
    .trim()
    .replace(/\/+$/, '');
}


function readConfiguration() {

  const config = JSON.parse(
    fs.readFileSync(
      CONFIG_FILE,
      'utf8'
    ).replace(/^\uFEFF/, '')
  );

  return {
    baseUrl:
      cleanBaseUrl(
        config.octane_base_url
      ),

    sharedSpace:
      String(
        config.shared_space || ''
      ).trim(),

    workspace:
      String(
        config.workspace || ''
      ).trim()
  };
}


function browserPath() {

  const candidates = [
    process.env.OCTANE_CHROME,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
  ].filter(Boolean);

  const found =
    candidates.find(
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

  const rl =
    readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

  return new Promise(
    resolve =>
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

      const response =
        await fetch(url);

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


class CDP {

  constructor(wsUrl) {

    this.id = 0;
    this.pending = new Map();
    this.ws = new WebSocket(wsUrl);
  }


  async open() {

    await new Promise(
      (resolve, reject) => {

        this.ws.onopen = resolve;
        this.ws.onerror = reject;
      }
    );

    this.ws.onmessage = event => {

      const message =
        JSON.parse(
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


async function attachToAuthenticatedOctane(
  baseUrl
) {

  const expectedOrigin =
    new URL(baseUrl).origin;

  const targets =
    await getJson(
      `http://127.0.0.1:${PORT}/json/list`,
      10
    );

  const pages =
    targets
      .filter(
        target =>
          target.type === 'page'
          && target.webSocketDebuggerUrl
      )
      .filter(
        target => {

          try {

            return (
              new URL(
                target.url || 'about:blank'
              ).origin === expectedOrigin
            );

          } catch (_) {
            return false;
          }
        }
      );

  if (!pages.length) {

    throw new Error(
      'Aucun onglet Octane authentifié disponible.'
    );
  }

  const target = pages[0];

  const cdp =
    new CDP(
      target.webSocketDebuggerUrl
    );

  await cdp.open();

  await cdp.send(
    'Runtime.enable'
  );

  await cdp.send(
    'Page.bringToFront'
  ).catch(() => {});

  console.log(
    'Session Octane utilisée :',
    target.url
  );

  return cdp;
}


async function executeInOctane(
  cdp,
  expression
) {

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

    throw new Error(
      result.exceptionDetails
        .exception
        ?.description
      || result.exceptionDetails.text
      || 'Erreur JavaScript Octane'
    );
  }

  return result.result?.value;
}


async function fetchOctaneJson(
  cdp,
  url
) {

  const expression = `
    (async () => {

      const response = await fetch(
        ${JSON.stringify(url)},
        {
          credentials: 'include',
          headers: {
            'Accept': 'application/json'
          }
        }
      );

      const text =
        await response.text();

      let body = null;

      try {
        body = JSON.parse(text);
      } catch (_) {
        body = {
          raw: text
        };
      }

      return {
        ok: response.ok,
        status: response.status,
        body
      };

    })()
  `;

  return await executeInOctane(
    cdp,
    expression
  );
}


function entitiesOf(response) {

  const body =
    response?.body || {};

  if (Array.isArray(body.data)) {
    return body.data;
  }

  if (Array.isArray(body.entities)) {
    return body.entities;
  }

  return [];
}


function text(value) {

  if (
    value === null
    || value === undefined
  ) {
    return '';
  }

  if (
    typeof value === 'object'
  ) {

    return String(
      value.name
      || value.value
      || value.id
      || ''
    ).trim();
  }

  return String(value).trim();
}


async function main() {

  const config =
    readConfiguration();

  const apiBase =
    `/api/shared_spaces/`
    + `${config.sharedSpace}`
    + `/workspaces/`
    + `${config.workspace}`;

  fs.mkdirSync(
    PROFILE,
    {
      recursive: true
    }
  );

  fs.mkdirSync(
    DATA_DIR,
    {
      recursive: true
    }
  );

  const chrome =
    browserPath();

  console.log();
  console.log(
    '='.repeat(72)
  );
  console.log(
    'GIL STANDALONE - DIAGNOSTIC HIERARCHIE OCTANE'
  );
  console.log(
    '='.repeat(72)
  );

  const browser =
    cp.spawn(
      chrome,
      [
        `--remote-debugging-port=${PORT}`,
        `--user-data-dir=${PROFILE}`,
        `${config.baseUrl}/ui/?p=${config.sharedSpace}/${config.workspace}#/release-quality/hierarchy/tests_in_backlog`
      ],
      {
        detached: true,
        stdio: 'ignore'
      }
    );

  browser.unref();

  await ask(
    '\nConnecte-toi à Octane puis appuie sur Entrée... '
  );

  const cdp =
    await attachToAuthenticatedOctane(
      config.baseUrl
    );

  try {

    const diagnostic = {
      generatedAt:
        new Date().toISOString(),

      epic: null,
      features: [],
      selectedFeature: null,
      tests: [],
      testSuites: [],
      suiteRuns: [],
      automatedRuns: [],
      raw: {}
    };


    // ========================================================
    // NIVEAU 1
    // BACKLOG / EPIC : GIL - Capabilities
    // ========================================================

    console.log();
    console.log(
      '[1] Recherche Epic GIL - Capabilities'
    );

    const epicsResponse =
      await fetchOctaneJson(
        cdp,
        `${apiBase}/epics?limit=200`
      );

    diagnostic.raw.epics =
      epicsResponse;

    const epics =
      entitiesOf(
        epicsResponse
      );

    console.log(
      '[OCTANE][EPICS HTTP]',
      'status =',
      epicsResponse?.status,
      '| ok =',
      epicsResponse?.ok
    );

    console.log(
      '[OCTANE][EPICS COUNT]',
      epics.length
    );

    console.log(
      '[OCTANE][EPICS BODY KEYS]',
      Object.keys(
        epicsResponse?.body || {}
      ).join(', ')
    );

    for (
      const row
      of epics.slice(0, 200)
    ) {

      console.log(
        '[OCTANE][EPIC CANDIDAT]',
        text(row.id),
        '|',
        text(row.name),
        '| type =',
        text(
          row.subtype
          || row.type
          || row.entity_type
        )
      );
    }

    /*
     * Toujours sauvegarder le diagnostic,
     * même si l'Epic recherché n'est pas trouvé.
     */
    fs.writeFileSync(
      OUTPUT,
      JSON.stringify(
        diagnostic,
        null,
        2
      ),
      'utf8'
    );

    const epic =
      epics.find(
        row =>
          text(row.name)
            .toLowerCase()
          === 'gil - capabilities'
      );

    if (!epic) {

      throw new Error(
        'Epic GIL - Capabilities introuvable '
        + '- réponse brute enregistrée dans '
        + OUTPUT
      );
    }

    diagnostic.epic = epic;

    console.log(
      '[EPIC]',
      text(epic.id),
      '|',
      text(epic.name)
    );


    // ========================================================
    // NIVEAU 2
    // FEATURES DE GIL - Capabilities
    // ========================================================

    console.log();
    console.log(
      '[2] Parcours des Features'
    );

    const featuresResponse =
      await fetchOctaneJson(
        cdp,
        `${apiBase}/features?limit=500`
      );

    diagnostic.raw.features =
      featuresResponse;

    const features =
      entitiesOf(
        featuresResponse
      );

    diagnostic.features =
      features;

    for (const feature of features) {

      console.log(
        '[FEATURE]',
        text(feature.id),
        '|',
        text(feature.name)
      );
    }


    // ========================================================
    // EXEMPLE DE REFERENCE
    // Sélection dynamique par nom, pas par ID fixe
    // ========================================================

    const selectedFeature =
      features.find(
        row =>
          text(row.name)
            .toLowerCase()
          === 'gil - exchange layer'
      );

    if (!selectedFeature) {

      throw new Error(
        'Feature GIL - Exchange layer introuvable'
      );
    }

    diagnostic.selectedFeature =
      selectedFeature;

    console.log();
    console.log(
      '[FEATURE SELECTIONNEE]',
      text(selectedFeature.id),
      '|',
      text(selectedFeature.name)
    );


    // ========================================================
    // La suite du diagnostic sera ajoutée après observation
    // de la relation réelle Feature -> Tests sur BNP.
    // ========================================================

    fs.writeFileSync(
      OUTPUT,
      JSON.stringify(
        diagnostic,
        null,
        2
      ),
      'utf8'
    );

    console.log();
    console.log(
      'OK - diagnostic écrit :',
      OUTPUT
    );

  } finally {

    cdp.close();
  }
}


main()
  .catch(error => {

    console.error();
    console.error(
      '[ERREUR DIAGNOSTIC HIERARCHIE OCTANE]'
    );

    console.error(
      error?.stack
      || error?.message
      || error
    );

    process.exitCode = 1;
  });
