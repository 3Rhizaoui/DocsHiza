from pathlib import Path
from datetime import datetime
import shutil
import re
import json
import zipfile

ROOT = Path(__file__).resolve().parent

SOURCE = ROOT / "portal"

OUT_ROOT = ROOT / "livraisons"

PAYLOAD_BASE = (
    SOURCE
    / "commun"
    / "data"
    / "payload_base.json"
)

PAYLOAD_STANDALONE = (
    SOURCE
    / "commun"
    / "data"
    / "standalone"
    / "payload_standalone.json"
)


# ============================================================
# CONTROLES SOURCE
# ============================================================

required = [
    SOURCE,
    PAYLOAD_BASE,
    PAYLOAD_STANDALONE,
]

for path in required:

    if not path.exists():

        raise SystemExit(
            "ERREUR : fichier/dossier introuvable : "
            + str(path)
        )


# ============================================================
# DESTINATION
# ============================================================

timestamp = datetime.now().strftime(
    "%Y-%m-%d_%H%M%S"
)

delivery_name = (
    "GIL_Portal_"
    + timestamp
)

destination = (
    OUT_ROOT
    / delivery_name
)


print("=" * 72)
print("GENERATION LIVRAISON PORTAL GIL - V3 SHAREPOINT")
print("=" * 72)

print("Source      :", SOURCE)
print("Destination :", destination)


OUT_ROOT.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# 1. COPIE MINIMALE
# ============================================================

def ignore_delivery_files(directory, names):

    ignored = set()

    current = Path(directory)

    for name in names:

        lower = name.lower()

        # ----------------------------------------------
        # Scripts DEV / extraction
        # ----------------------------------------------

        if (
            name == "scripts"
            and current.name == "commun"
        ):
            ignored.add(name)
            continue


        # ----------------------------------------------
        # Tests
        # ----------------------------------------------

        if (
            name == "tests"
            and current == SOURCE
        ):
            ignored.add(name)
            continue


        # ----------------------------------------------
        # Backups / caches / profils SSO
        # ----------------------------------------------

        if (
            name == ".v11_backup_before_normalisation"
            or name == "__pycache__"
            or lower.startswith(".jira_sso_profile")
            or lower.startswith(".octane_sso_profile")
            or lower.endswith(".pyc")
            or lower.endswith(".log")
            or ".bak" in lower
            or ".before" in lower
        ):

            ignored.add(name)

    return ignored


shutil.copytree(
    SOURCE,
    destination,
    ignore=ignore_delivery_files,
)

print("copie portail minimale => OK")


# ============================================================
# 2. CHARGEMENT DES SNAPSHOTS
# ============================================================

payload_base = json.loads(
    PAYLOAD_BASE.read_text(
        encoding="utf-8",
        errors="replace"
    )
)

payload_standalone = json.loads(
    PAYLOAD_STANDALONE.read_text(
        encoding="utf-8",
        errors="replace"
    )
)


payload_base_js = json.dumps(
    payload_base,
    ensure_ascii=False,
    separators=(",", ":")
)

payload_standalone_js = json.dumps(
    payload_standalone,
    ensure_ascii=False,
    separators=(",", ":")
)


print(
    "payload_base chargé    =>",
    len(payload_base_js),
    "car."
)

print(
    "payload standalone     =>",
    len(payload_standalone_js),
    "car."
)


# ============================================================
# 3. REPORTING :
#    UTILISER fallbackData
# ============================================================

report_pages = [

    destination
    / "reporting"
    / "general"
    / "index.html",

    destination
    / "reporting"
    / "sprint"
    / "index.html",

]


def patch_reporting(path):

    if not path.exists():

        raise RuntimeError(
            "Reporting absent : "
            + str(path)
        )


    text = path.read_text(
        encoding="utf-8",
        errors="replace"
    )


    # --------------------------------------------------------
    # A. loadData() :
    # supprimer lecture gil_project.json
    # --------------------------------------------------------

    load_pattern = re.compile(
        r'''
        async\s+function\s+loadData\s*
        \(\s*\)\s*
        \{
        .*?
        (?=
            \s*
            currentData\s*=\s*data\s*;
        )
        ''',
        re.S | re.X
    )


    replacement = '''async function loadData(){

      /*
       * SHAREPOINT DELIVERY V3
       *
       * Toutes les données nécessaires sont déjà présentes
       * dans fallbackData.
       */

      let data =
        fallbackData;

'''


    text, count = load_pattern.subn(
        replacement,
        text,
        count=1
    )


    if count != 1:

        raise RuntimeError(
            "loadData non patché : "
            + str(path)
        )


    # --------------------------------------------------------
    # B. runLocalAction()
    #
    # Cette fonction dépend du serveur Python local.
    # Elle n'est pas disponible dans SharePoint.
    # --------------------------------------------------------

    action_pattern = re.compile(
        r'''
        async\s+function\s+runLocalAction
        \s*
        \(
            [^)]*
        \)
        \s*
        \{
        .*?
        \n
        \}
        ''',
        re.S | re.X
    )


    action_replacement = '''function runLocalAction(action){

  /*
   * SHAREPOINT DELIVERY V3
   *
   * Les actions de génération locale sont volontairement
   * désactivées dans une livraison publiée.
   */

  alert(
    "Cette action est disponible uniquement "
    + "dans l'application GIL locale."
  );

}
'''


    text, action_count = (
        action_pattern.subn(
            action_replacement,
            text,
            count=1
        )
    )


    path.write_text(
        text,
        encoding="utf-8"
    )


    print(
        "reporting SharePoint  =>",
        path.relative_to(destination),
        "| loadData:",
        count,
        "| action:",
        action_count
    )


for page in report_pages:
    patch_reporting(page)


# ============================================================
# 4. STANDALONE :
#    REMPLACER FETCH PAR SNAPSHOT
# ============================================================

standalone_js = (
    destination
    / "qualite"
    / "standalone"
    / "standalone.js"
)


def patch_quality_js(
    path,
    is_suivi=False
):

    if not path.exists():

        raise RuntimeError(
            "JS qualité absent : "
            + str(path)
        )


    text = path.read_text(
        encoding="utf-8",
        errors="replace"
    )


    # ========================================================
    # DONNEES INJECTEES
    # ========================================================

    injected = f'''
/* =========================================================
   SHAREPOINT DELIVERY V3
   DONNEES EMBARQUEES
   ========================================================= */

window.__GIL_SHAREPOINT_PAYLOAD_BASE__ =
{payload_base_js};

window.__GIL_SHAREPOINT_PAYLOAD_STANDALONE__ =
{payload_standalone_js};

'''


    text = (
        injected
        + "\n"
        + text
    )


    # ========================================================
    # loadFluxData()
    # ========================================================

    start = text.find(
        "async function loadFluxData()"
    )

    if start == -1:

        raise RuntimeError(
            "loadFluxData introuvable : "
            + str(path)
        )


    end = text.find(
        "\n  function byId",
        start
    )

    if end == -1:

        raise RuntimeError(
            "fin loadFluxData introuvable : "
            + str(path)
        )


    if is_suivi:

        new_flux_loader = r'''async function loadFluxData() {

    /*
     * SHAREPOINT DELIVERY V3
     * payload_base déjà embarqué.
     */

    const data =
      window.__GIL_SHAREPOINT_PAYLOAD_BASE__
      || {};

    fluxSourceRows =
      enrichFluxRows(
        currentFluxRows(data)
      );

    initSuiviSprintBar();

    suiviRenderServiceKpis(
      fluxSourceRows
    );

    suiviRenderPerimeters(
      fluxSourceRows
    );

    initFluxFilters();

    renderFluxKpis(
      fluxSourceRows
    );

    renderFluxRows(
      fluxSourceRows
    );
  }

'''

    else:

        new_flux_loader = r'''async function loadFluxData() {

    /*
     * SHAREPOINT DELIVERY V3
     * payload_base déjà embarqué.
     */

    const data =
      window.__GIL_SHAREPOINT_PAYLOAD_BASE__
      || {};

    fluxSourceRows =
      enrichFluxRows(
        currentFluxRows(data)
      );

    initFluxFilters();

    renderFluxKpis(
      fluxSourceRows
    );

    renderFluxRows(
      fluxSourceRows
    );
  }

'''


    text = (
        text[:start]
        + new_flux_loader
        + text[end:]
    )


    # ========================================================
    # load() STANDALONE
    # ========================================================

    start = text.find(
        "async function load()"
    )

    if start == -1:

        raise RuntimeError(
            "load() introuvable : "
            + str(path)
        )


    # Le bloc suivant commence par :
    #
    # [
    #   "filterService",
    #
    # donc on prend ce marqueur.
    # ========================================================

    end = text.find(
        '\n  [\n    "filterService"',
        start
    )


    if end == -1:

        raise RuntimeError(
            "fin load() introuvable : "
            + str(path)
        )


    new_loader = r'''async function load() {

    /*
     * SHAREPOINT DELIVERY V3
     * payload Standalone déjà embarqué.
     */

    const data =
      window.__GIL_SHAREPOINT_PAYLOAD_STANDALONE__
      || {};

    sourceRows =
      Array.isArray(
        data.capabilities
      )
        ? data.capabilities
        : [];

    populateServices();
    populateVersions();

    renderKpis(
      sourceRows
    );

    renderRows(
      sourceRows
    );

    byId(
      "generatedAt"
    ).textContent =
      "Dernière génération : "
      + formatDate(
        data.generatedAt
      );
  }

'''


    text = (
        text[:start]
        + new_loader
        + text[end:]
    )


    path.write_text(
        text,
        encoding="utf-8"
    )


    print(
        "qualité autoporteuse =>",
        path.relative_to(destination)
    )


patch_quality_js(
    standalone_js,
    is_suivi=False
)


suivi_js = (
    destination
    / "qualite"
    / "suivi-quotidien"
    / "suivi-quotidien.js"
)


patch_quality_js(
    suivi_js,
    is_suivi=True
)


# ============================================================
# 5. SUPPRIMER JS TECHNIQUES NON NECESSAIRES
# ============================================================

# actions.js contient des appels vers le serveur local.
# Il ne doit pas être utilisé dans une livraison publiée.

actions_js = (
    destination
    / "commun"
    / "js"
    / "actions.js"
)

if actions_js.exists():

    actions_js.write_text(
        r'''
/*
 * SHAREPOINT DELIVERY V3
 *
 * Les actions serveur sont désactivées dans cette livraison.
 */

window.GIL_ACTIONS_DISABLED =
  true;
''',
        encoding="utf-8"
    )

    print(
        "commun/js/actions.js => neutralisé"
    )


# ------------------------------------------------------------
# data-loader.js :
# aucun chargement réseau autorisé dans la livraison.
# ------------------------------------------------------------

data_loader = (
    destination
    / "commun"
    / "js"
    / "data-loader.js"
)

if data_loader.exists():

    data_loader.write_text(
        r'''
/*
 * SHAREPOINT DELIVERY V3
 *
 * Les données sont directement embarquées dans les pages
 * métier. Aucun chargement réseau n'est effectué.
 */

window.GIL_SHAREPOINT_STATIC_DATA =
  true;
''',
        encoding="utf-8"
    )

    print(
        "commun/js/data-loader.js => neutralisé"
    )


# ------------------------------------------------------------
# logger.js :
# supprimer envoi réseau, conserver console locale.
# ------------------------------------------------------------

logger = (
    destination
    / "commun"
    / "js"
    / "logger.js"
)

if logger.exists():

    logger.write_text(
        r'''
/*
 * SHAREPOINT DELIVERY V3
 *
 * Logger local uniquement.
 * Aucun appel réseau.
 */

(function () {

  window.GILLogger = {

    log: function () {

      if (
        window.console
        && console.log
      ) {
        console.log.apply(
          console,
          arguments
        );
      }

    },

    info: function () {

      if (
        window.console
        && console.info
      ) {
        console.info.apply(
          console,
          arguments
        );
      }

    },

    warn: function () {

      if (
        window.console
        && console.warn
      ) {
        console.warn.apply(
          console,
          arguments
        );
      }

    },

    error: function () {

      if (
        window.console
        && console.error
      ) {
        console.error.apply(
          console,
          arguments
        );
      }

    }

  };

})();
''',
        encoding="utf-8"
    )

    print(
        "commun/js/logger.js => neutralisé"
    )


# ============================================================
# 6. SUPPRIMER DONNEES BRUTES INUTILES DE LA LIVRAISON
#
# Les données sont maintenant incorporées dans les JS qualité.
# ============================================================

standalone_data_dir = (
    destination
    / "commun"
    / "data"
    / "standalone"
)


# On conserve volontairement les JSON pour cette première V3
# afin de faciliter le contrôle de cohérence.
#
# Dans V4 ils pourront être supprimés du package.


# ============================================================
# 7. ANALYSE HTML + JS
# ============================================================

scan_files = []

scan_files.extend(
    destination.rglob("*.html")
)

scan_files.extend(
    destination.rglob("*.js")
)


problems = []


checks = {

    "fetch()":
        r"\bfetch\s*\(",

    "XMLHttpRequest":
        r"\bXMLHttpRequest\b",

    "localhost":
        r"\blocalhost\b",

    "127.0.0.1":
        r"127\.0\.0\.1",

    "URL HTTP externe src/href":
        r'''(?:src|href)\s*=\s*["']https?://''',

}


for file in scan_files:

    content = file.read_text(
        encoding="utf-8",
        errors="replace"
    )


    for label, regex in checks.items():

        if re.search(
            regex,
            content,
            flags=re.I
        ):

            problems.append(
                str(
                    file.relative_to(
                        destination
                    )
                )
                + " : "
                + label
            )


# ============================================================
# 8. CONTROLE DES LIENS LOCAUX
# ============================================================

missing_links = []


attr_pattern = re.compile(
    r'''(?:src|href)\s*=\s*["']([^"'#]+)["']''',
    re.I
)


for html in destination.rglob(
    "*.html"
):

    content = html.read_text(
        encoding="utf-8",
        errors="replace"
    )


    for match in attr_pattern.finditer(
        content
    ):

        value = (
            match.group(1)
            .strip()
        )


        if not value:
            continue


        # Templates JS dynamiques :
        # ${link.href}, ${settingsHref}, ...
        #
        # Ce ne sont pas des fichiers physiques.
        # ----------------------------------------

        if (
            "${" in value
            or "}" in value
        ):
            continue


        lower = value.lower()


        if (
            lower.startswith("http://")
            or lower.startswith("https://")
            or lower.startswith("mailto:")
            or lower.startswith("javascript:")
            or lower.startswith("data:")
            or lower.startswith("//")
        ):
            continue


        clean = (
            value
            .split("?", 1)[0]
            .split("#", 1)[0]
        )


        if not clean:
            continue


        target = (
            html.parent
            / clean
        ).resolve()


        if not target.exists():

            missing_links.append(
                str(
                    html.relative_to(
                        destination
                    )
                )
                + " -> "
                + value
            )


# ============================================================
# 9. RAPPORT
# ============================================================

report = (
    destination
    / "RAPPORT_LIVRAISON.txt"
)


html_count = len(
    list(
        destination.rglob(
            "*.html"
        )
    )
)

js_count = len(
    list(
        destination.rglob(
            "*.js"
        )
    )
)


lines = [

    "LIVRAISON PORTAL GIL - V3 SHAREPOINT",

    "=" * 70,

    "",

    "Generation : "
    + datetime.now().strftime(
        "%d/%m/%Y %H:%M:%S"
    ),

    "",

    f"HTML analyses : {html_count}",

    f"JS analyses   : {js_count}",

    "",

    "DONNEES EMBARQUEES",

    "-" * 70,

    "payload_base.json       : injecté",

    "payload_standalone.json : injecté",

    "",

    "REPORTING",

    "-" * 70,

    "Reporting général : fallbackData local",

    "Reporting sprint  : fallbackData local",

    "Actions serveur   : désactivées",

    "",

    "QUALITE",

    "-" * 70,

    "Tests Standalone  : données locales",

    "Suivi quotidien   : données locales",

    "",

]


if problems:

    lines += [

        "DEPENDANCES BLOQUANTES RESTANTES",

        "-" * 70,

        *problems,

        "",

    ]

else:

    lines += [

        "DEPENDANCES BLOQUANTES",

        "-" * 70,

        "Aucune dépendance réseau détectée.",

        "",

    ]


if missing_links:

    lines += [

        "LIENS LOCAUX MANQUANTS",

        "-" * 70,

        *missing_links,

        "",

    ]

else:

    lines += [

        "LIENS LOCAUX",

        "-" * 70,

        "Tous les liens locaux détectés existent.",

        "",

    ]


sharepoint_ready = (
    len(problems) == 0
    and len(missing_links) == 0
)


lines += [

    "RESULTAT",

    "-" * 70,

]


if sharepoint_ready:

    lines += [

        "CANDIDAT SHAREPOINT-SAFE",

        "",

        "La livraison ne dépend plus :",

        "- d'un serveur Python",

        "- de localhost",

        "- d'un fetch réseau",

        "- de JIRA",

        "- d'Octane",

        "- d'une authentification SSO",

    ]

else:

    lines += [

        "PAS ENCORE SHAREPOINT-SAFE",

        "",

        "Des dépendances restent à corriger.",

    ]


report.write_text(
    "\n".join(lines),
    encoding="utf-8"
)


# ============================================================
# 10. ZIP
# ============================================================

zip_path = (
    OUT_ROOT
    / (
        delivery_name
        + ".zip"
    )
)


with zipfile.ZipFile(
    zip_path,
    "w",
    compression=zipfile.ZIP_DEFLATED,
) as archive:

    for file in destination.rglob(
        "*"
    ):

        if file.is_file():

            archive.write(
                file,
                Path(delivery_name)
                / file.relative_to(
                    destination
                )
            )


# ============================================================
# RESULTAT
# ============================================================

print()
print("=" * 72)
print("RESULTAT V3")
print("=" * 72)

print(
    "HTML                   =>",
    html_count
)

print(
    "JS                     =>",
    js_count
)

print(
    "Dépendances restantes =>",
    len(problems)
)

print(
    "Liens manquants        =>",
    len(missing_links)
)

print(
    "Rapport                =>",
    report
)

print(
    "ZIP                    =>",
    zip_path
)

print()

if sharepoint_ready:

    print(
        "STATUT => CANDIDAT SHAREPOINT-SAFE"
    )

else:

    print(
        "STATUT => CONTROLE SUPPLEMENTAIRE NECESSAIRE"
    )

