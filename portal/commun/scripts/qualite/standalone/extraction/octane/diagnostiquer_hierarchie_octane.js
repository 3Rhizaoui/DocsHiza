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
        `${apiBase}/work_items`
        + '?fields='
        + encodeURIComponent(
          'id,name,subtype,parent,logical_name,'
          + 'workspace_id,phase,owner,author,'
          + 'has_children,shared'
        )
        + '&limit=max'
        + '&order_by=name'
        + '&query='
        + encodeURIComponent(
          '"(subtype=\'epic\')"'
        )
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
        '| name =',
        text(row.name) || '<vide>',
        '| logical_name =',
        text(row.logical_name) || '<vide>',
        '| type =',
        text(
          row.subtype
          || row.type
          || row.entity_type
        )
      );
    }


    // ========================================================
    // DETAIL DE CHAQUE EPIC
    //
    // La liste /epics ne retourne pas nécessairement
    // le libellé fonctionnel affiché dans l'interface.
    // On interroge donc chaque Epic individuellement afin
    // d'identifier le vrai champ contenant :
    //
    //   "GIL - Capabilities"
    //
    // Aucun ID n'est utilisé ici comme règle métier.
    // ========================================================

    console.log();
    console.log(
      '[OCTANE][EPIC DETAILS]'
    );

    const epicDetails = [];

    for (const row of epics) {

      const epicId =
        text(row.id);

      if (!epicId) {
        continue;
      }

      try {

        const detail =
          await fetchOctaneJson(
            cdp,
            `${apiBase}/epics/${epicId}`
          );

        epicDetails.push({
          id: epicId,
          response: detail
        });

        console.log();
        console.log(
          '[OCTANE][EPIC DETAIL]',
          epicId,
          '| status =',
          detail?.status,
          '| ok =',
          detail?.ok
        );

        console.log(
          JSON.stringify(
            detail?.body || {},
            null,
            2
          )
        );

      } catch (error) {

        epicDetails.push({
          id: epicId,
          error:
            String(
              error?.message ||
              error
            )
        });

        console.log(
          '[OCTANE][EPIC DETAIL ERROR]',
          epicId,
          '|',
          String(
            error?.message ||
            error
          )
        );
      }
    }

    diagnostic.raw.epicDetails =
      epicDetails;


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
          text(row.subtype)
            .toLowerCase()
          === 'epic'
          &&
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


    console.log();
    console.log(
      '[OCTANE][EPIC TROUVE]',
      text(epic.id),
      '|',
      text(epic.name)
    );

    diagnostic.epic = {
      id:
        text(epic.id),
      name:
        text(epic.name),
      subtype:
        text(epic.subtype),
      source:
        'work_items'
    };


    // ========================================================
    // FEATURES ENFANTS DE GIL - CAPABILITIES
    //
    // Requête reproduite à partir du Network Octane :
    //
    //   /work_items/descendants
    //   parents=<EPIC_ID>:feature
    //
    // L'ID de l'Epic est découvert dynamiquement ci-dessus.
    // ========================================================

    console.log();
    console.log(
      '[2] Recherche des Features de',
      text(epic.name)
    );

    const descendantsUrl =
      `${apiBase}/work_items/descendants`
      + '?fields='
      + 'id,parent,name,subtype,has_children,'
      + 'owner,author,path,workspace_id,'
      + 'shared_phase,entity_icon'
      + '&keep-descendants=n'
      + '&limit=max'
      + '&order_by=parent,name'
      + '&parents='
      + `${text(epic.id)}:feature`;

    const descendantsResponse =
      await fetchOctaneJson(
        cdp,
        descendantsUrl
      );

    diagnostic.raw.descendants =
      descendantsResponse;

    const descendants =
      entitiesOf(
        descendantsResponse
      );

    const capabilityFeatures =
      descendants.filter(
        row =>
          text(row.subtype)
            .toLowerCase()
          === 'feature'
      );

    diagnostic.features =
      capabilityFeatures.map(
        row => ({
          id:
            text(row.id),
          name:
            text(row.name),
          subtype:
            text(row.subtype),
          parent: {
            id:
              text(row.parent?.id),
            name:
              text(row.parent?.name),
            subtype:
              text(row.parent?.subtype)
          }
        })
      );

    console.log(
      '[OCTANE][FEATURES HTTP]',
      'status =',
      descendantsResponse?.status,
      '| ok =',
      descendantsResponse?.ok
    );

    console.log(
      '[OCTANE][FEATURES COUNT]',
      capabilityFeatures.length
    );

    for (const feature of capabilityFeatures) {

      console.log(
        '[OCTANE][FEATURE]',
        text(feature.id),
        '|',
        text(feature.name),
        '| parent =',
        text(feature.parent?.id),
        '-',
        text(feature.parent?.name)
      );
    }


    const selectedExchangeLayer =
      capabilityFeatures.find(
        row =>
          text(row.name)
            .toLowerCase()
          === 'gil - exchange layer'
      );

    if (selectedExchangeLayer) {

      diagnostic.selectedFeature = {
        id:
          text(selectedExchangeLayer.id),
        name:
          text(selectedExchangeLayer.name),
        subtype:
          text(selectedExchangeLayer.subtype)
      };

      console.log();
      console.log(
        '[OCTANE][FEATURE SELECTIONNEE]',
        text(selectedExchangeLayer.id),
        '|',
        text(selectedExchangeLayer.name)
      );

    } else {

      console.log();
      console.log(
        '[OCTANE][ATTENTION]',
        'Feature GIL - Exchange layer non trouvée'
      );
    }


    fs.mkdirSync(
      DATA_DIR,
      {
        recursive: true
      }
    );

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
      '[OCTANE][DIAGNOSTIC ECRIT]',
      OUTPUT
    );

    // ========================================================
    // NIVEAU 2 DEJA TRAITE
    //
    // Les Features ont été récupérées plus haut via :
    //
    //   /work_items/descendants
    //
    // à partir de l'Epic GIL - Capabilities découvert
    // dynamiquement avec /work_items.
    //
    // diagnostic.features et diagnostic.selectedFeature
    // contiennent donc déjà le résultat officiel.
    // ========================================================

    if (!diagnostic.selectedFeature) {

      throw new Error(
        'Feature GIL - Exchange layer introuvable '
        + 'dans les descendants de GIL - Capabilities'
      );
    }

    console.log();
    console.log(
      '[OCTANE][NIVEAU 2 VALIDE]',
      diagnostic.features.length,
      'Feature(s) trouvée(s)'
    );

    console.log(
      '[OCTANE][FEATURE DE REFERENCE]',
      diagnostic.selectedFeature.id,
      '|',
      diagnostic.selectedFeature.name
    );


    // ========================================================
    // PROCHAIN NIVEAU
    //
    // Feature sélectionnée
    //       ↓
    // onglet Tests
    //       ↓
    // Test Suite TS
    //
    // La relation réelle Feature -> Tests sera ajoutée
    // après observation Network Octane sur BNP.
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
