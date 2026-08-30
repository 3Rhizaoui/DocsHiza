from pathlib import Path
from collections import Counter
import datetime as dt
import json
import re

from gil_paths import (
    JIRA_BRUT,
    SPRINTS_DASHBOARD,
    SPRINT_COURANT,
    SPRINT_PRECEDENT,
    COMPARAISON_SPRINTS,
    KPIS_SPRINT,
    ARCHITECTURE_SPRINTS_DIAGNOSTIC,
)

OUT_PREV = SPRINT_PRECEDENT
OUT_CUR = SPRINT_COURANT
OUT_COMP = COMPARAISON_SPRINTS
OUT_KPIS = KPIS_SPRINT
OUT_DIAG = ARCHITECTURE_SPRINTS_DIAGNOSTIC


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def to_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def first_dict(*values):
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def name_of(value):
    if isinstance(value, dict):
        for key in ["displayName", "name", "value", "key", "emailAddress"]:
            if value.get(key):
                return str(value.get(key))
        return ""
    if value is None:
        return ""
    return str(value)


def list_names(value):
    if isinstance(value, list):
        return [name_of(v) for v in value if name_of(v)]
    if value:
        return [name_of(value)]
    return []


def is_issue(obj):
    if not isinstance(obj, dict):
        return False

    key = str(obj.get("key") or "")
    if key and re.match(r"^[A-Z][A-Z0-9_]+-\d+$", key):
        return True

    if "fields" in obj and ("id" in obj or "self" in obj):
        return True

    return False


def collect_issues(obj, out=None):
    if out is None:
        out = []

    if isinstance(obj, dict):
        if is_issue(obj):
            out.append(obj)

        for value in obj.values():
            collect_issues(value, out)

    elif isinstance(obj, list):
        for value in obj:
            collect_issues(value, out)

    return out


def dedupe_issues(issues):
    seen = set()
    result = []

    for issue in issues:
        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
        key = issue.get("key") or fields.get("key") or issue.get("id") or json.dumps(issue, ensure_ascii=False, sort_keys=True)[:200]

        if key in seen:
            continue

        seen.add(key)
        result.append(issue)

    return result


def get_role_summary(sprints_data, diagnostic_sprints, role):
    aliases = {
        "courant": ["courant", "current", "sprintCourant", "sprint_courant"],
        "precedent": ["precedent", "previous", "sprintPrecedent", "sprint_precedent"],
    }[role]

    src_diag = {}
    src_dash = {}

    for key in aliases:
        if isinstance(diagnostic_sprints.get(key), dict):
            src_diag = diagnostic_sprints.get(key)
            break

    for key in aliases:
        if isinstance(sprints_data.get(key), dict):
            src_dash = sprints_data.get(key)
            break

    merged = {}
    merged.update(src_diag)
    merged.update(src_dash)

    # Garder les tickets détaillés du diagnostic si le résumé dashboard ne les porte pas.
    for field in ["issues", "tickets", "items"]:
        if field not in merged and isinstance(src_diag.get(field), list):
            merged[field] = src_diag[field]

    return merged


def explicit_issues_from_summary(summary):
    issues = []

    for key in ["issues", "tickets", "items", "values"]:
        value = summary.get(key)
        if isinstance(value, list):
            issues.extend([item for item in value if is_issue(item)])

    return dedupe_issues(issues)


def issue_text(issue):
    try:
        return json.dumps(issue, ensure_ascii=False, default=str).lower()
    except Exception:
        return str(issue).lower()


def issue_matches_sprint(issue, summary):
    sprint_id = str(summary.get("id") or summary.get("sprintId") or "")
    sprint_name = str(
        summary.get("nom")
        or summary.get("name")
        or summary.get("sprint")
        or summary.get("label")
        or ""
    ).lower()

    text = issue_text(issue)

    if sprint_id and sprint_id in text:
        return True

    if sprint_name and sprint_name in text:
        return True

    return False


def select_sprint_issues(all_issues, summary):
    """
    Population officielle du sprint.

    Priorité absolue aux tickets explicitement retournés pour le sprint
    par l'API Agile Jira.

    On évite de reconstruire la population à partir d'une recherche
    textuelle globale sur le nom/id du sprint, car un ticket peut contenir
    un ancien sprint dans son historique ou dans ses champs Jira et être
    alors compté à tort dans le sprint courant.
    """
    explicit = explicit_issues_from_summary(summary)

    print(
        "[TRACE][SPRINT_SELECT]",
        "sprint=",
        summary.get("nom")
        or summary.get("name")
        or summary.get("sprint")
        or summary.get("label"),
        "explicit=",
        len(explicit),
        "all_issues=",
        len(all_issues or []),
    )

    if explicit:
        return explicit

    # Fallback historique uniquement si aucune population explicite
    # n'est disponible dans la réponse Agile.
    matched = [
        issue
        for issue in all_issues
        if issue_matches_sprint(issue, summary)
    ]

    return dedupe_issues(matched)


def normalize_issue(issue, base_url):
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}

    key = issue.get("key") or fields.get("key") or ""
    issue_type = name_of(fields.get("issuetype") or issue.get("issuetype") or issue.get("type"))
    status_obj = fields.get("status") or issue.get("status") or {}
    status_category = ""

    if isinstance(status_obj, dict):
        status_category = name_of(status_obj.get("statusCategory"))

    parent = fields.get("parent") or issue.get("parent") or {}
    priority = fields.get("priority") or issue.get("priority")
    assignee = fields.get("assignee") or issue.get("assignee")
    reporter = fields.get("reporter") or issue.get("reporter")

    description = fields.get("description") or issue.get("description") or ""
    summary = fields.get("summary") or issue.get("summary") or ""

    labels = fields.get("labels") or issue.get("labels") or []
    components = fields.get("components") or issue.get("components") or []
    fix_versions = fields.get("fixVersions") or issue.get("fixVersions") or []
    issuelinks = fields.get("issuelinks") or issue.get("issuelinks") or issue.get("links") or []

    url = f"{base_url.rstrip('/')}/browse/{key}" if key else ""

    type_lower = issue_type.lower()
    if any(token in type_lower for token in ["bug", "anomal", "défaut", "defaut"]):
        categorie = "anomalie"
    elif "epic" in type_lower:
        categorie = "epic"
    elif any(token in type_lower for token in ["task", "tâche", "tache", "story", "sub-task", "subtask"]):
        categorie = "tache"
    else:
        categorie = "flux"

    env = ""
    raw_text = issue_text(issue)
    if "uat" in raw_text:
        env = "UAT"
    elif "sit" in raw_text:
        env = "SIT"

    return {
        "key": key,
        "url": url,
        "id": issue.get("id"),
        "self": issue.get("self"),
        "type": issue_type,
        "categorie": categorie,
        "summary": summary,
        "description": description,
        "status": name_of(status_obj),
        "statusCategory": status_category,
        "assignee": name_of(assignee),
        "reporter": name_of(reporter),
        "priority": name_of(priority),
        "created": fields.get("created") or issue.get("created"),
        "updated": fields.get("updated") or issue.get("updated"),
        "resolution": name_of(fields.get("resolution") or issue.get("resolution")),
        "labels": labels if isinstance(labels, list) else list_names(labels),
        "components": list_names(components),
        "fixVersions": list_names(fix_versions),
        "parent": {
            "key": parent.get("key") if isinstance(parent, dict) else "",
            "type": name_of((parent.get("fields") or {}).get("issuetype")) if isinstance(parent, dict) else "",
            "summary": (parent.get("fields") or {}).get("summary") if isinstance(parent, dict) else "",
        },
        "links": issuelinks if isinstance(issuelinks, list) else [],
        "champsMetier": {
            "environnement": env,
            "domaine": "",
            "sousDomaine": "",
            "partenaire": "",
            "reference": "",
        },
        "raw": issue,
    }


def sprint_identity(summary, role):
    name = (
        summary.get("nom")
        or summary.get("name")
        or summary.get("sprint")
        or summary.get("label")
        or ("Sprint précédent" if role == "precedent" else "Sprint courant")
    )

    return {
        "id": summary.get("id") or summary.get("sprintId"),
        "nom": name,
        "etat": summary.get("etat") or summary.get("state"),
        "role": role,
        "board": summary.get("board") or summary.get("boardName"),
        "boardId": summary.get("boardId"),
        "dateDebut": summary.get("startDate") or summary.get("dateDebut"),
        "dateFin": summary.get("endDate") or summary.get("dateFin"),
    }


def build_sprint_document(summary, role, issues, base_url):
    normalized = [normalize_issue(issue, base_url) for issue in issues]

    epics = [i for i in normalized if i["categorie"] == "epic"]
    anomalies = [i for i in normalized if i["categorie"] == "anomalie"]
    taches = [i for i in normalized if i["categorie"] == "tache"]
    flux_items = [i for i in normalized if i["categorie"] != "anomalie"]

    official_total = to_int(summary.get("total"), len(normalized))
    official_flux = to_int(summary.get("flux"), len(flux_items))
    official_anomalies = to_int(summary.get("anomalies"), len(anomalies))

    if not official_total:
        official_total = official_flux + official_anomalies

    env_counter = Counter()
    for item in normalized:
        env = item.get("champsMetier", {}).get("environnement") or "NON_VENTILE"
        env_counter[env] += 1

    if not normalized:
        env_counter["NON_VENTILE"] = official_total

    document = {
        "schemaVersion": "1.0",
        "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "jira_agile_api",
        "sprint": sprint_identity(summary, role),
        "tickets": normalized,
        "epics": epics,
        "flux": flux_items,
        "anomalies": anomalies,
        "taches": taches,
        "statistiques": {
            "total": official_total,
            "ticketsCollectes": len(normalized),
            "flux": official_flux,
            "anomalies": official_anomalies,
            "epics": len(epics),
            "taches": len(taches),
            "environnements": dict(env_counter),
            "detailsTicketsDisponibles": len(normalized) > 0,
            "ecartTotalVsTicketsCollectes": official_total - len(normalized),
        },
    }

    return document


def presentation_row(document):
    stats = document["statistiques"]
    sprint = document["sprint"]

    total = stats["total"]
    sit = stats["environnements"].get("SIT", 0)
    uat = stats["environnements"].get("UAT", 0)
    non_ventile = stats["environnements"].get("NON_VENTILE", 0)

    # Compatibilité legacy : le graphe existant sait lire SIT/UAT.
    # Si Jira ne fournit pas encore l'environnement, on affiche le non ventilé côté SIT,
    # mais on garde nonVentile + ventilationMode pour ne pas masquer l'information.
    sit_compat = sit if (sit or uat) else non_ventile
    uat_compat = uat

    return {
        "role": sprint["role"],
        "sprint": sprint["nom"],
        "sprintId": sprint["id"],
        "total": total,
        "flux": stats["flux"],
        "anomalies": stats["anomalies"],
        "epics": stats["epics"],
        "taches": stats["taches"],
        "ticketsCollectes": stats["ticketsCollectes"],

        "sitTotal": sit_compat,
        "uatTotal": uat_compat,
        "totalSIT": sit_compat,
        "totalUAT": uat_compat,
        "fluxSIT": sit_compat,
        "fluxUAT": uat_compat,

        "nonVentile": non_ventile,
        "ventilationMode": "NON_VENTILE_COMPAT_LEGACY" if non_ventile and not (sit or uat) else "SIT_UAT",
        "detailsTicketsDisponibles": stats["detailsTicketsDisponibles"],
        "source": "jira/presentation/comparaison_sprints.json",
    }


def main():
    if not SPRINTS_DASHBOARD.exists():
        raise SystemExit(f"[ERREUR] Fichier absent : {SPRINTS_DASHBOARD}")

    sprints_data = read_json(SPRINTS_DASHBOARD, {})
    jira_brut = read_json(JIRA_BRUT, {})
    diagnostic_sprints = jira_brut.get("diagnostic_sprints") if isinstance(jira_brut, dict) else {}
    diagnostic_sprints = diagnostic_sprints if isinstance(diagnostic_sprints, dict) else {}

    base_url = (
        jira_brut.get("baseUrl")
        or jira_brut.get("base_url")
        or sprints_data.get("baseUrl")
        or "https://jira.group.echonet"
    )

    all_issues = dedupe_issues(collect_issues(jira_brut))

    previous_summary = get_role_summary(sprints_data, diagnostic_sprints, "precedent")
    current_summary = get_role_summary(sprints_data, diagnostic_sprints, "courant")

    previous_issues = select_sprint_issues(all_issues, previous_summary)
    current_issues = select_sprint_issues(all_issues, current_summary)

    previous_doc = build_sprint_document(previous_summary, "precedent", previous_issues, base_url)
    current_doc = build_sprint_document(current_summary, "courant", current_issues, base_url)

    comparison = [
        presentation_row(previous_doc),
        presentation_row(current_doc),
    ]

    kpis = {
        "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "sprintPrecedent": previous_doc["sprint"],
        "sprintCourant": current_doc["sprint"],
        "comparaison": comparison,
    }

    diagnostic = {
        "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "source": {
            "jira_brut": str(JIRA_BRUT),
            "sprints_dashboard": str(SPRINTS_DASHBOARD),
        },
        "ticketsBrutsDetectes": len(all_issues),
        "outputs": [
            str(OUT_PREV),
            str(OUT_CUR),
            str(OUT_COMP),
            str(OUT_KPIS),
        ],
    }

    write_json(OUT_PREV, previous_doc)
    write_json(OUT_CUR, current_doc)
    write_json(OUT_COMP, comparison)
    write_json(OUT_KPIS, kpis)
    write_json(OUT_DIAG, diagnostic)


    print("[OK] Architecture JSON sprint produite")
    print(" -", OUT_PREV)
    print(" -", OUT_CUR)
    print(" -", OUT_COMP)

    for row in comparison:
        print(
            "-",
            row["sprint"],
            "| total:", row["total"],
            "| flux:", row["flux"],
            "| anomalies:", row["anomalies"],
            "| SIT:", row["sitTotal"],
            "| UAT:", row["uatTotal"],
            "| nonVentile:", row["nonVentile"],
        )


if __name__ == "__main__":
    main()
