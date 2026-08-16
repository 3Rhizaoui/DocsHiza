from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
SOURCE = ROOT / "dashboard_gil_data.json"
HTML = ROOT / "dashboard_gil.html"
LEGACY_HTML = ROOT / "dashboard_gil_sprint21.html"
ARCHIVE_INDEX = PROJECT / "archives_sprints" / "index_sprints.json"
VERSION_CALCUL = "dynamic-v1"
ENVIRONMENTS = {"SIT", "UAT"}


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fold(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def to_number(value) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def week_key(value: str) -> tuple:
    match = re.search(r"(\d{4})\D*W?(\d{1,2})", str(value or ""), re.I)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (0, 0)


def sprint_order(value: str) -> tuple:
    match = re.search(r"(\d+)", str(value or ""))
    if match:
        return (1, int(match.group(1)))
    return (0, str(value or ""))


def normalize_records(data: dict) -> list[dict]:
    raw_records = data.get("records") or []
    if not raw_records and data.get("flux"):
        generated_at = str(data.get("generated_at") or data.get("generatedAt") or datetime.now().astimezone().isoformat())
        try:
            generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            generated_dt = datetime.now().astimezone()
        iso_year, iso_week, _ = generated_dt.isocalendar()
        week = f"{iso_year}-W{iso_week:02d}"
        sprint = str(data.get("sprint") or data.get("sprintCourant") or f"Semaine {week}")
        raw_records = []
        anomalies_by_key = defaultdict(list)
        for anomaly in data.get("anomalies") or []:
            anomalies_by_key[(str(anomaly.get("flux") or ""), str(anomaly.get("environnement") or ""))].append(anomaly)
        for item in data.get("flux") or []:
            ref = str(item.get("reference_flux") or item.get("reference") or item.get("id") or "")
            env = str(item.get("environnement") or "")
            related = anomalies_by_key[(ref, env)]
            has_blocker = any(bool(a.get("bloquante")) and fold(a.get("statut")) not in {"resolue", "resolu"} for a in related)
            raw_records.append({
                "id": ref,
                "reference": ref,
                "type": "AVRO" if str(item.get("type_flux") or "").casefold() == "event" else "Configuration",
                "domaine": item.get("domaine") or "Non renseigné",
                "sousDomaine": item.get("sous_domaine") or item.get("sousDomaine") or "Non renseigné",
                "environnement": env,
                "semaine": week,
                "sprint": item.get("sprint") or sprint,
                "etatFlux": "Prêt" if item.get("pret_arrimage") else "En cours",
                "etatAnomalie": "KO" if has_blocker else "",
                "statut": "Livré" if item.get("configuration_deployee") else str(item.get("statut_configuration") or ""),
                "version": " / ".join(map(str, item.get("versions") or [])) if isinstance(item.get("versions"), list) else str(item.get("versions") or ""),
                "nombre": 1,
                "commentaire": item.get("description") or "",
                "source": item.get("partenaire") or data.get("source_type") or "",
                "date": generated_dt.date().isoformat(),
                "nature": data.get("source_type") or "Source normalisée",
            })
        for anomaly in data.get("anomalies") or []:
            raw_records.append({
                "id": anomaly.get("flux") or anomaly.get("reference") or "",
                "reference": anomaly.get("reference") or "",
                "type": "Anomalie",
                "domaine": anomaly.get("domaine") or "Non renseigné",
                "sousDomaine": anomaly.get("sous_domaine") or anomaly.get("sousDomaine") or "Non renseigné",
                "environnement": anomaly.get("environnement") or "",
                "semaine": week,
                "sprint": anomaly.get("sprint") or sprint,
                "etatFlux": "",
                "etatAnomalie": "Corrigée" if fold(anomaly.get("statut")) in {"resolue", "resolu", "done", "clos"} else "KO",
                "statut": anomaly.get("statut") or "",
                "version": "",
                "nombre": 1,
                "commentaire": anomaly.get("description") or anomaly.get("resume") or "",
                "source": anomaly.get("responsable") or data.get("source_type") or "",
                "date": generated_dt.date().isoformat(),
                "severite": anomaly.get("severite") or "",
            })
    records = []
    for r in raw_records:
        env = str(r.get("environnement") or "").upper().strip()
        if env not in ENVIRONMENTS:
            continue
        week = str(r.get("semaine") or r.get("week") or "").strip()
        if not week:
            week = "Semaine non définie"
        sprint = str(r.get("sprint") or r.get("sprintCourant") or f"Semaine {week}").strip()
        kind = str(r.get("type") or r.get("typeLivraison") or "Configuration").strip()
        records.append({
            "id": str(r.get("id") or r.get("ID_Flux") or r.get("reference") or "").strip(),
            "reference": str(r.get("reference") or r.get("Référence_Source") or r.get("jira_key") or r.get("id") or "").strip(),
            "jira_key": str(r.get("jira_key") or r.get("epic_key") or "").strip(),
            "type": kind,
            "domaine": str(r.get("domaine") or r.get("Domaine") or "Non classé").strip(),
            "sousDomaine": str(r.get("sousDomaine") or r.get("sous_domaine") or r.get("Sous_Domaine") or "Non classé").strip(),
            "environnement": env,
            "semaine": week,
            "sprint": sprint,
            "etatFlux": str(r.get("etatFlux") or r.get("État_Flux") or "").strip(),
            "etatAnomalie": str(r.get("etatAnomalie") or r.get("État_Anomalie") or "").strip(),
            "statut": str(r.get("statut") or r.get("Statut") or "").strip(),
            "version": str(r.get("version") or r.get("Version") or "").strip(),
            "nombre": to_number(r.get("nombre") or r.get("Nombre") or 1),
            "commentaire": str(r.get("commentaire") or r.get("Commentaire") or r.get("resume") or "").strip(),
            "source": str(r.get("source") or r.get("source_system") or r.get("nature") or "").strip(),
            "date": str(r.get("date") or r.get("Date_Rapport") or "").strip(),
            "severite": str(r.get("severite") or r.get("sévérité") or r.get("criticite") or "").strip(),
            "url_source": str(r.get("url_source") or r.get("url") or "").strip(),
            "description": str(r.get("description") or "").strip(),
        })
    return records


def flow_status(row: dict) -> str:
    status = fold(" ".join(str(row.get(k) or "") for k in ("etatFlux", "etatAnomalie", "statut", "commentaire")))
    if row.get("etatAnomalie") == "KO" or any(w in status for w in ("bloqu", "rejet", "refus", " ko", "non pret", "non-pret", "abandon", "annul")):
        return "blocked"
    if any(w in status for w in ("en cours", "progress", "a faire", "a traiter", "todo", "doing")):
        return "progress"
    if row.get("etatFlux") == "Prêt" or any(w in status for w in ("pret", "prêt", "livr", "done", "termine", "terminé", "closed")):
        return "delivered"
    return "progress"


def detail_item(row: dict, label: str) -> dict:
    return {
        "reference": row.get("reference") or row.get("id") or "",
        "flux": row.get("id") or row.get("reference") or "",
        "jiraKey": row.get("jira_key") or "",
        "domaine": row.get("domaine") or "Non classé",
        "sousDomaine": row.get("sousDomaine") or "Non classé",
        "environnement": row.get("environnement") or "",
        "statut": label,
        "statutSource": row.get("statut") or row.get("etatFlux") or row.get("etatAnomalie") or "",
        "partenaire": row.get("source") or "",
        "nombre": to_number(row.get("nombre") or 1),
        "version": row.get("version") or "",
        "resume": row.get("commentaire") or "",
        "description": row.get("description") or "",
        "url": row.get("url_source") or "",
    }


def metrics(records: list[dict]) -> dict:
    flow_rows = [r for r in records if r.get("type") != "Anomalie"]
    delivered = []
    progress = []
    blocked = []
    for row in flow_rows:
        status = flow_status(row)
        if status == "delivered":
            delivered.append(detail_item(row, "Livré"))
        elif status == "blocked":
            blocked.append(detail_item(row, "Bloqué / Rejeté"))
        else:
            progress.append(detail_item(row, "En cours"))
    total_detail = [detail_item(r, "Total") for r in flow_rows]
    total = sum(x["nombre"] for x in total_detail)
    return {
        "fluxTotal": total,
        "fluxLivresTotal": sum(x["nombre"] for x in delivered),
        "fluxEnCoursTotal": sum(x["nombre"] for x in progress),
        "fluxBloquesTotal": sum(x["nombre"] for x in blocked),
        "fluxTotalDetail": total_detail,
        "fluxLivresDetail": delivered,
        "fluxEnCoursDetail": progress,
        "fluxBloquesDetail": blocked,
        "anomalies": sum(to_number(r.get("nombre") or 1) for r in records if r.get("type") == "Anomalie" or r.get("etatAnomalie") == "KO"),
        "tauxPret": round((sum(x["nombre"] for x in delivered) / total) * 100) if total else 0,
    }


def archive_records_for_previous(current_sprint: str):
    index = read_json(ARCHIVE_INDEX, {}) or {}
    entries = index.get("archives") or []
    if isinstance(entries, dict):
        entries = list(entries.values())
    candidates = [e for e in entries if str(e.get("sprint") or "") != current_sprint and e.get("statut", "VALIDE") == "VALIDE"]
    if not candidates:
        latest = index.get("last_validated") or index.get("dernier_sprint_valide") or {}
        if isinstance(latest, dict) and str(latest.get("sprint") or "") != current_sprint:
            candidates = [latest]
    if not candidates:
        return None, []
    candidates.sort(key=lambda e: str(e.get("date_validation") or e.get("validated_at") or ""))
    entry = candidates[-1]
    path = entry.get("data_path") or entry.get("chemin_data") or entry.get("path")
    if path:
        data_path = (PROJECT / path).resolve() if not Path(path).is_absolute() else Path(path)
    else:
        archive_dir = entry.get("archive_dir") or entry.get("chemin") or ""
        data_path = (PROJECT / archive_dir / "dashboard_gil_data.json").resolve()
    data = read_json(data_path, {}) or {}
    return str(entry.get("sprint") or data.get("sprintCourant") or "Sprint validé"), normalize_records(data)


def build_payload(data: dict) -> dict:
    records = normalize_records(data)
    if not records:
        raise SystemExit("Aucune ligne exploitable SIT/UAT dans dashboard_gil_data.json.")
    weeks = sorted({r["semaine"] for r in records}, key=week_key)
    sprints = sorted({r["sprint"] for r in records}, key=sprint_order)
    current_sprint = sprints[-1]
    current_records = [r for r in records if r["sprint"] == current_sprint]
    current_weeks = sorted({r["semaine"] for r in current_records}, key=week_key) or [weeks[-1]]
    previous_sprint, previous_records = archive_records_for_previous(current_sprint)
    comparison_source = "archive validée"
    if not previous_records:
        live_previous = [s for s in sprints if s != current_sprint]
        previous_sprint = live_previous[-1] if live_previous else current_sprint
        previous_records = [r for r in records if r["sprint"] == previous_sprint]
        comparison_source = "données live"
    current_metrics = metrics(current_records)
    previous_metrics = metrics(previous_records)
    def comparison_row(sprint: str, rows: list[dict], data_type: str) -> dict:
        m = metrics(rows)
        return {
            "sprint": sprint,
            "typeDonnee": data_type,
            "semaines": sorted({r["semaine"] for r in rows}, key=week_key),
            **m,
        }
    history = []
    for sprint in sprints:
        rows = [r for r in records if r["sprint"] == sprint]
        m = metrics(rows)
        history.append({
            "sprint": sprint,
            "semaine": " / ".join(sorted({r["semaine"] for r in rows}, key=week_key)),
            "flux": m["fluxTotal"],
            "pretTester": m["fluxLivresTotal"],
            "nonPret": m["fluxEnCoursTotal"] + m["fluxBloquesTotal"],
            "bugsBloquants": m["fluxBloquesTotal"],
            "sante": "Vert" if m["tauxPret"] >= 80 else ("Orange" if m["tauxPret"] >= 60 else "Rouge"),
        })
    anomalies = []
    for r in records:
        if r.get("type") == "Anomalie" or r.get("etatAnomalie") == "KO":
            anomalies.append({
                "reference": r.get("reference") or r.get("jira_key") or "",
                "flux": r.get("id") or "",
                "domaine": r.get("domaine") or "Non classé",
                "sousDomaine": r.get("sousDomaine") or "Non classé",
                "environnement": r.get("environnement") or "",
                "statut": "Ouverte" if r.get("etatAnomalie") == "KO" else (r.get("statut") or r.get("etatAnomalie") or ""),
                "severite": r.get("severite") or "Non renseignée",
                "resume": r.get("commentaire") or "",
                "sprint": r.get("sprint") or "",
                "semaine": r.get("semaine") or "",
            })
    return {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "versionCalcul": VERSION_CALCUL,
        "source": data.get("source_type") or data.get("source") or "multisources",
        "semaineCourante": current_weeks[-1],
        "sprintCourant": current_sprint,
        "semainesSprint": current_weeks,
        "comparisonSource": comparison_source,
        "kpis": {
            "flux": current_metrics["fluxTotal"],
            "pretTester": current_metrics["fluxLivresTotal"],
            "nonPret": current_metrics["fluxEnCoursTotal"] + current_metrics["fluxBloquesTotal"],
            "bugsBloquants": current_metrics["fluxBloquesTotal"],
            "testsKoBloques": current_metrics["anomalies"],
            "tauxPret": current_metrics["tauxPret"],
        },
        "tendanceHebdo": {"rows": history},
        "comparaisonSprints": [
            comparison_row(previous_sprint, previous_records, "N-1 validé" if comparison_source.startswith("archive") else "N-1 live"),
            comparison_row(current_sprint, current_records, "Réel"),
        ],
        "anomaliesDetail": anomalies,
        "records": records,
    }


def render_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang=\"fr\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Dashboard GIL dynamique</title>
<style>
:root{{--n:#17324d;--b:#2878b5;--g:#16a264;--r:#cc3b3b;--a:#e89a18;--m:#667589;--l:#dce4ea}}
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6f8;color:#182331;font-family:Segoe UI,Arial,sans-serif}}header{{background:linear-gradient(120deg,var(--n),#27638e);color:white;padding:22px}}main,.in{{max-width:1400px;margin:auto}}h1{{margin:0}}header p{{margin:6px 0 0;color:#d9e8f4}}main{{padding:18px}}.actions{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}}button{{border:1px solid var(--l);background:#fff;padding:10px 12px;border-radius:8px;font-weight:700;cursor:pointer}}button.primary{{background:var(--n);color:white}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}.card,.panel{{background:#fff;border:1px solid var(--l);border-radius:13px;padding:16px;box-shadow:0 1px 2px #00000010}}.kpi span{{display:block;color:var(--m);font-size:12px;text-transform:uppercase;font-weight:700}}.kpi b{{font-size:30px}}.green{{color:var(--g)}}.red{{color:var(--r)}}.amber{{color:var(--a)}}h2{{margin:24px 0 10px}}table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--l);border-radius:13px;overflow:hidden}}th{{background:var(--n);color:white;text-align:left}}th,td{{padding:10px;border-bottom:1px solid #e9eef1;font-size:13px;vertical-align:top}}.bar{{height:12px;background:#edf1f4;border-radius:99px;overflow:hidden}}.fill{{height:100%;background:var(--b)}}.small{{color:var(--m);font-size:12px}}details summary{{cursor:pointer;font-weight:700}}.env{{display:inline-block;padding:3px 7px;border-radius:99px;background:#eef3f7;margin-right:4px;font-size:11px;font-weight:700}}pre{{white-space:pre-wrap;background:#13283b;color:#e8f2f8;padding:12px;border-radius:10px;max-height:180px;overflow:auto}}
</style>
</head>
<body>
<header><div class=\"in\"><h1>Dashboard GIL dynamique</h1><p id=\"sub\"></p></div></header>
<main>
<div class=\"actions\">
<button class=\"primary\" onclick=\"runAction('excel')\">Importer Excel</button>
<button class=\"primary\" onclick=\"runAction('confluence')\">Importer Confluence</button>
<button class=\"primary\" onclick=\"runAction('jira')\">Importer JIRA</button>
<button onclick=\"runAction('sync')\">Synchroniser les 3</button>
<button onclick=\"runAction('archive')\">Valider / Archiver Sprint</button>
<button onclick=\"window.print()\">Générer PDF</button>
<button onclick=\"location.reload()\">Rafraîchir</button>
</div>
<div id=\"app\"></div>
<h2>Journal des actions locales</h2><pre id=\"log\">Démarre Lancer_Dashboard.cmd pour activer les boutons d'import.</pre>
</main>
<script>
const fallbackData = {data};
let currentData = fallbackData;
function esc(x){{return String(x??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c]));}}
function sum(items){{return (items||[]).reduce((s,x)=>s+Number(x.nombre||0),0);}}
function envDetails(items){{return ['SIT','UAT'].map(env=>{{const xs=(items||[]).filter(x=>x.environnement===env);return `<details><summary><span class=env>${{env}}</span> ${{sum(xs)}}</summary>${{xs.length?'<ul>'+xs.map(x=>`<li>${{esc(x.domaine)}} / ${{esc(x.sousDomaine)}} — ${{esc(x.flux||x.reference)}} — ${{esc(x.statutSource||x.statut)}} </li>`).join('')+'</ul>':'Aucun élément'}}</details>`}}).join('');}}
function render(){{
 const d=currentData,k=d.kpis||{{}},rows=d.comparaisonSprints||[];
 document.getElementById('sub').textContent=`${{d.sprintCourant||''}} · ${{(d.semainesSprint||[]).join(' / ')}} · généré le ${{d.generatedAt||''}}`;
 const app=document.getElementById('app');
 app.innerHTML=`<div class=grid>
  <div class='card kpi'><span>Flux / demandes total</span><b>${{k.flux||0}}</b></div>
  <div class='card kpi'><span>Flux livrés</span><b class=green>${{k.pretTester||0}}</b></div>
  <div class='card kpi'><span>Flux en cours</span><b class=amber>${{(k.nonPret||0)-(k.bugsBloquants||0)}}</b></div>
  <div class='card kpi'><span>Bloqués / rejetés</span><b class=red>${{k.bugsBloquants||0}}</b></div>
  <div class='card kpi'><span>Taux livré</span><b>${{k.tauxPret||0}}%</b></div>
 </div>
 <h2>Comparaison Sprint N / N-1 <span class=small>(${{esc(d.comparisonSource||'')}})</span></h2>
 <table><thead><tr><th>Sprint</th><th>Type</th><th>Total</th><th>Livrés</th><th>En cours</th><th>Bloqués / rejetés</th></tr></thead><tbody>${{rows.map(r=>`<tr><td><b>${{esc(r.sprint)}}</b><br><span class=small>${{esc((r.semaines||[]).join(' / '))}}</span></td><td>${{esc(r.typeDonnee)}}</td><td>${{envDetails(r.fluxTotalDetail)}}</td><td>${{envDetails(r.fluxLivresDetail)}}</td><td>${{envDetails(r.fluxEnCoursDetail)}}</td><td>${{envDetails(r.fluxBloquesDetail)}}</td></tr>`).join('')}}</tbody></table>
 <h2>Graphique flux</h2>
 <div class=panel>${{rows.map(r=>{{let max=Math.max(r.fluxTotal||1,1);return `<p><b>${{esc(r.sprint)}}</b></p>`+[['Total',r.fluxTotal],['Livrés',r.fluxLivresTotal],['En cours',r.fluxEnCoursTotal],['Bloqués / rejetés',r.fluxBloquesTotal]].map(x=>`<div class=small>${{x[0]}} · ${{x[1]||0}}</div><div class=bar><div class=fill style='width:${{((x[1]||0)*100/max).toFixed(0)}}%'></div></div>`).join('')}}).join('')}}</div>
 <h2>Anomalies séparées</h2>
 <table><thead><tr><th>Sprint</th><th>Référence</th><th>Flux</th><th>Domaine</th><th>Env.</th><th>Statut</th><th>Résumé</th></tr></thead><tbody>${{(d.anomaliesDetail||[]).map(a=>`<tr><td>${{esc(a.sprint)}}</td><td>${{esc(a.reference)}}</td><td>${{esc(a.flux)}}</td><td>${{esc(a.domaine)}} / ${{esc(a.sousDomaine)}}</td><td>${{esc(a.environnement)}}</td><td>${{esc(a.statut)}}</td><td>${{esc(a.resume)}}</td></tr>`).join('')||'<tr><td colspan=7>Aucune anomalie déclarée.</td></tr>'}}</tbody></table>`;
}}
async function runAction(name){{
 const log=document.getElementById('log');
 if(location.protocol==='file:'){{log.textContent='Boutons actifs uniquement via Lancer_Dashboard.cmd : http://127.0.0.1:8765/';return;}}
 log.textContent='Action en cours : '+name+'...';
 try{{const r=await fetch('/action/'+encodeURIComponent(name),{{method:'POST'}});const t=await r.text();log.textContent=t;if(r.ok && ['sync','archive','generate','excel','jira','confluence'].includes(name)) setTimeout(()=>location.reload(),1200);}}
 catch(e){{log.textContent='Erreur action locale : '+e;}}
}}
render();
</script>
</body></html>"""


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT, text=True).strip()
    except Exception:
        return ""


def main():
    if not SOURCE.exists():
        raise SystemExit("Source commun/dashboard_gil_data.json introuvable. Lancez un import ou Synchroniser_Tout.cmd.")
    data = read_json(SOURCE, {}) or {}
    payload = build_payload(data)
    payload["commitGit"] = git_commit()
    write_json(ROOT / "rapport_gil_v6_w28_data.json", payload)
    html = render_html(payload)
    HTML.write_text(html, encoding="utf-8")
    LEGACY_HTML.write_text(html, encoding="utf-8")
    print(f"Dashboard généré : {HTML}")
    print(f"Compatibilité : {LEGACY_HTML}")
    print(f"Sprint courant : {payload['sprintCourant']} - {payload['kpis']['pretTester']}/{payload['kpis']['flux']} livrés")


if __name__ == "__main__":
    main()
