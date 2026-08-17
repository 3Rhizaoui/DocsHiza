from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

JIRA_SOURCE = PROJECT / "jira" / "dashboard_gil_data.json"
COMMUN_SOURCE = ROOT / "dashboard_gil_data.json"
HTML = ROOT / "dashboard_gil_sprint21.html"
GENERATOR = ROOT / "generer_dashboard_gil_classique.py"

FETCH_LINE = "/* JIRA stable : chargement externe rapport_gil_v6_data.json désactivé ; fallbackData embarqué utilisé */"
COMMENT = "/* JIRA stable : chargement JSON externe desactive, fallbackData embarque utilise */"


def stop(msg: str) -> None:
    print("[ERREUR]", msg)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run(cmd: list[str], cwd: Path) -> None:
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr)
        stop("Commande en erreur : " + " ".join(cmd))


def disable_external_json_load(text: str) -> str:
    text = text.replace(FETCH_LINE, COMMENT)

    text = re.sub(
        r"try\s*\{\s*const\s+r\s*=\s*await\s+fetch\(\s*['\"]rapport_gil_v6_data\.json['\"]\s*,\s*\{cache\s*:\s*['\"]no-store['\"]\}\s*\)\s*;\s*if\s*\(r\.ok\)\s*data\s*=\s*await\s+r\.json\(\)\s*;\s*\}\s*catch\s*\(\s*e\s*\)\s*\{\s*\}",
        COMMENT,
        text,
        flags=re.S,
    )

    text = text.replace(
        "fetch('__disabled_rapport_gil_v6_data.json'",
        "fetch('__disabled_rapport_gil_v6_data.json'"
    )
    text = text.replace(
        'fetch("__disabled_rapport_gil_v6_data.json',
        'fetch("__disabled_rapport_gil_v6_data.json'
    )

    return text


def inject_buttons_and_js(html: str) -> str:
    buttons = """<div class="actions">
<button onclick="runLocalAction('excel')">Importer<br>Excel</button>
<button onclick="runLocalAction('confluence')">Importer<br>Confluence</button>
<button onclick="runLocalAction('jira')">Importer<br>JIRA</button>
<button onclick="runLocalAction('sync')">Synchroniser<br>les 3</button>
<button onclick="runLocalAction('archive')">Valider / Archiver<br>Sprint</button>
<button onclick="window.print()">Générer le<br>rapport PDF</button>
<button onclick="hardRefreshDashboard()">Rafraîchir</button>
</div>"""

    html = re.sub(r'<div class="actions">.*?</div>', '', html, flags=re.S)

    if "</header>" in html:
        html = html.replace("</header>", buttons + "\n</header>", 1)
    else:
        html = buttons + "\n" + html

    js = """
async function runLocalAction(action){
  try {
    const response = await fetch('http://127.0.0.1:8765/action/' + action, { method: 'POST' });
    const text = await response.text();
    alert(text);
  } catch (e) {
    alert("Serveur local indisponible. Lance Lancer_Dashboard.cmd puis réessaie.\\n\\n" + e);
  }
}

function hardRefreshDashboard(){
  window.location.href = window.location.pathname + '?t=' + Date.now();
}
"""

    if "function runLocalAction" not in html:
        html = html.replace("</script>", js + "\n</script>", 1)

    if "function hardRefreshDashboard" not in html:
        html = html.replace(
            "</script>",
            "\nfunction hardRefreshDashboard(){ window.location.href = window.location.pathname + '?t=' + Date.now(); }\n</script>",
            1,
        )

    if "<meta charset" not in html.lower():
        html = html.replace("<head>", '<head>\n<meta charset="utf-8">', 1)

    return html


def patch_generator_once() -> None:
    if not GENERATOR.exists():
        return

    text = read_text(GENERATOR)
    new_text = disable_external_json_load(text)

    if new_text != text:
        write_text(GENERATOR, new_text)
        print("[OK] generateur patche : il ne remettra plus rapport_gil_v6_data.json")


def main() -> None:
    print("=== PUBLICATION JIRA -> HTML LEGACY STABLE ===")

    if not JIRA_SOURCE.exists():
        stop(f"Source JIRA absente : {JIRA_SOURCE}")

    if not HTML.exists():
        stop(f"HTML legacy absent : {HTML}")

    patch_generator_once()

    print("[1/4] Copie JIRA vers commun/dashboard_gil_data.json")
    shutil.copy2(JIRA_SOURCE, COMMUN_SOURCE)

    print("[2/4] Generation HTML legacy")
    run([sys.executable, "generer_dashboard_gil_classique.py"], ROOT)

    print("[3/4] Stabilisation HTML")
    html = read_text(HTML)
    html = disable_external_json_load(html)
    html = inject_buttons_and_js(html)
    write_text(HTML, html)

    print("[4/4] Controle")
    html2 = read_text(HTML)

    if "fetch('rapport_gil_v6_data.json'" in html2 or 'fetch("rapport_gil_v6_data.json' in html2:
        stop("Le HTML contient encore un fetch actif vers rapport_gil_v6_data.json")

    if "function runLocalAction" not in html2:
        stop("runLocalAction absent apres publication")

    print("[OK] Publication JIRA stable.")
    print("HTML :", HTML)


if __name__ == "__main__":
    main()
