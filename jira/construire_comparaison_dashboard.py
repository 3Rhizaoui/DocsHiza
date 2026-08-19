from pathlib import Path
import datetime as dt
import json

ROOT = Path(__file__).resolve().parents[1]
JIRA = ROOT / "jira"

PREV = JIRA / "sprints" / "sprint_precedent.json"
CUR = JIRA / "sprints" / "sprint_courant.json"

OUT = JIRA / "presentation" / "comparaison_sprints.json"
OUT_ALIAS = JIRA / "comparaison_sprints.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def to_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def excel_serial(day: dt.date) -> int:
    return (day - dt.date(1899, 12, 30)).days


def iso_week(day: dt.date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def txt(value):
    if value is None:
        return ""
    return str(value)


def norm_env(item):
    env = (
        ((item.get("champsMetier") or {}).get("environnement"))
        or item.get("environnement")
        or ""
    )
    env = txt(env).upper()

    if "UAT" in env:
        return "UAT"
    if "SIT" in env:
        return "SIT"

    # Compatibilité avec le HTML existant : il sait afficher SIT/UAT.
    # L'absence de vraie ventilation reste visible via nonVentile.
    return "SIT"


def status_text(item):
    return " ".join([
        txt(item.get("status")),
        txt(item.get("statut")),
        txt(item.get("statusCategory")),
        txt(item.get("statutJira")),
    ]).lower()


def is_delivered(item):
    s = status_text(item)
    return any(x in s for x in [
        "done", "livré", "livre", "terminé", "termine",
        "validé", "valide", "résolu", "resolu", "closed", "clos"
    ])


def is_blocked(item):
    s = status_text(item)
    return any(x in s for x in [
        "bloqué", "bloque", "blocked", "ko", "rejeté", "rejete", "rejected"
    ])


def detail(item, sprint_name, week, statut):
    champs = item.get("champsMetier") or {}

    key = item.get("key") or item.get("jiraKey") or ""
    summary = item.get("summary") or item.get("resume") or key or "Ticket Jira"
    version = item.get("version") or ""

    if not version and isinstance(item.get("fixVersions"), list):
        version = " / ".join([txt(x) for x in item.get("fixVersions") if x])

    return {
        "reference": key or summary,
        "flux": item.get("flux") or key or summary,
        "jiraKey": key,
        "domaine": champs.get("domaine") or item.get("domaine") or "Jira",
        "sousDomaine": champs.get("sousDomaine") or item.get("sousDomaine") or "Sprint",
        "environnement": norm_env(item),
        "statut": statut,
        "statutSource": item.get("status") or item.get("statut") or "",
        "partenaire": item.get("assignee") or item.get("reporter") or "",
        "nombre": 1,
        "version": version,
        "resume": summary,
        "description": item.get("description") or "",
        "url": item.get("url") or "",
        "sprint": sprint_name,
        "semaine": week,
        "source": "Jira",
    }


def synthetic_total_detail(sprint_name, week, total):
    return {
        "reference": "Total Jira Agile",
        "flux": "Tickets du sprint",
        "jiraKey": "",
        "domaine": "Jira",
        "sousDomaine": "Sprint",
        "environnement": "SIT",
        "statut": "Total",
        "statutSource": "Total sprint officiel",
        "partenaire": "",
        "nombre": total,
        "version": "",
        "resume": "Total issu du sprint Jira officiel",
        "description": "",
        "url": "",
        "sprint": sprint_name,
        "semaine": week,
        "source": "Jira Agile API",
    }


def score_health(total, delivered, blocked):
    if total <= 0:
        score = 100
    else:
        score = round((delivered / total) * 100 - min(35, blocked * 3))

    score = max(0, min(100, score))

    if score >= 80:
        return "Vert"
    if score >= 60:
        return "Orange"
    return "Rouge"


def build_row(doc, role, week):
    sprint = doc.get("sprint") or {}
    stats = doc.get("statistiques") or {}

    sprint_name = sprint.get("nom") or sprint.get("name") or (
        "Sprint précédent" if role == "precedent" else "Sprint courant"
    )

    raw_items = doc.get("flux") or doc.get("tickets") or []
    raw_items = [x for x in raw_items if isinstance(x, dict)]

    total_official = to_int(stats.get("flux"), to_int(stats.get("total"), len(raw_items)))
    anomalies = to_int(stats.get("anomalies"), 0)

    total_details = []
    delivered_details = []
    in_progress_details = []
    blocked_details = []

    for item in raw_items:
        total_details.append(detail(item, sprint_name, week, "Total"))

        if is_blocked(item):
            blocked_details.append(detail(item, sprint_name, week, "Bloqué"))
        elif is_delivered(item):
            delivered_details.append(detail(item, sprint_name, week, "Livré"))
        else:
            in_progress_details.append(detail(item, sprint_name, week, "En cours"))

    total_from_details = sum(to_int(x.get("nombre")) for x in total_details)

    if total_official > total_from_details:
        total_details.append(
            synthetic_total_detail(sprint_name, week, total_official - total_from_details)
        )

    if not total_details and total_official:
        total_details.append(synthetic_total_detail(sprint_name, week, total_official))

    flux_total = sum(to_int(x.get("nombre")) for x in total_details)
    flux_livres = sum(to_int(x.get("nombre")) for x in delivered_details)
    flux_en_cours = sum(to_int(x.get("nombre")) for x in in_progress_details)
    flux_bloques = sum(to_int(x.get("nombre")) for x in blocked_details)

    non_ventile = 0
    if not raw_items and flux_total:
        non_ventile = flux_total

    sante = score_health(flux_total, flux_livres, flux_bloques)

    today = dt.date.today()

    return {
        "semaine": week,
        "dateRapport": excel_serial(today),
        "flux": flux_total,
        "pretTester": flux_livres,
        "nonPret": max(0, flux_total - flux_livres),
        "bugsBloquants": flux_bloques,
        "servicesRisque": 0,
        "testsKoBloques": flux_bloques,
        "prioritesTraitees": flux_livres,
        "sante": sante,
        "faitMarquant": "Données Jira sprint officiel",
        "risque": f"{max(0, flux_total - flux_livres)} élément(s) non livrés ou non ventilés",
        "sprint": sprint_name,
        "typeDonnee": "Réel Jira",
        "semaines": [week],

        "fluxTotalDetail": total_details,
        "fluxLivresDetail": delivered_details,
        "fluxEnCoursDetail": in_progress_details,
        "fluxBloquesDetail": blocked_details,

        "fluxTotal": flux_total,
        "fluxLivresTotal": flux_livres,
        "fluxEnCoursTotal": flux_en_cours,
        "fluxBloquesTotal": flux_bloques,

        "anomalies": anomalies,
        "nonVentile": non_ventile,
        "ventilationMode": "DETAILS_JIRA" if raw_items else "TOTAL_OFFICIEL_NON_DETAILLE",
        "source": "jira/presentation/comparaison_sprints.json",
    }


def main():
    if not PREV.exists():
        raise SystemExit(f"[ERREUR] Fichier absent : {PREV}")
    if not CUR.exists():
        raise SystemExit(f"[ERREUR] Fichier absent : {CUR}")

    previous = load(PREV)
    current = load(CUR)

    today = dt.date.today()
    previous_week = iso_week(today - dt.timedelta(days=7))
    current_week = iso_week(today)

    rows = [
        build_row(previous, "precedent", previous_week),
        build_row(current, "courant", current_week),
    ]

    write(OUT, rows)
    write(OUT_ALIAS, rows)

    print("[OK] Comparaison dashboard compatible HTML produite :")
    print(" -", OUT)

    for row in rows:
        print(
            "-",
            row["sprint"],
            "| total:", row["fluxTotal"],
            "| livrés:", row["fluxLivresTotal"],
            "| en cours:", row["fluxEnCoursTotal"],
            "| bloqués:", row["fluxBloquesTotal"],
            "| nonVentile:", row["nonVentile"],
        )


if __name__ == "__main__":
    main()
