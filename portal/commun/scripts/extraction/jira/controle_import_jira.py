from __future__ import annotations

import json
from pathlib import Path

from gil_paths import (
    JIRA_DIAGNOSTIC,
    JIRA_BRUT,
    DASHBOARD_GIL_DATA,
    SPRINTS_DASHBOARD,
    COMPARAISON_SPRINTS,
    PAYLOAD_DASHBOARD_FINAL,
)

DIAG = JIRA_DIAGNOSTIC
BRUT = JIRA_BRUT
SOURCE = DASHBOARD_GIL_DATA


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
print("[5/5] CONTROLE FINAL IMPORT JIRA")
print("============================================================")

print()
print("Fichiers produits :")

FILES = [
    BRUT,
    DIAG,
    SPRINTS_DASHBOARD,
    SOURCE,
    COMPARAISON_SPRINTS,
    PAYLOAD_DASHBOARD_FINAL,
]

for path in FILES:
    print(
        f" - {path.name:<28} "
        f"{'OK' if path.exists() else 'ABSENT'}"
    )

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
print("Contrôle publication Portal :")

required = [
    SOURCE,
    SPRINTS_DASHBOARD,
    COMPARAISON_SPRINTS,
    PAYLOAD_DASHBOARD_FINAL,
]

for path in required:
    print(
        f" - {path.name:<28} "
        f"{'OK' if path.exists() else 'ABSENT'}"
    )

print()
print("Résumé :")
missing = [
    path
    for path in required
    if not path.exists()
]

if SOURCE.exists() and not missing:
    print(" - import exploitable : OUI")
else:
    print(" - import exploitable : NON")

    if missing:
        print(
            " - fichiers manquants :",
            ", ".join(
                path.name
                for path in missing
            ),
        )

print("============================================================")
