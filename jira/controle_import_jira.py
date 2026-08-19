from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

DIAG = ROOT / "jira_diagnostic.json"
BRUT = ROOT / "jira_brut.json"
SOURCE = ROOT / "dashboard_gil_data.json"
HTML = PROJECT / "commun" / "dashboard_gil_sprint21.html"
SPRINTS_DASHBOARD = ROOT / "sprints_dashboard.json"


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        print(f"[WARN] JSON illisible : {path} -> {exc}")
        return None


def rows_from_source(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["rows", "data", "items", "records"]:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


print()
print("============================================================")
print("[4/4] CONTROLE FINAL IMPORT JIRA")
print("============================================================")

print()
print("Fichiers produits :")
for path in [BRUT, DIAG, SPRINTS_DASHBOARD, SOURCE, HTML]:
    print(f" - {path.name:<28} {'OK' if path.exists() else 'ABSENT'}")

print()
print("Diagnostic JIRA :")
diag = load_json(DIAG) if DIAG.exists() else None

if isinstance(diag, dict):
    requetes = diag.get("requetes") or []
    erreurs = diag.get("erreurs") or []

    print(" - requêtes suivies :", len(requetes))
    print(" - erreurs déclarées:", len(erreurs))

    sprints = diag.get("sprints") or diag.get("diagnostic_sprints") or {}
    courant = sprints.get("courant") or {}
    precedent = sprints.get("precedent") or {}

    if sprints:
        print(" - sprint courant   :", courant.get("nom") or courant.get("name") or "(non détecté)")
        print(" - sprint précédent :", precedent.get("nom") or precedent.get("name") or "(non détecté)")

        sc = sprints.get("sprintsCourants") or []
        sf = sprints.get("sprintsFermes") or []

        print(" - sprints ouverts  :", len(sc))
        print(" - sprints fermés   :", len(sf))

        if sc:
            print()
            print("Sprints ouverts détectés :")
            for item in sc[:5]:
                print(
                    " -",
                    item.get("nom") or item.get("name"),
                    "| flux:", item.get("flux"),
                    "| anomalies:", item.get("anomalies"),
                    "| total:", item.get("total"),
                )

        if sf:
            print()
            print("Derniers sprints fermés détectés :")
            for item in sf[:5]:
                print(
                    " -",
                    item.get("nom") or item.get("name"),
                    "| flux:", item.get("flux"),
                    "| anomalies:", item.get("anomalies"),
                    "| total:", item.get("total"),
                )
    else:
        print(" - sprints          : diagnostic non présent")
else:
    print(" - diagnostic absent ou illisible")

print()
print("Source dashboard normalisée :")
source = load_json(SOURCE) if SOURCE.exists() else None
rows = rows_from_source(source)
print(" - lignes dashboard :", len(rows))

flux = []
anomalies = []

for row in rows:
    if not isinstance(row, dict):
        continue
    typ = str(row.get("type") or row.get("issuetype") or row.get("issueType") or "").lower()
    if "anomal" in typ or typ == "bug":
        anomalies.append(row)
    else:
        flux.append(row)

print(" - flux             :", len(flux))
print(" - anomalies        :", len(anomalies))

print()
print("Publication HTML :")
if HTML.exists():
    html = HTML.read_text(encoding="utf-8", errors="replace")
    print(" - runLocalAction   :", "OK" if "function runLocalAction" in html else "ABSENT")
    print(" - fallbackData     :", "OK" if "const fallbackData" in html else "ABSENT")
    print(" - fetch externe    :", "KO" if "fetch('rapport_gil_v6_data.json'" in html or 'fetch(\"rapport_gil_v6_data.json' in html else "OK désactivé")
    print(" - détail calcul    :", "OK" if "statutSprintCalcul" in html else "ABSENT")
else:
    print(" - HTML absent")

print()
print("Résumé :")
if SOURCE.exists() and HTML.exists():
    print(" - import exploitable : OUI")
else:
    print(" - import exploitable : NON")

print("============================================================")
