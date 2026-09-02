const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const readline = require('readline');

const ROOT = __dirname;

const DATA_DIR = path.resolve(
  ROOT,
  '../../../../../data/standalone/octane'
);

const QUALIFICATIONS_OUT = path.join(
  DATA_DIR,
  'qualifications_brut.json'
);

const CONFIG_FILE = path.join(
  ROOT,
  'octane_config_standalone.json'
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

  const baseUrl = cleanBaseUrl(
    config.octane_base_url
  );

  const sharedSpace = String(
    config.shared_space || ''
  ).trim();

  const workspace = String(
    config.workspace || ''
  ).trim();

  if (!baseUrl) {
    throw new Error(
      'octane_base_url absent'
    );
  }

  if (!sharedSpace) {
    throw new Error(
      'shared_space absent'
    );
  }

  if (!workspace) {
    throw new Error(
      'workspace absent'
    );
  }

  return {
    baseUrl,
    sharedSpace,
    workspace
  };

}


function browserPath() {

  const candidates = [
    process.env.OCTANE_CHROME,
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


async function attachToAuthenticatedOctane(
  baseUrl
) {

  const expectedOrigin =
    new URL(baseUrl).origin;

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
      'Aucun onglet Octane authentifié disponible.'
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

    const detail =
      result.exceptionDetails
        .exception
        ?.description ||
      result.exceptionDetails.text;

    throw new Error(
      detail ||
      'Erreur JavaScript Octane'
    );
  }

  return result.result?.value;
}


async function diagnosticApi(
  cdp,
  config
) {

  const apiBase =
    `/api/shared_spaces/`
    + `${config.sharedSpace}`
    + `/workspaces/`
    + `${config.workspace}`;

  const expression = `
    (async () => {

      const urls = [
        ${JSON.stringify(
          `/api/shared_spaces/${config.sharedSpace}/workspaces/${config.workspace}`
        )},
        ${JSON.stringify(
          `/api/shared_spaces/${config.sharedSpace}/workspaces/${config.workspace}/features?limit=1`
        )}
      ];

      const results = [];

      for (const url of urls) {

        try {

          const response =
            await fetch(
              url,
              {
                credentials: 'include',
                headers: {
                  'Accept':
                    'application/json'
                }
              }
            );

          const body =
            await response.text();

          results.push({
            url,
            status:
              response.status,
            contentType:
              response.headers.get(
                'content-type'
              ),
            bodyPreview:
              body.slice(0, 1000)
          });

        } catch (error) {

          results.push({
            url,
            status: 0,
            error:
              String(
                error?.message ||
                error
              )
          });
        }
      }

      return {
        apiBase:
          ${JSON.stringify(apiBase)},
        results
      };

    })()
  `;

  return await executeInOctane(
    cdp,
    expression
  );
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

      const text = await response.text();

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
        contentType:
          response.headers.get(
            'content-type'
          ),
        body
      };

    })()
  `;

  const result =
    await executeInOctane(
      cdp,
      expression
    );

  if (!result?.ok) {

    throw new Error(
      `Octane HTTP ${result?.status} sur ${url}`
    );
  }

  return result.body;
}



async function probeOctaneJson(
  cdp,
  url
) {

  try {

    const body =
      await fetchOctaneJson(
        cdp,
        url
      );

    return {
      ok: true,
      url,
      body
    };

  } catch (error) {

    return {
      ok: false,
      url,
      error:
        String(
          error?.message ||
          error
        )
    };

  }
}


function octaneApiBase(
  config
) {

  return (
    `/api/shared_spaces/`
    + `${config.sharedSpace}`
    + `/workspaces/`
    + `${config.workspace}`
  );
}


async function extractReferenceSample(
  cdp,
  config
) {

  const apiBase =
    `/api/shared_spaces/`
    + `${config.sharedSpace}`
    + `/workspaces/`
    + `${config.workspace}`;

  const probes = {

    metadata:
      `${apiBase}/metadata/entity_types`,

    feature:
      `${apiBase}/features/770019`,

    testSuite:
      `${apiBase}/test_suites/1118086`,

    suiteRun:
      `${apiBase}/suite_runs/901502`,

    testRun:
      `${apiBase}/runs/901503`
  };

  const result = {};

  for (
    const [name, url]
    of Object.entries(probes)
  ) {

    try {

      result[name] =
        await fetchOctaneJson(
          cdp,
          url
        );

      console.log(
        "[OCTANE]",
        name,
        "OK"
      );

    } catch (error) {

      result[name] = {
        error:
          String(
            error?.message ||
            error
          )
      };

      console.log(
        "[OCTANE]",
        name,
        "KO",
        result[name].error
      );
    }
  }

  return {
    schemaVersion: 1,
    source: {
      type: "OCTANE_REFERENCE_PROBE",
      sharedSpace:
        config.sharedSpace,
      workspace:
        config.workspace
    },
    ids: {
      capability: "770019",
      testSuite: "1118086",
      suiteRun: "901502",
      testRun: "901503"
    },
    probes: result
  };
}


async function discoverOctaneModel(
  cdp,
  config
) {

  const apiBase =
    octaneApiBase(
      config
    );

  /*
   * IMPORTANT :
   *
   * Cette phase reste volontairement générique.
   * Les réponses BNP permettront ensuite de figer :
   *
   * - les vrais champs Release
   * - les vrais champs Environment
   * - les relations Feature -> Test Suite
   * - Test Suite -> Suite Run
   * - Suite Run -> Runs
   * - pièces jointes / preuves
   */

  const endpoints = {

    entityTypes:
      `${apiBase}/metadata/entity_types`,

    features:
      `${apiBase}/features?limit=50`,

    testSuites:
      `${apiBase}/test_suites?limit=50`,

    suiteRuns:
      `${apiBase}/suite_runs?limit=50`,

    runs:
      `${apiBase}/runs?limit=50`
  };

  const result = {};

  for (
    const [name, url]
    of Object.entries(endpoints)
  ) {

    console.log(
      '[OCTANE DISCOVERY]',
      name,
      '...'
    );

    const probe =
      await probeOctaneJson(
        cdp,
        url
      );

    result[name] =
      probe;

    console.log(
      '[OCTANE DISCOVERY]',
      name,
      probe.ok
        ? 'OK'
        : 'KO'
    );

  }

  return {
    schemaVersion: 1,

    generatedAt:
      new Date().toISOString(),

    source: {
      type:
        'OCTANE_DISCOVERY',
      sharedSpace:
        config.sharedSpace,
      workspace:
        config.workspace
    },

    endpoints:
      result
  };
}



function safeEntityBody(
  probe
) {

  if (
    !probe
    || probe.error
  ) {
    return {};
  }

  if (
    probe.body
    && typeof probe.body === 'object'
  ) {
    return probe.body;
  }

  return (
    typeof probe === 'object'
      ? probe
      : {}
  );
}


function firstEntity(
  body
) {

  if (!body) {
    return {};
  }

  if (
    Array.isArray(body.data)
    && body.data.length
  ) {
    return body.data[0] || {};
  }

  if (
    Array.isArray(body.entities)
    && body.entities.length
  ) {
    return body.entities[0] || {};
  }

  return body;
}


function entityText(
  entity,
  ...keys
) {

  for (const key of keys) {

    const value =
      entity?.[key];

    if (
      value === null
      || value === undefined
      || value === ''
    ) {
      continue;
    }

    if (
      typeof value === 'object'
    ) {

      if (value.name) {
        return String(value.name).trim();
      }

      if (value.value) {
        return String(value.value).trim();
      }

      continue;
    }

    return String(value).trim();
  }

  return '';
}


function buildReferenceQualification(
  reference
) {

  const probes =
    reference?.probes || {};

  const feature =
    firstEntity(
      safeEntityBody(
        probes.feature
      )
    );

  const testSuite =
    firstEntity(
      safeEntityBody(
        probes.testSuite
      )
    );

  const suiteRun =
    firstEntity(
      safeEntityBody(
        probes.suiteRun
      )
    );

  const testRun =
    firstEntity(
      safeEntityBody(
        probes.testRun
      )
    );

  const featureName =
    entityText(
      feature,
      'name'
    )
    || 'GIL - Exchange layer';

  const capability =
    featureName
      .replace(
        /^GIL\s*-\s*/i,
        ''
      )
      .trim();

  const release =
    entityText(
      testRun,
      'release',
      'release_name'
    )
    || entityText(
      suiteRun,
      'release',
      'release_name'
    );

  const environment =
    (
      entityText(
        testRun,
        'environment',
        'environnement'
      )
      || entityText(
        suiteRun,
        'environment',
        'environnement'
      )
    ).toUpperCase();

  const executionStatus =
    entityText(
      testRun,
      'status',
      'run_status'
    );

  const executionDate =
    entityText(
      testRun,
      'execution_date',
      'executionDate',
      'started',
      'start_time',
      'last_modified'
    );

  const qualification = {
    capability,

    octaneFeature: {
      id:
        entityText(
          feature,
          'id'
        )
        || '770019',
      nom:
        featureName
    },

    release,

    environnement:
      environment,

    testSuite: {
      id:
        entityText(
          testSuite,
          'id'
        )
        || '1118086',

      nom:
        entityText(
          testSuite,
          'name'
        )
        || 'TS-GIL - Exchange layer',

      testsPlanifies: 0
    },

    suiteRun: {
      id:
        entityText(
          suiteRun,
          'id'
        )
        || '901502',

      nom:
        entityText(
          suiteRun,
          'name'
        )
        || 'TS-GIL - Exchange layer'
    },

    executions: []
  };

  if (
    Object.keys(testRun).length
  ) {

    qualification.executions.push({
      id:
        entityText(
          testRun,
          'id'
        )
        || '901503',

      nom:
        entityText(
          testRun,
          'name'
        ),

      statut:
        executionStatus,

      dateExecution:
        executionDate,

      preuves: []
    });
  }

  return qualification;
}


function buildQualificationsPayload(
  config,
  reference
) {

  return {
    schemaVersion: 1,

    generatedAt:
      new Date().toISOString(),

    source: {
      type: 'OCTANE SSO',
      sharedSpace:
        config.sharedSpace,
      workspace:
        config.workspace
    },

    qualifications: [
      buildReferenceQualification(
        reference
      )
    ]
  };
}


async function main() {

  const config =
    readConfiguration();

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
    'GIL STANDALONE - EXTRACTION OCTANE SSO'
  );

  console.log(
    '='.repeat(70)
  );

  console.log(
    'Workspace :',
    config.sharedSpace,
    '/',
    config.workspace
  );

  console.log();
  console.log(
    'Ouverture Octane SSO...'
  );

  const browser =
    cp.spawn(
      chrome,
      [
        `--remote-debugging-port=${PORT}`,
        `--user-data-dir=${PROFILE}`,
        `${config.baseUrl}/ui/?p=${config.sharedSpace}/${config.workspace}`
      ],
      {
        detached: true,
        stdio: 'ignore'
      }
    );

  browser.unref();

  await ask(
    '\nConnecte-toi à Octane si nécessaire puis appuie sur Entrée... '
  );

  const cdp =
    await attachToAuthenticatedOctane(
      config.baseUrl
    );

  try {

    console.log();
    console.log(
      'Extraction de référence Octane...'
    );

    const result =
      await extractReferenceSample(
        cdp,
        config
      );

    console.log();
    console.log(
      'Découverte du modèle Octane...'
    );

    const discovery =
      await discoverOctaneModel(
        cdp,
        config
      );

    const target = path.join(
      DATA_DIR,
      'octane_reference_probe.json'
    );

    fs.mkdirSync(
      path.dirname(target),
      {
        recursive: true
      }
    );

    fs.writeFileSync(
      target,
      JSON.stringify(
        result,
        null,
        2
      ),
      'utf8'
    );

    const discoveryTarget =
      path.join(
        DATA_DIR,
        'octane_discovery.json'
      );

    fs.writeFileSync(
      discoveryTarget,
      JSON.stringify(
        discovery,
        null,
        2
      ),
      'utf8'
    );

    const qualificationsPayload =
      buildQualificationsPayload(
        config,
        result
      );

    fs.mkdirSync(
      DATA_DIR,
      {
        recursive: true
      }
    );

    fs.writeFileSync(
      QUALIFICATIONS_OUT,
      JSON.stringify(
        qualificationsPayload,
        null,
        2
      ),
      'utf8'
    );

    console.log();

    console.log(
      'OK - qualifications Octane brutes produites :',
      QUALIFICATIONS_OUT
    );

    console.log();
    console.log(
      'OK - diagnostic métier Octane produit :',
      target
    );

    console.log();
    console.log(
      JSON.stringify(
        result,
        null,
        2
      )
    );

  } finally {

    cdp.close();
  }
}


main()
  .catch(error => {

    console.error();
    console.error(
      '[ERREUR EXTRACTION OCTANE]'
    );

    console.error(
      error?.stack ||
      error?.message ||
      error
    );

    process.exitCode = 1;
  });
