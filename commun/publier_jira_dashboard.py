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



def enrich_score_detail(payload: dict) -> dict:
    """Ajoute le détail du calcul de santé sprint sans changer la règle historique.

    Règle conservée :
    - score brut = flux prêts / total flux
    - pénalité = bugsBloquants * 3
    - pénalité max = 35 points
    - score final = score brut - pénalité
    """

    def to_int(value, default=0):
        try:
            if value is None or value == "":
                return default
            return int(round(float(value)))
        except Exception:
            return default

    tendance = payload.setdefault("tendanceHebdo", {})
    rows = tendance.get("rows") or []

    current = tendance.get("current")
    if not isinstance(current, dict):
        current = rows[-1] if rows and isinstance(rows[-1], dict) else {}

    kpis = payload.setdefault("kpis", {})

    total_flux = to_int(
        current.get("flux")
        or current.get("total")
        or kpis.get("flux")
        or kpis.get("total")
    )

    flux_prets = to_int(
        current.get("pretTester")
        or current.get("prets")
        or current.get("ready")
        or kpis.get("pretTester")
        or kpis.get("prets")
        or kpis.get("ready")
    )

    bugs_bloquants = to_int(
        current.get("bugsBloquants")
        or kpis.get("bugsBloquants")
        or 0
    )

    score_brut = round((flux_prets / total_flux) * 100) if total_flux else 100
    penalite_unitaire = 3
    penalite_max = 35
    penalite = min(penalite_max, bugs_bloquants * penalite_unitaire)
    score_final = max(0, min(100, round(score_brut - penalite)))

    niveau = "Vert" if score_final >= 80 else ("Orange" if score_final >= 60 else "Rouge")

    detail = {
        "totalFlux": total_flux,
        "fluxPrets": flux_prets,
        "bugsBloquants": bugs_bloquants,
        "scoreBrut": score_brut,
        "penaliteUnitaireBugBloquant": penalite_unitaire,
        "penaliteMax": penalite_max,
        "penalite": penalite,
        "scoreFinal": score_final,
        "niveau": niveau,
        "formule": "scoreFinal = round(fluxPrets / totalFlux * 100) - min(35, bugsBloquants * 3)",
        "regle": "Règle historique conservée : seule la volumétrie des bugs bloquants pénalise le score.",
    }

    kpis.update({
        "flux": total_flux,
        "pretTester": flux_prets,
        "bugsBloquants": bugs_bloquants,
        "scoreBrut": score_brut,
        "penalite": penalite,
        "scoreFinal": score_final,
        "taux": score_final,
        "niveau": niveau,
    })

    current.update({
        "flux": total_flux,
        "pretTester": flux_prets,
        "nonPret": max(0, total_flux - flux_prets),
        "bugsBloquants": bugs_bloquants,
        "scoreBrut": score_brut,
        "penalite": penalite,
        "scoreFinal": score_final,
        "sante": niveau,
    })

    if rows:
        rows[-1].update(current)
    else:
        rows.append(current)

    tendance["rows"] = rows
    tendance["current"] = current

    payload["statutSprintCalcul"] = detail

    return payload


def load_sprint_context() -> dict:
    """Lit le diagnostic Jira et retourne les noms de sprint détectés."""

    diagnostic = PROJECT / "jira" / "jira_diagnostic.json"
    if not diagnostic.exists():
        return {}

    try:
        data = json.loads(diagnostic.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}

    sprints = data.get("sprints") or data.get("diagnostic_sprints") or {}
    courant = sprints.get("courant") or sprints.get("current") or {}
    precedent = sprints.get("precedent") or sprints.get("previous") or {}

    return {
        "projectKey": sprints.get("projectKey") or data.get("project_key") or "",
        "courant": courant,
        "precedent": precedent,
        "nomCourant": courant.get("nom") or courant.get("name") or "",
        "nomPrecedent": precedent.get("nom") or precedent.get("name") or "",
        "sprints": sprints,
    }


def apply_sprint_context(payload: dict) -> dict:
    """Injecte les noms de sprint Jira sans modifier le calcul."""

    ctx = load_sprint_context()
    current_name = ctx.get("nomCourant") or payload.get("sprintCourant") or "Sprint courant"
    previous_name = ctx.get("nomPrecedent") or payload.get("sprintPrecedent") or "Sprint N-1"

    payload["sprintCourant"] = current_name
    payload["sprintPrecedent"] = previous_name
    payload["diagnosticSprintsJira"] = ctx

    comparaison = payload.get("comparaisonSprints")
    if isinstance(comparaison, list) and comparaison:
        if len(comparaison) >= 2:
            comparaison[0]["sprint"] = previous_name
            comparaison[0]["typeDonnee"] = comparaison[0].get("typeDonnee") or "Sprint N-1"
            comparaison[-1]["sprint"] = current_name
            comparaison[-1]["typeDonnee"] = comparaison[-1].get("typeDonnee") or "Réel"
        else:
            comparaison[0]["sprint"] = current_name
            comparaison[0]["typeDonnee"] = comparaison[0].get("typeDonnee") or "Réel"

    for key in [
        "fluxPrets",
        "fluxPretsArrimage",
        "histoFlux",
        "histoAnomalies",
        "anomalies",
        "anomaliesDetail",
        "prioritesHebdo",
    ]:
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                sprint = str(item.get("sprint") or "")
                if not sprint or sprint.startswith("Sprint "):
                    item["sprint"] = current_name

    tendance = payload.get("tendanceHebdo") or {}
    rows = tendance.get("rows") or []
    if rows and isinstance(rows[-1], dict):
        rows[-1]["sprint"] = current_name
    if isinstance(tendance.get("current"), dict):
        tendance["current"]["sprint"] = current_name

    return payload


def load_sprints_dashboard() -> dict:
    """Charge la base sprint construite depuis Jira.

    Cette base devient la source de vérité pour :
    - sprint courant
    - sprint précédent
    - comparaison des flux/anomalies entre les deux sprints
    """

    path = PROJECT / "jira" / "sprints_dashboard.json"
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def apply_sprint_comparison_from_jira(payload: dict) -> dict:
    """Injecte les noms de sprint dynamiques et la comparaison Jira.

    Le calcul du statut sprint n'est pas modifié ici.
    """

    sprint_data = load_sprints_dashboard()
    if not sprint_data:
        return payload

    if sprint_data.get("reliable") is not True:
        payload["diagnosticSprintsJira"] = sprint_data
        payload["sprintDetectionWarning"] = sprint_data.get("warnings") or [
            "Détection sprint Jira non fiable : comparaison dynamique non appliquée."
        ]
        return payload

    courant = sprint_data.get("courant") or {}
    precedent = sprint_data.get("precedent") or {}

    nom_courant = courant.get("nom") or payload.get("sprintCourant") or "Sprint courant"
    nom_precedent = precedent.get("nom") or payload.get("sprintPrecedent") or "Sprint précédent"

    payload["sprintCourant"] = nom_courant
    payload["sprintPrecedent"] = nom_precedent
    payload["diagnosticSprintsJira"] = sprint_data

    comparaison = sprint_data.get("comparaisonSprints")
    if isinstance(comparaison, list) and comparaison:
        payload["comparaisonSprints"] = comparaison

    tendance = payload.get("tendanceHebdo") or {}
    rows = tendance.get("rows") or []

    if rows and isinstance(rows[-1], dict):
        rows[-1]["sprint"] = nom_courant

    if isinstance(tendance.get("current"), dict):
        tendance["current"]["sprint"] = nom_courant

    payload["tendanceHebdo"] = tendance

    for key in [
        "fluxPrets",
        "fluxPretsArrimage",
        "histoFlux",
        "histoAnomalies",
        "anomalies",
        "anomaliesDetail",
        "prioritesHebdo",
    ]:
        values = payload.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                item["sprint"] = nom_courant

    return payload

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



def inject_statut_sprint_tooltips(html: str) -> str:
    """Injecte les bulles d'explication du bloc Statut du Sprint."""

    css = r"""
<style id="statutSprintCalcStyle">
.statutCalcBox{
  display:flex;
  flex-wrap:wrap;
  justify-content:center;
  gap:10px;
  margin:12px auto 4px auto;
  max-width:980px;
  font-size:12px;
}
.statutCalcBox .calcPill{
  position:relative;
  border:1px solid #cbd5e1;
  border-radius:10px;
  background:#f8fafc;
  padding:8px 10px;
  min-width:120px;
  text-align:center;
  cursor:help;
}
.statutCalcBox .calcPill b{
  display:block;
  color:#334155;
  font-size:11px;
}
.statutCalcBox .calcPill span{
  display:block;
  color:#0f172a;
  font-weight:800;
  font-size:15px;
  margin-top:2px;
}
.statutCalcBox .calcPill:hover::after{
  content:attr(data-tip);
  position:absolute;
  left:50%;
  bottom:calc(100% + 8px);
  transform:translateX(-50%);
  width:280px;
  background:#111827;
  color:white;
  padding:10px;
  border-radius:8px;
  box-shadow:0 8px 20px rgba(0,0,0,.25);
  z-index:9999;
  white-space:normal;
  line-height:1.35;
  text-align:left;
}
.statutCalcBox .calcPill:hover::before{
  content:"";
  position:absolute;
  left:50%;
  bottom:100%;
  transform:translateX(-50%);
  border:8px solid transparent;
  border-top-color:#111827;
  z-index:9999;
}
.statutCalcFormula{
  width:100%;
  text-align:center;
  color:#475569;
  font-size:12px;
  margin-top:4px;
}
</style>
"""

    js = r"""
<script id="statutSprintCalcTooltipScript">
(function(){
  function esc(v){
    return String(v ?? '').replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function readCalc(data){
    data = data || {};
    const k = data.kpis || {};
    const t = data.tendanceHebdo || {};
    const rows = t.rows || [];
    const current = t.current || rows[rows.length - 1] || {};
    const c = data.statutSprintCalcul || {};

    const totalFlux = c.totalFlux ?? k.flux ?? k.total ?? current.flux ?? current.total ?? 0;
    const fluxPrets = c.fluxPrets ?? k.pretTester ?? k.prets ?? current.pretTester ?? current.prets ?? 0;
    const bugsBloquants = c.bugsBloquants ?? k.bugsBloquants ?? current.bugsBloquants ?? 0;

    const scoreBrut = c.scoreBrut ?? Math.round(totalFlux ? fluxPrets / totalFlux * 100 : 100);
    const penalite = c.penalite ?? Math.min(35, Number(bugsBloquants || 0) * 3);
    const scoreFinal = c.scoreFinal ?? Math.max(0, Math.min(100, Math.round(scoreBrut - penalite)));
    const niveau = c.niveau ?? (scoreFinal >= 80 ? 'Vert' : scoreFinal >= 60 ? 'Orange' : 'Rouge');

    return {totalFlux, fluxPrets, bugsBloquants, scoreBrut, penalite, scoreFinal, niveau};
  }

  function findStatutSection(){
    const sections = Array.from(document.querySelectorAll('section'));
    return sections.find(function(s){
      const h = s.querySelector('h2');
      return h && /Statut du Sprint/i.test(h.textContent || '');
    });
  }

  function decorateStatutSprintTooltips(){
    let data;
    try { data = currentData || fallbackData; } catch(e) { data = null; }
    if (!data) return;

    const c = readCalc(data);
    const section = findStatutSection();
    if (!section) return;

    let box = section.querySelector('.statutCalcBox');
    if (!box) {
      box = document.createElement('div');
      box.className = 'statutCalcBox';
      section.appendChild(box);
    }

    box.innerHTML =
      '<div class="calcPill" title="Nombre total de flux suivis dans le sprint, hors lignes purement anomalies." data-tip="Total flux : nombre de flux suivis pour le sprint. Les anomalies servent à la pénalité mais ne sont pas comptées comme flux prêts."><b>Total flux</b><span>'+esc(c.totalFlux)+'</span></div>' +
      '<div class="calcPill" title="Flux considérés prêts pour arrimage." data-tip="Flux prêts : nombre de flux dont le statut est prêt, livré ou prêt pour arrimage selon la source préparée."><b>Flux prêts</b><span>'+esc(c.fluxPrets)+'</span></div>' +
      '<div class="calcPill" title="Score brut = flux prêts / total flux × 100." data-tip="Score brut : round(flux prêts / total flux × 100). Exemple : 16 / 18 = 88,89 %, arrondi à 89 %."><b>Score brut</b><span>'+esc(c.scoreBrut)+'%</span></div>' +
      '<div class="calcPill" title="Bugs bloquants utilisés pour appliquer la pénalité historique." data-tip="Bugs bloquants : nombre d’anomalies bloquantes prises en compte par la règle historique. Chaque bug bloquant enlève 3 points."><b>Bugs bloquants</b><span>'+esc(c.bugsBloquants)+'</span></div>' +
      '<div class="calcPill" title="Pénalité = min(35, bugs bloquants × 3)." data-tip="Pénalité : min(35, bugs bloquants × 3). Le plafond de 35 évite qu’une volumétrie élevée d’anomalies fasse tomber le score de façon illimitée."><b>Pénalité</b><span>-'+esc(c.penalite)+' pts</span></div>' +
      '<div class="calcPill" title="Score final affiché par la jauge." data-tip="Score final : score brut - pénalité. C’est cette valeur qui pilote la jauge et le niveau Rouge, Orange ou Vert."><b>Score final</b><span>'+esc(c.scoreFinal)+'% '+esc(c.niveau)+'</span></div>' +
      '<div class="statutCalcFormula">Méthode : score final = round(flux prêts / total flux × 100) - min(35, bugs bloquants × 3). Seuils : Rouge 0–59 %, Orange 60–79 %, Vert 80–100 %.</div>';
  }

  const previousRender = (typeof render === 'function') ? render : null;
  if (previousRender && !previousRender.__statutCalcWrapped) {
    const wrapped = function(data){
      previousRender(data);
      setTimeout(decorateStatutSprintTooltips, 0);
    };
    wrapped.__statutCalcWrapped = true;
    render = wrapped;
  }

  window.addEventListener('load', function(){
    setTimeout(decorateStatutSprintTooltips, 150);
  });

  window.decorateStatutSprintTooltips = decorateStatutSprintTooltips;
})();
</script>
"""

    if "statutSprintCalcStyle" not in html:
        html = html.replace("</head>", css + "\n</head>", 1) if "</head>" in html else css + "\n" + html

    if "statutSprintCalcTooltipScript" not in html:
        html = html.replace("</body>", js + "\n</body>", 1) if "</body>" in html else html + "\n" + js

    return html



def has_reliable_sprints_dashboard() -> bool:
    data = load_sprints_dashboard()
    return bool(data and data.get("reliable") is True)


def clean_dynamic_sprint_labels(html: str) -> str:
    return re.sub(
        r'\n?<script id="dynamicSprintLabelsScript">[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )

def inject_dynamic_sprint_labels(html: str) -> str:
    """Met à jour les libellés visibles des sprints dans le HTML legacy.

    Source de vérité :
    - payload.sprintCourant
    - payload.sprintPrecedent
    - payload.diagnosticSprintsJira
    """

    js = r"""
<script id="dynamicSprintLabelsScript">
(function(){
  function value(v, fallback){
    const text = String(v ?? '').trim();
    return text || fallback;
  }

  function getDashboardData(){
    try {
      if (typeof currentData !== 'undefined' && currentData) return currentData;
      if (typeof fallbackData !== 'undefined' && fallbackData) return fallbackData;
    } catch(e) {}
    return {};
  }

  function sprintNames(data){
    data = data || {};
    const diag = data.diagnosticSprintsJira || {};
    const courant = diag.courant || {};
    const precedent = diag.precedent || {};

    const currentName = value(
      data.sprintCourant || courant.nom || courant.name,
      'Sprint courant'
    );

    const previousName = value(
      data.sprintPrecedent || precedent.nom || precedent.name,
      'Sprint précédent'
    );

    return {currentName, previousName};
  }

  function setTextById(id, text){
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function updateComparisonTitle(previousName, currentName){
    const headings = Array.from(document.querySelectorAll('h1,h2,h3'));
    for (const h of headings) {
      const text = h.textContent || '';
      if (/Comparaison\s+Sprint\s+N-1\s*\/\s*Sprint\s+actuel/i.test(text)) {
        h.textContent = 'Comparaison ' + previousName + ' / ' + currentName;
      }
    }
  }

  function replaceVisibleSprintTokens(root, previousName, currentName){
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];

    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }

    for (const node of nodes) {
      const parent = node.parentElement;
      if (!parent) continue;

      const tag = parent.tagName ? parent.tagName.toLowerCase() : '';
      if (tag === 'script' || tag === 'style') continue;

      let text = node.nodeValue || '';
      let next = text
        .replace(/Sprint\s+N-1/g, previousName)
        .replace(/Sprint\s+précédent/g, previousName)
        .replace(/Sprint\s+precedent/g, previousName)
        .replace(/Sprint\s+actuel/g, currentName)
        .replace(/Sprint\s+courant/g, currentName);

      if (next !== text) {
        node.nodeValue = next;
      }
    }
  }

  function updateWeeklyTrendRows(previousName, currentName){
    const table = document.getElementById('weeklyTrend');
    if (!table) return;

    const bodyRows = Array.from(table.querySelectorAll('tr')).filter(function(tr){
      return tr.querySelector('td');
    });

    if (bodyRows.length >= 2) {
      const first = bodyRows[0].querySelector('td');
      const last = bodyRows[bodyRows.length - 1].querySelector('td');

      if (first) first.textContent = previousName;
      if (last) last.textContent = currentName;
    }
  }

  function applyDynamicSprintLabels(){
    const data = getDashboardData();
    const names = sprintNames(data);

    document.title = 'Biweekly GIL - Reporting ' + names.currentName;

    setTextById('reportTitle', 'Biweekly GIL - Reporting ' + names.currentName);
    setTextById('gaugeTitle', 'Statut du Sprint — ' + names.currentName);
    setTextById('generalTitle', 'Statut général du Sprint — ' + names.currentName);

    updateComparisonTitle(names.previousName, names.currentName);
    replaceVisibleSprintTokens(document.body, names.previousName, names.currentName);
    updateWeeklyTrendRows(names.previousName, names.currentName);
  }

  const previousRender = (typeof render === 'function') ? render : null;
  if (previousRender && !previousRender.__dynamicSprintLabelsWrapped) {
    const wrapped = function(data){
      previousRender(data);
      setTimeout(applyDynamicSprintLabels, 0);
    };
    wrapped.__dynamicSprintLabelsWrapped = true;
    render = wrapped;
  }

  window.addEventListener('load', function(){
    setTimeout(applyDynamicSprintLabels, 150);
  });

  window.applyDynamicSprintLabels = applyDynamicSprintLabels;
})();
</script>
"""

    if "dynamicSprintLabelsScript" not in html:
        html = html.replace("</body>", js + "\n</body>", 1) if "</body>" in html else html + "\n" + js

    return html

def replace_fallback_data(html: str, payload: dict) -> str:
    payload = apply_sprint_context(payload)
    payload = enrich_score_detail(payload)
    payload = apply_sprint_comparison_from_jira(payload)
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
    """Contrôle non destructif après publication.

    On ne re-parse pas fallbackData depuis le HTML.
    Le payload est déjà construit en Python puis injecté avec json.dumps.
    """

    if "fetch('rapport_gil_v6_data.json'" in html or 'fetch("rapport_gil_v6_data.json' in html:
        stop("Le HTML contient encore un fetch actif vers rapport_gil_v6_data.json")

    if "function runLocalAction" not in html:
        stop("runLocalAction absent après publication")

    if "const fallbackData" not in html or "let currentData = fallbackData" not in html:
        stop("fallbackData absent après publication")

    required_tokens = [
        '"statutSprintCalcul"',
        '"scoreBrut"',
        '"penalite"',
        '"scoreFinal"',
        '"niveau"',
        "statutSprintCalcTooltipScript",
        "decorateStatutSprintTooltips",
    ]

    missing = [token for token in required_tokens if token not in html]
    if missing:
        stop("Détail du calcul statut sprint ou bulles absents du HTML : " + ", ".join(missing))


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
    html = inject_statut_sprint_tooltips(html)
    html = clean_dynamic_sprint_labels(html)
    html = inject_dynamic_sprint_labels(html) if has_reliable_sprints_dashboard() else html
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
