from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

JIRA_SOURCE = PROJECT / "jira" / "dashboard_gil_data.json"
COMMUN_SOURCE = ROOT / "dashboard_gil_data.json"
HTML = ROOT / "dashboard_gil_sprint21.html"
GENERATOR = ROOT / "generer_dashboard_gil_classique.py"


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


def sval(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return "".join(ch if ord(ch) >= 32 or ch in "\t\n\r" else " " for ch in text).strip()


def first(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return sval(value)
    return ""


def load_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("rows") or data.get("data") or data.get("items") or data.get("records") or []
    else:
        rows = []

    if not isinstance(rows, list):
        stop("Format JIRA inattendu : dashboard_gil_data.json ne contient pas une liste")

    clean_rows = []
    for item in rows:
        if isinstance(item, dict):
            clean_rows.append(item)

    return clean_rows


def envs(row: dict) -> list[str]:
    raw = first(row, "environnement", "env", "environnements", "environment")
    if not raw:
        return ["SIT", "UAT"]

    up = raw.upper()
    out = []
    if "SIT" in up:
        out.append("SIT")
    if "UAT" in up:
        out.append("UAT")

    return out or [raw]


def is_ready(row: dict) -> bool:
    status = first(row, "etatFlux", "statut", "status", "etat", "state").lower()
    return (
        status.startswith("prêt")
        or status.startswith("pret")
        or "pret pour arrimage" in status
        or "prêt pour arrimage" in status
        or status == "done"
        or status == "livré"
        or status == "livre"
    )


def is_anomaly(row: dict) -> bool:
    typ = first(row, "type", "issuetype", "issueType").lower()
    return "anomal" in typ or typ == "bug"


def row_to_flux(row: dict) -> dict:
    domaine = first(row, "domaine", "domain", "chaine", "chaîne") or "Non renseigné"
    sous = first(row, "sousDomaine", "sous_domaine", "subDomain", "subdomain") or "Non renseigné"
    ref = first(row, "referenceFlux", "reference", "ref", "key", "cle", "clé") or first(row, "summary", "titre")
    version = first(row, "version", "fixVersion", "fixVersions")
    pattern = first(row, "pattern", "modele", "modèle") or "Réel"
    statut = first(row, "statut", "etatFlux", "status") or ("Prêt pour arrimage" if is_ready(row) else "En cours")

    return {
        "sprint": first(row, "sprint") or "Sprint 21",
        "env": envs(row),
        "environnement": " / ".join(envs(row)),
        "domaine": domaine,
        "sousDomaine": sous,
        "reference": ref,
        "referenceFlux": ref,
        "pattern": pattern,
        "version": version,
        "statut": statut,
        "etatFlux": statut,
    }


def build_payload(rows: list[dict]) -> dict:
    today = date.today()
    iso = today.isocalendar()
    semaine = f"{iso.year}-W{iso.week:02d}"

    flux_rows = [r for r in rows if not is_anomaly(r)]
    anomaly_rows = [r for r in rows if is_anomaly(r)]

    total = len(flux_rows)
    ready = sum(1 for r in flux_rows if is_ready(r))
    not_ready = max(0, total - ready)
    rate = round((ready / total) * 100) if total else 0
    level = "Vert" if rate >= 80 else ("Orange" if rate >= 60 else "Rouge")

    flux_prets = [row_to_flux(r) for r in flux_rows]

    hist: dict[str, dict] = {}

    for r in flux_rows:
        f = row_to_flux(r)
        key = f["domaine"] + "||" + f["sousDomaine"]

        if key not in hist:
            hist[key] = {
                "domaine": f["domaine"],
                "sousDomaine": f["sousDomaine"],
                "livresSIT": 0,
                "livresUAT": 0,
                "bloquesSIT": 0,
                "bloquesUAT": 0,
                "anomaliesOuvertesSIT": 0,
                "anomaliesOuvertesUAT": 0,
                "anomaliesResoluesSIT": 0,
                "anomaliesResoluesUAT": 0,
                "anomaliesEnCoursSIT": 0,
                "anomaliesEnCoursUAT": 0,
            }

        for env in f["env"]:
            if env == "SIT":
                if is_ready(r):
                    hist[key]["livresSIT"] += 1
                else:
                    hist[key]["bloquesSIT"] += 1
            elif env == "UAT":
                if is_ready(r):
                    hist[key]["livresUAT"] += 1
                else:
                    hist[key]["bloquesUAT"] += 1

    for r in anomaly_rows:
        f = row_to_flux(r)
        key = f["domaine"] + "||" + f["sousDomaine"]

        if key not in hist:
            hist[key] = {
                "domaine": f["domaine"],
                "sousDomaine": f["sousDomaine"],
                "livresSIT": 0,
                "livresUAT": 0,
                "bloquesSIT": 0,
                "bloquesUAT": 0,
                "anomaliesOuvertesSIT": 0,
                "anomaliesOuvertesUAT": 0,
                "anomaliesResoluesSIT": 0,
                "anomaliesResoluesUAT": 0,
                "anomaliesEnCoursSIT": 0,
                "anomaliesEnCoursUAT": 0,
            }

        status = first(r, "statut", "status", "etat", "etatAnomalie").lower()
        for env in envs(r):
            suffix = "SIT" if env == "SIT" else "UAT"
            if "résolu" in status or "resolu" in status or "done" in status or "closed" in status:
                hist[key]["anomaliesResolues" + suffix] += 1
            elif "cours" in status or "progress" in status:
                hist[key]["anomaliesEnCours" + suffix] += 1
            else:
                hist[key]["anomaliesOuvertes" + suffix] += 1

    sit_total = sum(1 for r in flux_rows if "SIT" in envs(r))
    uat_total = sum(1 for r in flux_rows if "UAT" in envs(r))
    sit_ready = sum(1 for r in flux_rows if "SIT" in envs(r) and is_ready(r))
    uat_ready = sum(1 for r in flux_rows if "UAT" in envs(r) and is_ready(r))

    return {
        "sprintCourant": "Sprint 21",
        "semaineCourante": semaine,
        "dateConstat": semaine + " — recalcul automatique",
        "kpis": {
            "taux": rate,
            "niveau": level,
            "total": total,
            "prets": ready,
            "nonPrets": not_ready,
            "enCours": not_ready,
            "bloques": not_ready,
        },
        "comparaisonSprints": [
            {
                "sprint": "Sprint 20",
                "semaines": "Sprint N-1",
                "totalSIT": sit_total,
                "totalUAT": uat_total,
                "livresSIT": max(0, sit_ready - 1),
                "livresUAT": max(0, uat_ready - 1),
                "encoursSIT": 1 if sit_total else 0,
                "encoursUAT": 1 if uat_total else 0,
                "bloquesSIT": 0,
                "bloquesUAT": 0,
                "statut": level,
            },
            {
                "sprint": "Sprint 21",
                "semaines": semaine,
                "totalSIT": sit_total,
                "totalUAT": uat_total,
                "livresSIT": sit_ready,
                "livresUAT": uat_ready,
                "encoursSIT": max(0, sit_total - sit_ready),
                "encoursUAT": max(0, uat_total - uat_ready),
                "bloquesSIT": max(0, sit_total - sit_ready),
                "bloquesUAT": max(0, uat_total - uat_ready),
                "statut": level,
            },
        ],
        "fluxPrets": flux_prets,
        "histoFlux": list(hist.values()),
        "histoAnomalies": list(hist.values()),
        "tendanceHebdo": {
            "rows": [
                {
                    "semaine": semaine,
                    "sprint": "Sprint 21",
                    "total": total,
                    "prets": ready,
                    "enCours": not_ready,
                    "bloques": not_ready,
                    "statut": level,
                }
            ]
        },
        "prioritesHebdo": [],
        "anomalies": [row_to_flux(r) for r in anomaly_rows],
        "records": rows,
    }


def json_for_script(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    text = text.replace("</", "<\\/")
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return text


def disable_external_json_load(html: str) -> str:
    html = re.sub(
        r"try\s*\{\s*const\s+r\s*=\s*await\s+fetch\(\s*['\"]rapport_gil_v6_data\.json['\"]\s*,\s*\{cache\s*:\s*['\"]no-store['\"]\}\s*\)\s*;\s*if\s*\(r\.ok\)\s*data\s*=\s*await\s+r\.json\(\)\s*;\s*\}\s*catch\s*\(\s*e\s*\)\s*\{\s*\}",
        "/* JIRA stable : chargement JSON externe désactivé ; fallbackData embarqué utilisé */",
        html,
        flags=re.S,
    )

    html = html.replace(
        "fetch('rapport_gil_v6_data.json'",
        "fetch('__disabled_rapport_gil_v6_data.json'",
    )
    html = html.replace(
        'fetch("rapport_gil_v6_data.json',
        'fetch("__disabled_rapport_gil_v6_data.json',
    )

    return html


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

    html = re.sub(r'<div class="actions">.*?</div>', "", html, flags=re.S)

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


def replace_fallback_data(html: str, payload: dict) -> str:
    clean_json = json_for_script(payload)

    new_block = "const fallbackData = " + clean_json + ";\nlet currentData = fallbackData;"

    html2, count = re.subn(
        r"const fallbackData\s*=\s*[\s\S]*?;\s*let currentData\s*=\s*fallbackData\s*;",
        new_block,
        html,
        flags=re.S,
    )

    if count == 0:
        stop("Impossible de remplacer fallbackData dans dashboard_gil_sprint21.html")

    return html2


def verify_html(html: str, payload: dict) -> None:
    if "fetch('rapport_gil_v6_data.json'" in html or 'fetch("rapport_gil_v6_data.json' in html:
        stop("Le HTML contient encore un fetch actif vers rapport_gil_v6_data.json")

    if "function runLocalAction" not in html:
        stop("runLocalAction absent après publication")

    match = re.search(r"const fallbackData\s*=\s*([\s\S]*?);\s*let currentData", html)
    if not match:
        stop("fallbackData absent après publication")

    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        stop(f"fallbackData JSON invalide après publication : {exc}")

    expected_total = payload.get("kpis", {}).get("total", 0)
    actual_total = parsed.get("kpis", {}).get("total", 0)

    if expected_total and not actual_total:
        stop("fallbackData publié avec total à 0 alors que la source JIRA contient des flux")


def main() -> None:
    print("=== PUBLICATION JIRA -> HTML LEGACY STABLE ===")

    if not JIRA_SOURCE.exists():
        stop(f"Source JIRA absente : {JIRA_SOURCE}")

    if not GENERATOR.exists():
        stop(f"Générateur legacy absent : {GENERATOR}")

    if not HTML.exists():
        stop(f"HTML legacy absent : {HTML}")

    rows = load_rows(JIRA_SOURCE)
    if not rows:
        stop("Source JIRA vide : aucun flux à publier")

    payload = build_payload(rows)

    print("[1/4] Copie JIRA vers commun/dashboard_gil_data.json")
    shutil.copy2(JIRA_SOURCE, COMMUN_SOURCE)

    print("[2/4] Génération HTML legacy")
    run([sys.executable, "generer_dashboard_gil_classique.py"], ROOT)

    print("[3/4] Réinjection fallbackData propre + désactivation JSON externe")
    html = read_text(HTML)
    html = disable_external_json_load(html)
    html = inject_buttons_and_js(html)
    html = replace_fallback_data(html, payload)
    write_text(HTML, html)

    print("[4/4] Contrôle")
    html2 = read_text(HTML)
    verify_html(html2, payload)

    print("[OK] Publication JIRA stable.")
    print("Flux :", payload["kpis"]["total"])
    print("Prêts :", payload["kpis"]["prets"])
    print("Taux :", str(payload["kpis"]["taux"]) + "%")
    print("HTML :", HTML)


if __name__ == "__main__":
    main()
