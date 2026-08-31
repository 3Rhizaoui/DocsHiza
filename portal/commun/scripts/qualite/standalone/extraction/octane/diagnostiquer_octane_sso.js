const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const readline = require('readline');

const ROOT = __dirname;

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
    'GIL STANDALONE - DIAGNOSTIC OCTANE SSO'
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
      'Diagnostic API Octane...'
    );

    const result =
      await diagnosticApi(
        cdp,
        config
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
      '[ERREUR DIAGNOSTIC OCTANE]'
    );

    console.error(
      error?.stack ||
      error?.message ||
      error
    );

    process.exitCode = 1;
  });
