from __future__ import annotations

import json
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
JSON_LEGACY = ROOT / "rapport_gil_v6_data.json"
JSON_TEMPLATE = ROOT / "rapport_gil_v6_w28_data.json"


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

    # Supprimer toutes les barres actions existantes pour éviter les doublons.
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

    if "<meta charset" not in html.lower():
        html = html.replace("<head>", '<head>\n<meta charset="utf-8">', 1)

    return html


def extract_fallback_payload(html: str) -> dict:
    match = re.search(
        r"const fallbackData\s*=\s*([\s\S]*?);\s*let currentData\s*=\s*fallbackData\s*;",
        html,
    )
    if not match:
        stop("Impossible de trouver fallbackData dans dashboard_gil_sprint21.html")

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        stop(f"fallbackData JSON invalide : {exc}")


def main() -> None:
    print("=== PUBLICATION JIRA -> HTML LEGACY ===")

    if not JIRA_SOURCE.exists():
        stop(f"Source JIRA absente : {JIRA_SOURCE}")

    if not HTML.exists():
        stop(f"HTML legacy absent : {HTML}")

    print("[1/5] Copie JIRA vers commun/dashboard_gil_data.json")
    shutil.copy2(JIRA_SOURCE, COMMUN_SOURCE)

    print("[2/5] Génération HTML legacy")
    run([sys.executable, "generer_dashboard_gil_classique.py"], ROOT)

    print("[3/5] Réinjection boutons + JS")
    html = read_text(HTML)
    html = inject_buttons_and_js(html)
    write_text(HTML, html)

    print("[4/5] Création du JSON legacy depuis fallbackData")
    payload = extract_fallback_payload(html)
    JSON_LEGACY.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    JSON_TEMPLATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[5/5] Résumé publication")
    print("sprintCourant   :", payload.get("sprintCourant"))
    print("semaineCourante :", payload.get("semaineCourante"))
    print("kpis            :", payload.get("kpis"))
    print("comparaison     :", len(payload.get("comparaisonSprints") or []))

    print()
    print("[OK] Publication JIRA stabilisée.")
    print("HTML :", HTML)
    print("JSON :", JSON_LEGACY)


if __name__ == "__main__":
    main()
