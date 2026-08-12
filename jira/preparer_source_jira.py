from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent


def text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or value.get("displayName") or value.get("key") or "")
    if isinstance(value, list):
        return " / ".join(filter(None, (text(item) for item in value)))
    return str(value)


def folded(value):
    value = unicodedata.normalize("NFKD", text(value)).encode("ascii", "ignore").decode("ascii")
    return value.casefold()


def configured(fields, field_id):
    return fields.get(field_id) if field_id else None


def named_field(fields, names, configured_id, expected_name):
    if configured_id:
        return fields.get(configured_id)
    wanted = folded(expected_name)
    for field_id, label in names.items():
        if wanted in folded(label):
            value = fields.get(field_id)
            if value not in (None, "", []):
                return value
    return None


def sprint_name(value, fallback):
    raw = text(value)
    match = re.search(r"name=([^,\]]+)", raw)
    if match:
        return match.group(1).strip()
    match = re.search(r"Sprint\s*[-_ ]?\s*(\d+)", raw, re.I)
    if match:
        return f"Sprint {match.group(1)}"
    return raw.strip() or fallback


def environment(value, fallback):
    raw = folded(value)
    found = []
    if "sit" in raw or "qua" in raw:
        found.append("SIT")
    if "uat" in raw:
        found.append("UAT")
    return found or [fallback]


def classify(issue, rules, inherited=None):
    fields = issue.get("fields") or {}
    cfg = rules["champs"]
    explicit_domain = text(configured(fields, cfg.get("domaine")))
    explicit_subdomain = text(configured(fields, cfg.get("sous_domaine")))
    domain = explicit_domain or (inherited or {}).get("domaine", "")
    subdomain = explicit_subdomain or (inherited or {}).get("sous_domaine", "")
    corpus = " ".join([
        text(fields.get("summary")), text(fields.get("description")), text(fields.get("labels")),
        text(fields.get("components")), text(fields.get("epic")), text(fields.get("parent")),
    ])
    for mapping in rules.get("mappings", []):
        if any(folded(token) in folded(corpus) for token in mapping.get("contient", [])):
            domain = domain or mapping.get("domaine", "")
            subdomain = subdomain or mapping.get("sous_domaine", "")
    defaults = rules["valeurs_par_defaut"]
    return {"domaine": domain or defaults["domaine"], "sous_domaine": subdomain or defaults["sous_domaine"]}


def parent_key(issue, epic_field):
    fields = issue.get("fields") or {}
    parent = fields.get("parent") or {}
    if isinstance(parent, dict) and parent.get("key"):
        return parent["key"]
    epic = fields.get(epic_field) if epic_field else None
    if isinstance(epic, dict):
        return epic.get("key", "")
    return text(epic)


def is_resolved(fields, rules):
    status = text(fields.get("status"))
    category = text((fields.get("status") or {}).get("statusCategory") if isinstance(fields.get("status"), dict) else "")
    resolution = text(fields.get("resolution"))
    corpus = folded(" ".join([status, category, resolution]))
    return any(folded(item) in corpus for item in rules.get("statuts_resolus", [])) or folded(category) == "done"


def main():
    parser = argparse.ArgumentParser(description="Normalise un export JIRA SSO pour le dashboard GIL commun.")
    parser.add_argument("--input", default=ROOT / "jira_brut.json", type=Path)
    parser.add_argument("--rules", default=ROOT / "regles_domaines.json", type=Path)
    parser.add_argument("--output", default=ROOT / "dashboard_gil_data.json", type=Path)
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8-sig"))
    rules = json.loads(args.rules.read_text(encoding="utf-8-sig"))
    names = raw.get("names") or {}
    issues_by_key = {}
    searches = raw.get("recherches") or raw.get("searches") or []
    for search in searches:
        names.update(search.get("names") or {})
        for issue in search.get("issues") or []:
            if issue.get("key"):
                issues_by_key[issue["key"]] = issue
    for issue in raw.get("issues") or []:
        if issue.get("key"):
            issues_by_key[issue["key"]] = issue
    if not issues_by_key:
        raise SystemExit("Aucun ticket JIRA trouvé dans jira_brut.json.")

    cfg = rules["champs"]
    defaults = rules["valeurs_par_defaut"]
    epic_types = {folded(x) for x in rules["types"]["epic"]}
    bug_types = {folded(x) for x in rules["types"]["bug"]}
    classifications = {}
    for key, issue in issues_by_key.items():
        fields = issue.get("fields") or {}
        if folded(text(fields.get("issuetype"))) in epic_types:
            classifications[key] = classify(issue, rules)
    for key, issue in issues_by_key.items():
        inherited = classifications.get(parent_key(issue, cfg.get("epic_link")))
        classifications[key] = classify(issue, rules, inherited)

    source_urls = [x.get("url", "") for x in searches if x.get("url")]
    origin = ""
    if source_urls:
        part = urlsplit(source_urls[0])
        origin = f"{part.scheme}://{part.netloc}"
    iso = datetime.now().isocalendar()
    default_week = f"{iso.year}-W{iso.week:02d}"
    records, epics, taches, anomalies = [], [], [], []

    for key, issue in sorted(issues_by_key.items()):
        fields = issue.get("fields") or {}
        issue_type = text(fields.get("issuetype")) or "Ticket"
        status = text(fields.get("status")) or "Inconnu"
        resolved = is_resolved(fields, rules)
        classification = classifications[key]
        sprint = sprint_name(named_field(fields, names, cfg.get("sprint"), "Sprint"), defaults["sprint"])
        envs = environment(named_field(fields, names, cfg.get("environnement"), "Environnement"), defaults["environnement"])
        severity = text(named_field(fields, names, cfg.get("severite"), "Sévérité") or fields.get("priority"))
        responsible = text(fields.get("assignee")) or text(fields.get("reporter")) or "Non affecté"
        parent = parent_key(issue, cfg.get("epic_link"))
        url = f"{origin}/browse/{key}" if origin else key
        is_bug = folded(issue_type) in bug_types
        for env in envs:
            record = {
                "id": f"JIRA-{key}-{env}", "reference": key, "type": "Anomalie" if is_bug else issue_type,
                "domaine": classification["domaine"], "sousDomaine": classification["sous_domaine"],
                "environnement": env, "semaine": default_week, "sprint": sprint,
                # Une anomalie corrigée ne doit jamais augmenter le compteur des flux livrés.
                "etatFlux": "" if is_bug else ("Prêt" if resolved else "En cours"),
                "etatAnomalie": ("Corrigée" if resolved else "KO") if is_bug else "",
                "statut": status, "version": text(fields.get("fixVersions")), "nombre": 1,
                "commentaire": text(fields.get("summary")), "source": "JIRA SSO", "date": text(fields.get("updated")),
                "nature": issue_type, "url_source": url, "responsable": responsible, "severite": severity,
                "epic_parent": parent
            }
            records.append(record)
        item = {
            "cle": key, "resume": text(fields.get("summary")), "type": issue_type, "statut": status,
            "domaine": classification["domaine"], "sous_domaine": classification["sous_domaine"],
            "epic_parent": parent, "sprint": sprint, "responsable": responsible, "severite": severity, "url": url
        }
        if folded(issue_type) in epic_types:
            epics.append(item)
        elif is_bug:
            anomalies.append(item)
        else:
            taches.append(item)

    payload = {
        "schema_version": "1.0", "source_type": "jira", "generated_at": datetime.now().astimezone().isoformat(),
        "source": {"type": "JIRA SSO", "urls": source_urls}, "records": records, "epics": epics,
        "taches": taches, "anomalies": anomalies,
        "indicateurs": {
            "tickets_uniques": len(issues_by_key), "epics": len(epics), "taches": len(taches),
            "bugs": len(anomalies),
            "domaines": dict(Counter(x["domaine"] for x in classifications.values()))
        }
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Source JIRA prête : {args.output.name}")
    print(f"Tickets uniques : {len(issues_by_key)} | Epics : {len(epics)} | Tâches : {len(taches)} | Bugs : {len(anomalies)} | Lignes SIT/UAT : {len(records)}")


if __name__ == "__main__":
    main()
