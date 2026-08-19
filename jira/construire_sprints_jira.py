
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRUT = ROOT / "jira_brut.json"
DIAG = ROOT / "jira_diagnostic.json"
OUT = ROOT / "sprints_dashboard.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def sval(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def norm(value) -> str:
    return sval(value).casefold()


def sprint_sort_value(s: dict) -> tuple:
    for key in ["endDate", "completeDate", "startDate"]:
        value = sval(s.get(key))
        if value:
            return (1, value)
    try:
        return (0, int(s.get("id") or 0))
    except Exception:
        return (0, 0)


def parse_sprint_string(text: str):
    text = sval(text)
    if not text:
        return None

    def get(key):
        marker = key + "="
        start = text.find(marker)
        if start < 0:
            return ""
        start += len(marker)
        end = text.find(",", start)
        if end < 0:
            end = text.find("]", start)
        if end < 0:
            end = len(text)
        return text[start:end].strip()

    name = get("name")
    if not name and "Sprint" not in text:
        return None

    return {
        "id": get("id"),
        "nom": name or text,
        "etat": get("state"),
        "startDate": get("startDate"),
        "endDate": get("endDate"),
        "completeDate": get("completeDate"),
    }


def parse_sprint_entry(value):
    if value is None:
        return None

    if isinstance(value, str):
        return parse_sprint_string(value)

    if isinstance(value, dict):
        name = value.get("name") or value.get("nom") or value.get("sprintName")
        sid = value.get("id") or value.get("sprintId") or ""
        if not name and not sid:
            return None
        return {
            "id": sval(sid),
            "nom": sval(name or sid),
            "etat": sval(value.get("state") or value.get("etat")),
            "startDate": sval(value.get("startDate") or value.get("start_date")),
            "endDate": sval(value.get("endDate") or value.get("end_date")),
            "completeDate": sval(value.get("completeDate") or value.get("complete_date")),
        }

    return None


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def merge_names(searches):
    names = {}
    for search in searches:
        if isinstance(search, dict):
            names.update(search.get("names") or {})
    return names


def find_sprint_fields(names: dict):
    ids = []
    for field_id, label in (names or {}).items():
        if "sprint" in norm(label):
            ids.append(field_id)
    return ids


def issue_sprints(issue: dict, names: dict):
    fields = issue.get("fields") or {}
    candidates = []

    for field_id in find_sprint_fields(names):
        if field_id in fields:
            candidates.append(fields.get(field_id))

    # Fallback : Jira stocke souvent Sprint dans un customfield_xxxxx.
    for field_id, value in fields.items():
        if not str(field_id).startswith("customfield_"):
            continue
        dumped = json.dumps(value, ensure_ascii=False, default=str)
        if "Sprint" in dumped or "com.atlassian.greenhopper" in dumped:
            candidates.append(value)

    sprints = []
    seen = set()

    for candidate in candidates:
        for item in as_list(candidate):
            sprint = parse_sprint_entry(item)
            if not sprint:
                continue
            key = sprint.get("id") or sprint.get("nom")
            if key and key not in seen:
                seen.add(key)
                sprints.append(sprint)

    return sprints


def issue_type(issue: dict) -> str:
    fields = issue.get("fields") or {}
    issue_type_value = fields.get("issuetype")
    if isinstance(issue_type_value, dict):
        return sval(issue_type_value.get("name"))
    return sval(issue_type_value)


def is_anomaly(issue: dict) -> bool:
    t = norm(issue_type(issue))
    return "bug" in t or "anomal" in t


def issue_status(issue: dict) -> str:
    fields = issue.get("fields") or {}
    status = fields.get("status")
    if isinstance(status, dict):
        return sval(status.get("name"))
    return sval(status)


def anomaly_group(issue: dict) -> str:
    s = norm(issue_status(issue))
    if any(x in s for x in ["done", "closed", "clos", "résolu", "resolu", "corrig", "termin", "valid"]):
        return "resolved"
    if any(x in s for x in ["progress", "cours", "traitement", "dev"]):
        return "progress"
    return "open"


def field_by_label(issue: dict, names: dict, contains: list[str]) -> str:
    fields = issue.get("fields") or {}
    for field_id, label in (names or {}).items():
        label_norm = norm(label)
        if all(part in label_norm for part in contains):
            value = fields.get(field_id)
            if isinstance(value, dict):
                return sval(value.get("value") or value.get("name") or value.get("displayName"))
            if isinstance(value, list):
                vals = []
                for item in value:
                    if isinstance(item, dict):
                        vals.append(sval(item.get("value") or item.get("name") or item.get("displayName")))
                    else:
                        vals.append(sval(item))
                return " / ".join(v for v in vals if v)
            return sval(value)
    return ""


def components(issue: dict):
    fields = issue.get("fields") or {}
    values = []
    for c in fields.get("components") or []:
        if isinstance(c, dict):
            values.append(sval(c.get("name")))
        else:
            values.append(sval(c))
    return [v for v in values if v]


def labels(issue: dict):
    fields = issue.get("fields") or {}
    return [sval(x) for x in fields.get("labels") or [] if sval(x)]


def environment(issue: dict, names: dict) -> str:
    value = field_by_label(issue, names, ["environnement"]) or field_by_label(issue, names, ["environment"])
    if value:
        up = value.upper()
        if "SIT" in up:
            return "SIT"
        if "UAT" in up:
            return "UAT"
        return value

    joined = " ".join(labels(issue)).upper()
    if "UAT" in joined:
        return "UAT"
    if "SIT" in joined:
        return "SIT"

    return "SIT"


def domain(issue: dict, names: dict) -> str:
    value = field_by_label(issue, names, ["domaine"]) or field_by_label(issue, names, ["domain"])
    if value:
        return value
    comps = components(issue)
    return comps[0] if comps else "À qualifier"


def subdomain(issue: dict, names: dict) -> str:
    value = (
        field_by_label(issue, names, ["sous", "domaine"])
        or field_by_label(issue, names, ["sub", "domain"])
        or field_by_label(issue, names, ["chaine"])
        or field_by_label(issue, names, ["chaîne"])
    )
    if value:
        return value
    comps = components(issue)
    return comps[1] if len(comps) > 1 else "À qualifier"


def assignee(issue: dict) -> str:
    fields = issue.get("fields") or {}
    a = fields.get("assignee")
    if isinstance(a, dict):
        return sval(a.get("displayName") or a.get("name") or a.get("emailAddress"))
    return ""


def priority(issue: dict) -> str:
    fields = issue.get("fields") or {}
    p = fields.get("priority")
    if isinstance(p, dict):
        return sval(p.get("name"))
    return sval(p)


def versions(issue: dict) -> str:
    fields = issue.get("fields") or {}
    out = []
    for key in ["fixVersions", "versions"]:
        for item in fields.get(key) or []:
            if isinstance(item, dict):
                out.append(sval(item.get("name")))
            else:
                out.append(sval(item))
    return " / ".join(v for v in out if v)


def issue_detail(issue: dict, names: dict, sprint_name: str) -> dict:
    fields = issue.get("fields") or {}
    summary = sval(fields.get("summary"))
    return {
        "reference": issue.get("key"),
        "flux": issue.get("key"),
        "domaine": domain(issue, names),
        "sousDomaine": subdomain(issue, names),
        "environnement": environment(issue, names),
        "statut": issue_status(issue),
        "partenaire": assignee(issue) or "Non renseigné",
        "responsable": assignee(issue) or "Non renseigné",
        "version": versions(issue),
        "severite": priority(issue) or "Non renseignée",
        "summary": summary,
        "sprint": sprint_name,
        "nombre": 1,
    }


def add_issue_to_bucket(buckets: dict, sprint: dict, issue: dict, names: dict):
    key = sval(sprint.get("id") or sprint.get("nom"))
    if not key:
        return

    if key not in buckets:
        buckets[key] = {
            "id": sval(sprint.get("id")),
            "nom": sval(sprint.get("nom")),
            "etat": sval(sprint.get("etat")),
            "startDate": sval(sprint.get("startDate")),
            "endDate": sval(sprint.get("endDate")),
            "completeDate": sval(sprint.get("completeDate")),
            "cles": [],
            "clesFlux": [],
            "clesAnomalies": [],
            "issues": [],
        }

    bucket = buckets[key]
    issue_key = issue.get("key")

    if issue_key and issue_key not in bucket["cles"]:
        bucket["cles"].append(issue_key)
        bucket["issues"].append(issue)

    if is_anomaly(issue):
        if issue_key and issue_key not in bucket["clesAnomalies"]:
            bucket["clesAnomalies"].append(issue_key)
    else:
        if issue_key and issue_key not in bucket["clesFlux"]:
            bucket["clesFlux"].append(issue_key)


def enrich_bucket_counts(bucket: dict):
    bucket["total"] = len(bucket.get("cles") or [])
    bucket["flux"] = len(bucket.get("clesFlux") or [])
    bucket["anomalies"] = len(bucket.get("clesAnomalies") or [])
    return bucket


def bucket_signature(bucket: dict) -> str:
    return sval(bucket.get("id") or bucket.get("nom"))


def pick_current(buckets: list[dict]):
    active = [b for b in buckets if any(x in norm(b.get("etat")) for x in ["active", "open", "ouvert"])]
    if active:
        return sorted(active, key=sprint_sort_value, reverse=True)[0]
    return sorted(buckets, key=sprint_sort_value, reverse=True)[0] if buckets else None


def pick_previous(buckets: list[dict], current: dict | None):
    if not buckets:
        return None
    current_key = bucket_signature(current or {})
    candidates = [b for b in buckets if bucket_signature(b) != current_key]
    return sorted(candidates, key=sprint_sort_value, reverse=True)[0] if candidates else None


def comparison_row(bucket: dict, names: dict, type_donnee: str) -> dict:
    sprint_name = bucket.get("nom") or "Sprint non détecté"

    flux_details = []
    open_anomalies = []
    resolved_anomalies = []
    progress_anomalies = []

    for issue in bucket.get("issues") or []:
        detail = issue_detail(issue, names, sprint_name)

        if is_anomaly(issue):
            group = anomaly_group(issue)
            if group == "resolved":
                resolved_anomalies.append(detail)
            elif group == "progress":
                progress_anomalies.append(detail)
            else:
                open_anomalies.append(detail)
        else:
            flux_details.append(detail)

    known_issue_keys = {d.get("reference") for d in flux_details + open_anomalies + resolved_anomalies + progress_anomalies}

    for key in bucket.get("clesFlux") or []:
        if key not in known_issue_keys:
            flux_details.append({
                "reference": key,
                "flux": key,
                "domaine": "À qualifier",
                "sousDomaine": "À qualifier",
                "environnement": "SIT",
                "statut": "Non renseigné",
                "partenaire": "Non renseigné",
                "version": "",
                "sprint": sprint_name,
                "nombre": 1,
            })

    for key in bucket.get("clesAnomalies") or []:
        if key not in known_issue_keys:
            open_anomalies.append({
                "reference": key,
                "flux": key,
                "domaine": "À qualifier",
                "sousDomaine": "À qualifier",
                "environnement": "SIT",
                "statut": "Non renseigné",
                "partenaire": "Non renseigné",
                "version": "",
                "severite": "Non renseignée",
                "sprint": sprint_name,
                "nombre": 1,
            })

    total_flux = len(flux_details)
    total_anomalies = len(open_anomalies) + len(resolved_anomalies) + len(progress_anomalies)

    return {
        "sprint": sprint_name,
        "typeDonnee": type_donnee,
        "semaines": [sprint_name],
        "flux": total_flux,
        "pretTester": total_flux,
        "nonPret": 0,
        "bugsBloquants": len(open_anomalies),
        "servicesRisque": 0,
        "testsKoBloques": 0,
        "prioritesTraitees": total_flux,
        "sante": "Vert",
        "faitMarquant": "Jira — diagnostic sprint dynamique",
        "risque": f"{total_anomalies} anomalie(s) détectée(s)",
        "fluxLivresDetail": flux_details,
        "anomaliesOuvertesDetail": open_anomalies,
        "anomaliesResoluesDetail": resolved_anomalies,
        "anomaliesEnCoursDetail": progress_anomalies,
        "sousDomainesRisqueDetail": [],
        "fluxLivresTotal": len(flux_details),
        "anomaliesOuvertesTotal": len(open_anomalies),
        "anomaliesResoluesTotal": len(resolved_anomalies),
        "anomaliesEnCoursTotal": len(progress_anomalies),
        "sousDomainesRisqueTotal": 0,
    }


def main() -> int:
    print()
    print("============================================================")
    print("[2/5] ANALYSE DYNAMIQUE DES SPRINTS JIRA")
    print("============================================================")

    if not BRUT.exists():
        print("[ERREUR BLOQUANTE] jira_brut.json absent.")
        return 1

    raw = load_json(BRUT)
    searches = raw.get("recherches") or []
    names = merge_names(searches)

    issues_by_key = {}
    for search in searches:
        for issue in search.get("issues") or []:
            if issue.get("key"):
                issues_by_key[issue["key"]] = issue

    print("Tickets Jira disponibles :", len(issues_by_key))

    buckets_map = {}

    for issue in issues_by_key.values():
        sprints = issue_sprints(issue, names)
        for sprint in sprints:
            add_issue_to_bucket(buckets_map, sprint, issue, names)

    buckets = [enrich_bucket_counts(b) for b in buckets_map.values()]
    buckets = sorted(buckets, key=sprint_sort_value, reverse=True)

    raw_diag = raw.get("diagnostic_sprints") or {}
    diag_current = raw_diag.get("courant") or {}
    diag_previous = raw_diag.get("precedent") or {}

    current = None
    previous = None

    if diag_current.get("nom"):
        current = next((b for b in buckets if bucket_signature(b) == bucket_signature(diag_current) or b.get("nom") == diag_current.get("nom")), None)
        if not current:
            current = enrich_bucket_counts({
                "id": diag_current.get("id", ""),
                "nom": diag_current.get("nom"),
                "etat": diag_current.get("etat", ""),
                "startDate": diag_current.get("startDate", ""),
                "endDate": diag_current.get("endDate", ""),
                "completeDate": diag_current.get("completeDate", ""),
                "cles": diag_current.get("cles", []),
                "clesFlux": diag_current.get("clesFlux", []),
                "clesAnomalies": diag_current.get("clesAnomalies", []),
                "issues": [issues_by_key[k] for k in diag_current.get("cles", []) if k in issues_by_key],
            })

    if diag_previous.get("nom"):
        previous = next((b for b in buckets if bucket_signature(b) == bucket_signature(diag_previous) or b.get("nom") == diag_previous.get("nom")), None)
        if not previous:
            previous = enrich_bucket_counts({
                "id": diag_previous.get("id", ""),
                "nom": diag_previous.get("nom"),
                "etat": diag_previous.get("etat", ""),
                "startDate": diag_previous.get("startDate", ""),
                "endDate": diag_previous.get("endDate", ""),
                "completeDate": diag_previous.get("completeDate", ""),
                "cles": diag_previous.get("cles", []),
                "clesFlux": diag_previous.get("clesFlux", []),
                "clesAnomalies": diag_previous.get("clesAnomalies", []),
                "issues": [issues_by_key[k] for k in diag_previous.get("cles", []) if k in issues_by_key],
            })

    if current is None:
        current = pick_current(buckets)

    if previous is None:
        previous = pick_previous(buckets, current)

    if not current or not current.get("nom"):
        print("[ERREUR BLOQUANTE] Sprint courant non détecté depuis Jira.")
        print("Cause probable : champ Sprint absent des tickets récupérés ou requête openSprints en erreur.")
        return 1

    if not previous or not previous.get("nom"):
        print("[ERREUR BLOQUANTE] Sprint précédent non détecté depuis Jira.")
        print("Cause probable : aucune donnée closedSprints exploitable ou champ Sprint absent.")
        return 1

    comparison = [
        comparison_row(previous, names, "Sprint précédent"),
        comparison_row(current, names, "Sprint courant"),
    ]

    output = {
        "schema_version": "1.0",
        "source": "jira_brut.json",
        "projectKey": raw.get("project_key") or raw_diag.get("projectKey") or "",
        "courant": {k: current.get(k) for k in ["id", "nom", "etat", "startDate", "endDate", "completeDate", "total", "flux", "anomalies", "cles", "clesFlux", "clesAnomalies"]},
        "precedent": {k: previous.get(k) for k in ["id", "nom", "etat", "startDate", "endDate", "completeDate", "total", "flux", "anomalies", "cles", "clesFlux", "clesAnomalies"]},
        "sprints": [{k: b.get(k) for k in ["id", "nom", "etat", "startDate", "endDate", "completeDate", "total", "flux", "anomalies", "cles", "clesFlux", "clesAnomalies"]} for b in buckets],
        "comparaisonSprints": comparison,
    }

    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    if DIAG.exists():
        try:
            diag = load_json(DIAG)
        except Exception:
            diag = {}
    else:
        diag = {}

    diag["sprints"] = {
        "projectKey": output.get("projectKey"),
        "courant": output["courant"],
        "precedent": output["precedent"],
        "sprintsCourants": [output["courant"]],
        "sprintsFermes": [s for s in output["sprints"] if s.get("nom") != output["courant"].get("nom")],
        "source": "sprints_dashboard.json",
    }

    DIAG.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Sprint courant   :", output["courant"]["nom"], "| flux:", output["courant"].get("flux"), "| anomalies:", output["courant"].get("anomalies"))
    print("Sprint précédent :", output["precedent"]["nom"], "| flux:", output["precedent"].get("flux"), "| anomalies:", output["precedent"].get("anomalies"))
    print("Comparaison      :", len(output["comparaisonSprints"]), "ligne(s)")
    print("Fichier produit  :", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
