
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRUT = ROOT / "jira_brut.json"
DIAG = ROOT / "jira_diagnostic.json"
OUT = ROOT / "sprints_dashboard.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def sval(value) -> str:
    return "" if value is None else str(value).strip()


def norm(value) -> str:
    return sval(value).casefold()


def issue_type(issue: dict) -> str:
    v = (issue.get("fields") or {}).get("issuetype")
    return sval(v.get("name") if isinstance(v, dict) else v)


def is_anomaly(issue: dict) -> bool:
    t = norm(issue_type(issue))
    return "bug" in t or "anomal" in t


def status(issue: dict) -> str:
    v = (issue.get("fields") or {}).get("status")
    return sval(v.get("name") if isinstance(v, dict) else v)


def is_done(issue: dict) -> bool:
    s = norm(status(issue))
    return any(x in s for x in ["done", "closed", "clos", "résolu", "resolu", "termin", "livr", "valid"])


def priority(issue: dict) -> str:
    v = (issue.get("fields") or {}).get("priority")
    return sval(v.get("name") if isinstance(v, dict) else v)


def assignee(issue: dict) -> str:
    v = (issue.get("fields") or {}).get("assignee")
    return sval(v.get("displayName") or v.get("name") if isinstance(v, dict) else "")


def versions(issue: dict) -> str:
    fields = issue.get("fields") or {}
    out = []
    for key in ["fixVersions", "versions"]:
        for item in fields.get(key) or []:
            out.append(sval(item.get("name") if isinstance(item, dict) else item))
    return " / ".join(v for v in out if v)


def components(issue: dict):
    out = []
    for item in (issue.get("fields") or {}).get("components") or []:
        out.append(sval(item.get("name") if isinstance(item, dict) else item))
    return [x for x in out if x]


def issue_detail(issue: dict, sprint_name: str) -> dict:
    fields = issue.get("fields") or {}
    comps = components(issue)

    return {
        "reference": issue.get("key"),
        "flux": issue.get("key"),
        "summary": sval(fields.get("summary")),
        "domaine": comps[0] if comps else "À qualifier",
        "sousDomaine": comps[1] if len(comps) > 1 else "À qualifier",
        "environnement": "SIT",
        "statut": status(issue) or "Non renseigné",
        "partenaire": assignee(issue) or "Non renseigné",
        "responsable": assignee(issue) or "Non renseigné",
        "version": versions(issue),
        "severite": priority(issue) or "Non renseignée",
        "sprint": sprint_name,
        "nombre": 1,
    }


def split_issues(issues: list[dict]):
    flux = []
    anomalies_open = []
    anomalies_done = []

    for issue in issues:
        if is_anomaly(issue):
            if is_done(issue):
                anomalies_done.append(issue)
            else:
                anomalies_open.append(issue)
        else:
            flux.append(issue)

    return flux, anomalies_open, anomalies_done


def sprint_summary(sprint: dict, issues: list[dict]) -> dict:
    flux, anomalies_open, anomalies_done = split_issues(issues)

    return {
        "id": sprint.get("id"),
        "nom": sprint.get("nom") or sprint.get("name"),
        "etat": sprint.get("etat") or sprint.get("state"),
        "startDate": sprint.get("startDate", ""),
        "endDate": sprint.get("endDate", ""),
        "completeDate": sprint.get("completeDate", ""),
        "total": len(issues),
        "flux": len(flux),
        "anomalies": len(anomalies_open) + len(anomalies_done),
        "cles": [x.get("key") for x in issues if x.get("key")],
        "clesFlux": [x.get("key") for x in flux if x.get("key")],
        "clesAnomalies": [x.get("key") for x in anomalies_open + anomalies_done if x.get("key")],
    }


def comparison_row(sprint: dict, issues: list[dict], label: str) -> dict:
    sprint_name = sprint.get("nom") or sprint.get("name") or label
    flux, anomalies_open, anomalies_done = split_issues(issues)

    ready_flux = [x for x in flux if is_done(x)]
    in_progress_flux = [x for x in flux if not is_done(x)]

    return {
        "sprint": sprint_name,
        "typeDonnee": label,
        "semaines": [sprint_name],
        "flux": len(flux),
        "pretTester": len(ready_flux),
        "nonPret": len(in_progress_flux),
        "bugsBloquants": len(anomalies_open),
        "servicesRisque": 0,
        "testsKoBloques": 0,
        "prioritesTraitees": len(ready_flux),
        "sante": "Vert",
        "faitMarquant": "Jira — sprint officiel via board Agile",
        "risque": f"{len(anomalies_open)} anomalie(s) ouverte(s)",
        "fluxLivresDetail": [issue_detail(x, sprint_name) for x in ready_flux],
        "fluxEnCoursDetail": [issue_detail(x, sprint_name) for x in in_progress_flux],
        "anomaliesOuvertesDetail": [issue_detail(x, sprint_name) for x in anomalies_open],
        "anomaliesResoluesDetail": [issue_detail(x, sprint_name) for x in anomalies_done],
        "anomaliesEnCoursDetail": [],
        "sousDomainesRisqueDetail": [],
        "fluxLivresTotal": len(ready_flux),
        "fluxEnCoursTotal": len(in_progress_flux),
        "anomaliesOuvertesTotal": len(anomalies_open),
        "anomaliesResoluesTotal": len(anomalies_done),
        "anomaliesEnCoursTotal": 0,
        "sousDomainesRisqueTotal": 0,
    }


def write_unreliable(reason: str, raw: dict) -> int:
    output = {
        "schema_version": "1.0",
        "source": "jira_brut.json",
        "methode": "agile_api",
        "reliable": False,
        "warnings": [reason],
        "courant": {},
        "precedent": {},
        "comparaisonSprints": [],
    }

    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    diag = load_json(DIAG) if DIAG.exists() else {}
    diag["sprints"] = output
    DIAG.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[ATTENTION NON BLOQUANTE] Diagnostic sprint officiel non fiable.")
    print(" -", reason)
    print("Action : le dashboard garde la publication stable sans comparaison dynamique.")
    return 0


def main() -> int:
    print()
    print("============================================================")
    print("[2/5] DETECTION OFFICIELLE DES SPRINTS JIRA")
    print("============================================================")

    raw = load_json(BRUT)
    diag = raw.get("diagnostic_sprints") or {}

    if diag.get("methode") != "agile_api" or diag.get("reliable") is not True:
        return write_unreliable("API Agile absente, refusée ou diagnostic non fiable.", raw)

    courant = diag.get("courant") or {}
    precedent = diag.get("precedent") or {}
    issues_courant = diag.get("issuesCourant") or []
    issues_precedent = diag.get("issuesPrecedent") or []

    if not courant.get("nom") or not precedent.get("nom"):
        return write_unreliable("Sprint courant ou sprint précédent absent du diagnostic officiel.", raw)

    if not issues_courant:
        return write_unreliable("Aucun ticket récupéré pour le sprint courant officiel.", raw)

    if not issues_precedent:
        return write_unreliable("Aucun ticket récupéré pour le sprint précédent officiel.", raw)

    courant_summary = sprint_summary(courant, issues_courant)
    precedent_summary = sprint_summary(precedent, issues_precedent)

    output = {
        "schema_version": "1.0",
        "source": "jira_brut.json",
        "methode": "agile_api",
        "reliable": True,
        "warnings": [],
        "projectKey": diag.get("projectKey"),
        "board": diag.get("board"),
        "courant": courant_summary,
        "precedent": precedent_summary,
        "sprints": diag.get("sprints") or [],
        "comparaisonSprints": [
            comparison_row(precedent, issues_precedent, "Sprint précédent"),
            comparison_row(courant, issues_courant, "Sprint courant"),
        ],
    }

    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    diag_file = load_json(DIAG) if DIAG.exists() else {}
    diag_file["sprints"] = {
        "projectKey": output.get("projectKey"),
        "board": output.get("board"),
        "methode": "agile_api",
        "reliable": True,
        "warnings": [],
        "courant": output["courant"],
        "precedent": output["precedent"],
        "sprintsCourants": [output["courant"]],
        "sprintsFermes": [output["precedent"]],
        "source": "sprints_dashboard.json",
    }
    DIAG.write_text(json.dumps(diag_file, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Méthode          : API Agile officielle")
    print("Board            :", (output.get("board") or {}).get("name"), "| id:", (output.get("board") or {}).get("id"))
    print("Sprint courant   :", output["courant"]["nom"], "| id:", output["courant"]["id"], "| flux:", output["courant"]["flux"], "| anomalies:", output["courant"]["anomalies"], "| total:", output["courant"]["total"])
    print("Sprint précédent :", output["precedent"]["nom"], "| id:", output["precedent"]["id"], "| flux:", output["precedent"]["flux"], "| anomalies:", output["precedent"]["anomalies"], "| total:", output["precedent"]["total"])
    print("Comparaison      :", len(output["comparaisonSprints"]), "ligne(s)")
    print("Fichier produit  :", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
