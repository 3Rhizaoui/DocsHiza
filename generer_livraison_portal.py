from pathlib import Path
from datetime import datetime
import shutil
import re
import json
import zipfile
import hashlib

ROOT = Path(__file__).resolve().parent

SOURCE = ROOT / "portal"

OUT_ROOT = ROOT / "livraisons"

PAYLOAD_BASE = (
    SOURCE
    / "commun"
    / "data"
    / "payload_base.json"
)


# ============================================================
# V5 - PUBLICATION REELLE DU PORTAL
# ============================================================

GIL_PROJECT = (
    SOURCE
    / "commun"
    / "data"
    / "gil_project.json"
)

GIL_HOME = (
    SOURCE
    / "commun"
    / "data"
    / "gil_home.json"
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
    GIL_PROJECT,
    GIL_HOME,
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

payload_meta = json.loads(
    GIL_PROJECT.read_text(
        encoding="utf-8",
        errors="replace"
    )
)

sprint_name = str(
    payload_meta.get(
        "sprintCourant",
        "Sprint_Inconnu"
    )
).strip()

sprint_slug = re.sub(
    r"[^A-Za-z0-9_-]+",
    "_",
    sprint_name
).strip("_")

delivery_name = (
    "GIL_Portal_"
    + sprint_slug
    + "_"
    + timestamp
)

destination = (
    OUT_ROOT
    / delivery_name
)


print("=" * 72)
print("GENERATION LIVRAISON PORTAL GIL - V5 SHAREPOINT")
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

gil_project = json.loads(
    GIL_PROJECT.read_text(
        encoding="utf-8",
        errors="replace"
    )
)

gil_home = json.loads(
    GIL_HOME.read_text(
        encoding="utf-8",
        errors="replace"
    )
)

# Compatibilité avec le code V4 :
# toutes les fonctions utilisant payload_base utilisent
# désormais la publication réelle.
payload_base = gil_project

payload_standalone = json.loads(
    PAYLOAD_STANDALONE.read_text(
        encoding="utf-8",
        errors="replace"
    )
)


gil_project_js = json.dumps(
    gil_project,
    ensure_ascii=False,
    separators=(",", ":")
)

gil_home_js = json.dumps(
    gil_home,
    ensure_ascii=False,
    separators=(",", ":")
)

payload_base_js = gil_project_js

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


    # ========================================================
    # V5 - SNAPSHOT REEL REPORTING
    # ========================================================

    fallback_pattern = re.compile(
        r"const\s+fallbackData\s*=\s*\{.*?\};"
        r"\s*(?=let\s+currentData\s*=)",
        re.S
    )

    fallback_value = (
        "const fallbackData = "
        + gil_project_js
        + ";\n\n    "
    )

    text, fallback_count = (
        fallback_pattern.subn(
            fallback_value,
            text,
            count=1
        )
    )

    if fallback_count != 1:
        raise RuntimeError(
            "fallbackData réel non injecté : "
            + str(path)
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
# 3.1 HOME - SNAPSHOT REEL gil_home.json
# ============================================================

home_page = (
    destination
    / "index.html"
)

if not home_page.exists():
    raise RuntimeError(
        "Home Portal absente"
    )

home_text = home_page.read_text(
    encoding="utf-8",
    errors="replace"
)

home_script = (
    """
<script id="GIL_SHAREPOINT_HOME_V5">
(function () {

  const data =
"""
    + gil_home_js
    + """;

  window.__GIL_HOME_DATA__ =
    data;

  function setText(id, value) {

    const el =
      document.getElementById(id);

    if (!el) {
      return;
    }

    if (
      value === undefined
      || value === null
    ) {
      return;
    }

    el.textContent =
      String(value);
  }


  const arrimage =
    data.arrimage
    || {};

  setText(
    "homeTotalFlux",
    arrimage.total
  );

  setText(
    "homeDelivered",
    arrimage.delivered
  );

  setText(
    "homeDeliveredPct",
    arrimage.deliveredPct != null
      ? String(arrimage.deliveredPct) + "%"
      : null
  );

  setText(
    "homeProgress",
    arrimage.inProgress
  );

  setText(
    "homeProgressPct",
    arrimage.inProgressPct != null
      ? String(arrimage.inProgressPct) + "%"
      : null
  );

  if (data.generatedAt) {

    setText(
      "gilHeaderUpdated",
      data.generatedAt
    );
  }

})();
</script>
"""
)

if "GIL_SHAREPOINT_HOME_V5" not in home_text:

    if "</body>" not in home_text:
        raise RuntimeError(
            "balise </body> Home introuvable"
        )

    home_text = home_text.replace(
        "</body>",
        home_script
        + "\n</body>",
        1
    )

home_page.write_text(
    home_text,
    encoding="utf-8"
)

print(
    "Home snapshot réel     => OK"
)


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
# 6.1 NETTOYAGE FINAL SHAREPOINT
# ============================================================

technical_files = [
    destination / "Lancer_Portal.cmd",
    destination / "serveur_portal.py",
]

for technical_file in technical_files:

    if technical_file.exists():

        technical_file.unlink()

        print(
            "supprimé livraison     =>",
            technical_file.name
        )


technical_dirs = [
    destination / "logs",
]

for technical_dir in technical_dirs:

    if technical_dir.exists():

        shutil.rmtree(
            technical_dir
        )

        print(
            "supprimé livraison     =>",
            technical_dir.name + "/"
        )


# ------------------------------------------------------------
# Supprimer les fichiers uniquement utiles à Git.
# ------------------------------------------------------------

for pattern in (
    ".gitignore",
    ".gitkeep",
):

    for file in list(
        destination.rglob(pattern)
    ):

        if file.is_file():

            file.unlink()


print(
    "fichiers Git internes  => supprimés"
)


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

    "LIVRAISON PORTAL GIL - V5 SHAREPOINT",

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

    "gil_project.json        : publication réelle injectée",

    "gil_home.json           : publication réelle injectée",
    "payload_standalone.json : publication réelle injectée",

    "",

    "REPORTING",

    "-" * 70,

    "Reporting général : snapshot gil_project réel",

    "Reporting sprint  : snapshot gil_project réel",

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
# 11. MANIFESTE
# ============================================================

manifest_files = []

for file in destination.rglob("*"):

    if not file.is_file():
        continue

    rel = file.relative_to(
        destination
    ).as_posix()

    try:
        raw = file.read_bytes()

        sha256 = hashlib.sha256(
            raw
        ).hexdigest()

        size = len(raw)

    except Exception:
        sha256 = ""
        size = 0

    manifest_files.append(
        {
            "path": rel,
            "size": size,
            "sha256": sha256,
        }
    )


manifest = {
    "application": "GIL Portal",
    "deliveryVersion": "V5",
    "generatedAt": datetime.now().isoformat(
        timespec="seconds"
    ),
    "sprint": sprint_name,
    "deliveryName": delivery_name,
    "sharePointSafe": sharepoint_ready,
    "htmlFiles": html_count,
    "jsFiles": js_count,
    "blockingDependencies": len(problems),
    "missingLinks": len(missing_links),
    "files": manifest_files,
}


manifest_path = (
    destination
    / "manifest.json"
)

manifest_path.write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print(
    "manifest.json          => OK"
)


# ============================================================
# 12. CONTROLE PAGES PRINCIPALES
# ============================================================

expected_pages = [
    "index.html",
    "cartographie/index.html",
    "reporting/general/index.html",
    "reporting/sprint/index.html",
    "qualite/standalone/index.html",
    "qualite/suivi-quotidien/index.html",
    "qualite/ateliers/index.html",
]

missing_pages = []

for rel in expected_pages:

    if not (
        destination
        / rel
    ).exists():

        missing_pages.append(
            rel
        )


if missing_pages:

    print()
    print(
        "ATTENTION - pages principales manquantes :"
    )

    for page in missing_pages:
        print(" -", page)

    sharepoint_ready = False

else:

    print(
        "pages principales     => OK"
    )



# ============================================================
# 12.1 README LIVRAISON
# ============================================================

readme = (
    destination
    / "README_LIVRAISON.txt"
)

readme_content = f"""PORTAIL GIL - LIVRAISON SHAREPOINT
============================================================

Sprint :
{sprint_name}

Livraison :
{delivery_name}

Point d'entrée :
index.html

Contenu principal :
- Accueil
- Cycle opérationnel
- Reporting général
- Reporting Sprint
- Tests Standalone
- Suivi quotidien
- Ateliers

Mode de fonctionnement :
- portail statique et autoporteur
- aucun serveur Python requis
- aucun appel JIRA
- aucun appel Octane
- aucun fetch réseau
- aucune authentification SSO requise

Pour consulter le portail :
ouvrir index.html

Généré le :
{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
"""

readme.write_text(
    readme_content,
    encoding="utf-8"
)

print(
    "README_LIVRAISON.txt   => OK"
)


# ============================================================
# 13. DOSSIER latest
# ============================================================

latest_dir = (
    OUT_ROOT
    / "latest"
)

if latest_dir.exists():

    shutil.rmtree(
        latest_dir
    )


shutil.copytree(
    destination,
    latest_dir
)

print(
    "livraisons/latest      => OK"
)


# ============================================================
# 14. ZIP latest
# ============================================================

latest_zip = (
    OUT_ROOT
    / "GIL_Portal_latest.zip"
)

if latest_zip.exists():

    latest_zip.unlink()


with zipfile.ZipFile(
    latest_zip,
    "w",
    compression=zipfile.ZIP_DEFLATED,
) as archive:

    for file in latest_dir.rglob("*"):

        if file.is_file():

            archive.write(
                file,
                Path("GIL_Portal_latest")
                / file.relative_to(
                    latest_dir
                )
            )


print(
    "GIL_Portal_latest.zip  => OK"
)



# ============================================================
# 15. ZIP METIER STABLE
# ============================================================

business_zip = (
    OUT_ROOT
    / (
        "GIL_Portal_"
        + sprint_slug
        + ".zip"
    )
)

if business_zip.exists():

    business_zip.unlink()


with zipfile.ZipFile(
    business_zip,
    "w",
    compression=zipfile.ZIP_DEFLATED,
) as archive:

    for file in destination.rglob("*"):

        if file.is_file():

            archive.write(
                file,
                Path(
                    "GIL_Portal_"
                    + sprint_slug
                )
                / file.relative_to(
                    destination
                )
            )


print(
    "ZIP métier             =>",
    business_zip.name
)


# ============================================================
# RESULTAT
# ============================================================

print()
print("=" * 72)
print("RESULTAT V5")
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

