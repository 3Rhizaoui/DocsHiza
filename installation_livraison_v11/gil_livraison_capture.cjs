'use strict';

const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');

const hash = x =>
  crypto.createHash('sha256')
    .update(x)
    .digest('hex');

const safeJSON = x =>
  JSON.stringify(x)
    .replace(/</g, '\\u003c')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');

const sleep = ms =>
  new Promise(resolve =>
    setTimeout(resolve, ms)
  );

function loadPlaywright() {

  try {
    return require('playwright');
  }
  catch (e) {

    throw new Error(
      'Module Node playwright absent. ' +
      'Verifier avec : node -e "console.log(require.resolve(\'playwright\'))"'
    );
  }
}


function keyOf(raw, base) {

  const u =
    new URL(raw, base);

  [
    't',
    '_',
    '_gil_refresh'
  ].forEach(k =>
    u.searchParams.delete(k)
  );

  u.searchParams.sort();

  return (
    u.pathname
    +
    u.search
  );
}


function relativeHref(
  url,
  pageURL,
  baseURL
) {

  const u =
    new URL(
      url,
      pageURL
    );

  const base =
    new URL(baseURL);

  if (
    u.origin !==
    base.origin
  ) {
    return url;
  }

  if (
    !u.pathname.startsWith(
      base.pathname
    )
  ) {
    throw new Error(
      'Lien hors Portal : '
      + u.pathname
    );
  }

  const to =
    u.pathname.slice(
      base.pathname.length
    )
    || 'index.html';

  const from =
    new URL(pageURL)
      .pathname
      .slice(
        base.pathname.length
      );

  return (
    path.posix.relative(
      path.posix.dirname(from),
      to
    )
    ||
    path.posix.basename(to)
  )
  + u.search
  + u.hash;
}


function extractJSONAssignment(
  code,
  value
) {

  const hits = [
    ...code.matchAll(
      /\bconst\s+fallbackData\s*=\s*/g
    )
  ];

  if (!hits.length) {
    return {
      code,
      count: 0
    };
  }

  if (
    hits.length !== 1
  ) {
    throw new Error(
      'Plusieurs declarations fallbackData dans un script'
    );
  }

  const start =
    hits[0].index
    +
    hits[0][0].length;

  if (
    code[start] !== '{'
  ) {
    throw new Error(
      'fallbackData ne contient pas un objet JSON literal'
    );
  }

  let depth = 0;
  let quoted = false;
  let escaped = false;
  let end = -1;

  for (
    let i = start;
    i < code.length;
    i++
  ) {

    const ch =
      code[i];

    if (quoted) {

      if (escaped) {
        escaped = false;
      }
      else if (
        ch === '\\'
      ) {
        escaped = true;
      }
      else if (
        ch === '"'
      ) {
        quoted = false;
      }
    }
    else if (
      ch === '"'
    ) {
      quoted = true;
    }
    else if (
      ch === '{'
      ||
      ch === '['
    ) {
      depth++;
    }
    else if (
      ch === '}'
      ||
      ch === ']'
    ) {

      depth--;

      if (
        depth === 0
      ) {
        end = i + 1;
        break;
      }
    }
  }

  if (
    end < 0
  ) {
    throw new Error(
      'fallbackData JSON non termine'
    );
  }

  JSON.parse(
    code.slice(
      start,
      end
    )
  );

  return {
    code:
      code.slice(
        0,
        start
      )
      +
      safeJSON(value)
      +
      code.slice(end),

    count: 1
  };
}

function pageState(kind) {

  const obj = value =>
    value !== null
    &&
    typeof value === 'object'
    &&
    !Array.isArray(value);

  let data = null;

  if (
    kind === 'report'
  ) {

    try {

      if (
        typeof currentData !==
        'undefined'
      ) {
        data =
          currentData;
      }

    }
    catch (_) {}

    if (
      !obj(data)
    ) {
      data =
        window.__GIL_FINAL_PAYLOAD__;
    }
  }
  else if (
    kind === 'home'
  ) {

    data =
      window.__GIL_HOME_DATA__
      ||
      null;
  }


  const validNumber = n =>

    n !== null
    &&
    n !== undefined
    &&
    n !== ''
    &&
    Number.isFinite(
      Number(n)
    )
    &&
    Number(n) >= 0;


  const canonical =

    obj(data)
    &&
    obj(data.arrimage)
    &&
    [
      'total',
      'delivered',
      'inProgress',
      'blocked'
    ].every(
      key =>
        validNumber(
          data.arrimage[key]
        )
    );


  const reportReady =

    canonical
    &&
    obj(
      data.sprintJiraSynthese
    )
    &&
    validNumber(
      data.sprintJiraSynthese
        .totalJira
    )
    &&
    obj(
      data.sprintJiraSynthese
        .statuts
    )
    &&
    Array.isArray(
      data.sprintJiraSynthese
        .billets
    )
    &&
    Array.isArray(
      data.anomaliesArrimageDetail
    );


  const bodyText =

    document.body
      ?
        document.body
          .innerText
          .replace(
            /\s+/g,
            ' '
          )
          .trim()
      :
        '';


  return {

    data:
      obj(data)
        ?
          data
        :
          null,

    ready:
      document.readyState ===
        'complete'
      &&
      bodyText.length > 20
      &&
      (
        kind !== 'report'
        ||
        reportReady
      ),

    text:
      bodyText,

    svgCount:
      document.querySelectorAll(
        'svg'
      ).length,

    canvasCount:
      document.querySelectorAll(
        'canvas'
      ).length,

    images:
      [
        ...document.images
      ].map(
        img => ({
          alt:
            img.alt,

          src:
            img.currentSrc
            ||
            img.src,

          cls:
            img.className,

          good:
            img.complete
            &&
            img.naturalWidth > 0
        })
      )
  };
}

async function capturePage({
  browser,
  baseURL,
  relativePath,
  destinationRoot,
  kind,
  timeout
}) {

  const pageURL =
    new URL(
      relativePath,
      baseURL
    ).href;

  const output =
    path.join(
      destinationRoot,
      relativePath.replace(
        /\//g,
        path.sep
      )
    );

  const context =
    await browser.newContext({
      serviceWorkers: 'block'
    });

  const page =
    await context.newPage();

  const captured =
    new Map();


  /*
   * --------------------------------------------------------
   * CAPTURE DES REPONSES LOCALES DU PORTAL PRINCIPAL
   * --------------------------------------------------------
   *
   * On conserve les réponses du serveur 8765 nécessaires
   * à la page pendant son chargement.
   *
   * Aucun appel externe n'est embarqué.
   * --------------------------------------------------------
   */

  page.on(
    'response',
    async response => {

      try {

        const url =
          response.url();

        const parsed =
          new URL(url);

        const base =
          new URL(baseURL);

        if (
          parsed.origin !==
          base.origin
        ) {
          return;
        }

        if (
          response.status() < 200
          ||
          response.status() >= 400
        ) {
          return;
        }

        const request =
          response.request();

        if (
          request.method() !==
          'GET'
        ) {
          return;
        }

        const resourceType =
          request.resourceType();

        /*
         * Les documents HTML seront reconstruits séparément.
         */
        if (
          resourceType ===
          'document'
        ) {
          return;
        }

        const body =
          await response.body();

        captured.set(
          keyOf(
            url,
            baseURL
          ),
          {
            url,
            status:
              response.status(),

            headers:
              response.headers(),

            body
          }
        );
      }
      catch (_) {
        /*
         * Une ressource impossible à lire ne doit pas
         * interrompre toute la capture.
         */
      }
    }
  );


  const pageErrors = [];

  page.on(
    'pageerror',
    error => {

      pageErrors.push(
        String(error)
      );
    }
  );


  const consoleErrors = [];

  page.on(
    'console',
    message => {

      if (
        message.type() ===
        'error'
      ) {

        consoleErrors.push(
          message.text()
        );
      }
    }
  );


  console.log(
    '[CAPTURE]',
    relativePath,
    '<-',
    pageURL
  );


  await page.goto(
    pageURL,
    {
      waitUntil:
        'domcontentloaded',

      timeout
    }
  );


  /*
   * --------------------------------------------------------
   * ATTENDRE LES DONNEES ET LE RENDU FINAL
   * --------------------------------------------------------
   */

  await page.waitForFunction(
    ({ kind }) => {

      const obj = value =>
        value !== null
        &&
        typeof value === 'object'
        &&
        !Array.isArray(value);


      let data = null;

      if (
        kind === 'report'
      ) {

        try {

          if (
            typeof currentData !==
            'undefined'
          ) {
            data =
              currentData;
          }
        }
        catch (_) {}


        if (
          !obj(data)
        ) {
          data =
            window.__GIL_FINAL_PAYLOAD__;
        }
      }


      if (
        kind === 'home'
      ) {

        data =
          window.__GIL_HOME_DATA__
          ||
          null;
      }


      if (
        kind === 'report'
      ) {

        return (
          document.readyState !==
            'loading'
          &&
          obj(data)
          &&
          obj(data.arrimage)
          &&
          obj(
            data.sprintJiraSynthese
          )
          &&
          Array.isArray(
            data.anomaliesArrimageDetail
          )
        );
      }


      return (
        document.readyState !==
          'loading'
        &&
        document.body
        &&
        document.body.innerText
          .trim()
          .length > 20
      );

    },
    {
      kind
    },
    {
      timeout
    }
  );


  /*
   * Laisser les derniers render / setTimeout du Portal
   * se terminer.
   */
  await sleep(750);


  const state =
    await page.evaluate(
      pageState,
      kind
    );


  if (
    !state.ready
  ) {
    throw new Error(
      'Page non prête : '
      + relativePath
    );
  }


  if (
    kind === 'report'
    &&
    !state.data
  ) {
    throw new Error(
      'Données Reporting absentes : '
      + relativePath
    );
  }


  /*
   * --------------------------------------------------------
   * DONNEES REPORTING
   * --------------------------------------------------------
   *
   * On remplace le fallbackData historique par les données
   * réellement utilisées par la page après chargement.
   * --------------------------------------------------------
   */

  if (
    kind === 'report'
  ) {

    const replacement =
      await page.evaluate(
        data => {

          let count = 0;

          for (
            const script
            of document.querySelectorAll(
              'script:not([src])'
            )
          ) {

            if (
              script.textContent
                .includes(
                  'const fallbackData'
                )
            ) {

              script.dataset
                .gilReplaceFallback =
                '1';

              count++;
            }
          }

          return count;

        },
        state.data
      );


    if (
      replacement < 1
    ) {
      throw new Error(
        'fallbackData introuvable dans '
        + relativePath
      );
    }
  }


  /*
   * --------------------------------------------------------
   * REECRITURE DES LIENS INTERNES
   * --------------------------------------------------------
   */

  await page.evaluate(
    ({ baseURL, pageURL }) => {

      const base =
        new URL(baseURL);

      const current =
        new URL(pageURL);


      const relative =
        value => {

          if (!value) {
            return value;
          }

          try {

            const u =
              new URL(
                value,
                current
              );

            if (
              u.origin !==
              base.origin
            ) {
              return value;
            }

            if (
              !u.pathname.startsWith(
                base.pathname
              )
            ) {
              return value;
            }

            const from =
              current.pathname
                .slice(
                  base.pathname.length
                );

            const to =
              u.pathname
                .slice(
                  base.pathname.length
                )
              ||
              'index.html';


            const fromParts =
              from.split('/');

            fromParts.pop();

            const toParts =
              to.split('/');


            while (
              fromParts.length
              &&
              toParts.length
              &&
              fromParts[0] ===
                toParts[0]
            ) {

              fromParts.shift();
              toParts.shift();
            }


            const prefix =
              '../'.repeat(
                fromParts.length
              );


            return (
              prefix
              +
              toParts.join('/')
              +
              u.search
              +
              u.hash
            );
          }
          catch (_) {
            return value;
          }
        };


      for (
        const element
        of document.querySelectorAll(
          '[href]'
        )
      ) {

        element.setAttribute(
          'href',
          relative(
            element.getAttribute(
              'href'
            )
          )
        );
      }


      for (
        const element
        of document.querySelectorAll(
          '[src]'
        )
      ) {

        const raw =
          element.getAttribute(
            'src'
          );

        if (
          raw
          &&
          !raw.startsWith(
            'data:'
          )
        ) {

          element.setAttribute(
            'src',
            relative(raw)
          );
        }
      }

    },
    {
      baseURL,
      pageURL
    }
  );


  let html =
    await page.content();


  /*
   * --------------------------------------------------------
   * INJECTION DU PAYLOAD FINAL DANS fallbackData
   * --------------------------------------------------------
   */

  if (
    kind === 'report'
  ) {

    const marker =
      /<script([^>]*)data-gil-replace-fallback="1"([^>]*)>([\s\S]*?)<\/script>/i;

    const match =
      html.match(marker);

    if (!match) {
      throw new Error(
        'Script fallback marqué introuvable : '
        + relativePath
      );
    }

    const result =
      extractJSONAssignment(
        match[3],
        state.data
      );


    if (
      result.count !== 1
    ) {
      throw new Error(
        'Injection fallbackData impossible : '
        + relativePath
      );
    }


    html =
      html.replace(
        marker,
        '<script'
        + match[1]
        + match[2]
        + '>'
        + result.code
        + '</script>'
      );
  }


  /*
   * --------------------------------------------------------
   * SUPPRESSION DES ATTRIBUTS TEMPORAIRES
   * --------------------------------------------------------
   */

  html =
    html.replace(
      /\sdata-gil-replace-fallback="1"/g,
      ''
    );


  /*
   * --------------------------------------------------------
   * ECRITURE DE LA PAGE CAPTUREE
   * --------------------------------------------------------
   */

  fs.mkdirSync(
    path.dirname(output),
    {
      recursive: true
    }
  );


  fs.writeFileSync(
    output,
    html,
    'utf8'
  );


  console.log(
    '[EMBARQUE]',
    relativePath,
    '| data:',
    state.data
      ?
        hash(
          safeJSON(
            state.data
          )
        ).slice(0, 12)
      :
        '-',
    '| ressources:',
    captured.size
  );


  await context.close();


  return {
    relativePath,
    kind,
    dataHash:
      state.data
        ?
          hash(
            safeJSON(
              state.data
            )
          )
        :
          null,

    resources:
      captured.size,

    pageErrors,
    consoleErrors
  };
}

async function main() {

  const args =
    process.argv.slice(2);


  const value = (
    name,
    fallback = null
  ) => {

    const index =
      args.indexOf(name);

    if (
      index < 0
    ) {
      return fallback;
    }

    return (
      args[index + 1]
      ??
      fallback
    );
  };


  const baseURL =
    value(
      '--base-url',
      'http://127.0.0.1:8765/'
    );


  const destinationRoot =
    value(
      '--destination'
    );


  const browserChannel =
    value(
      '--browser-channel'
    );


  const timeout =
    Number(
      value(
        '--timeout',
        '60000'
      )
    );


  if (
    !destinationRoot
  ) {
    throw new Error(
      '--destination obligatoire'
    );
  }


  const {
    chromium
  } =
    loadPlaywright();


  const launchOptions = {
    headless: true
  };


  if (
    browserChannel
  ) {

    if (
      browserChannel.toLowerCase() ===
      'msedge-bnp'
    ) {

      launchOptions.executablePath =
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

    }
    else {

      launchOptions.channel =
        browserChannel;
    }
  }


  const browser =
    await chromium.launch(
      launchOptions
    );


  const pages = [

    {
      path:
        'index.html',

      kind:
        'home'
    },

    {
      path:
        'cartographie/index.html',

      kind:
        'generic'
    },

    {
      path:
        'reporting/general/index.html',

      kind:
        'report'
    },

    {
      path:
        'reporting/sprint/index.html',

      kind:
        'report'
    },

    {
      path:
        'qualite/standalone/index.html',

      kind:
        'generic'
    },

    {
      path:
        'qualite/suivi-quotidien/index.html',

      kind:
        'generic'
    },

    {
      path:
        'qualite/ateliers/index.html',

      kind:
        'generic'
    }
  ];


  const results = [];


  try {

    for (
      const item
      of pages
    ) {

      const result =
        await capturePage({
          browser,
          baseURL,
          relativePath:
            item.path,
          destinationRoot,
          kind:
            item.kind,
          timeout
        });


      results.push(
        result
      );
    }

  }
  finally {

    await browser.close();
  }


  const reportPages =
    results.filter(
      item =>
        item.kind ===
        'report'
    );


  if (
    reportPages.some(
      item =>
        !item.dataHash
    )
  ) {

    throw new Error(
      'Capture Reporting incomplete'
    );
  }


  /*
   * Les deux pages Reporting doivent provenir de la même
   * publication complète.
   *
   * Elles ne sont pas obligées d'avoir exactement le même DOM,
   * mais elles doivent disposer d'un payload.
   */
  console.log('');
  console.log(
    '[OK] Capture Portal principal terminee'
  );


  console.log(
    JSON.stringify(
      results,
      null,
      2
    )
  );
}


main()
  .catch(error => {

    console.error(
      '[ERREUR CAPTURE V11]',
      error
      &&
      error.stack
        ?
          error.stack
        :
          String(error)
    );

    process.exitCode = 1;
  });
