from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
JIRA = ROOT / "jira"

FILES = {
    "sprint_precedent": JIRA / "sprints" / "sprint_precedent.json",
    "sprint_courant": JIRA / "sprints" / "sprint_courant.json",
    "comparaison": JIRA / "presentation" / "comparaison_sprints.json",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def fail(msg):
    print("[FAIL]", msg)
    return 1


def warn(msg):
    print("[WARN]", msg)


def ok(msg):
    print("[OK]", msg)


def main():
    errors = 0

    for name, path in FILES.items():
        if not path.exists():
            errors += fail(f"Fichier absent : {path}")
        else:
            ok(f"Fichier présent : {path}")

    if errors:
        return errors

    previous = load(FILES["sprint_precedent"])
    current = load(FILES["sprint_courant"])
    comparison = load(FILES["comparaison"])

    if not isinstance(comparison, list) or len(comparison) != 2:
        errors += fail("comparaison_sprints.json doit contenir exactement 2 lignes")
        return errors

    docs = {
        "precedent": previous,
        "courant": current,
    }

    for role, doc in docs.items():
        sprint = doc.get("sprint") or {}
        stats = doc.get("statistiques") or {}

        if not sprint.get("nom"):
            errors += fail(f"{role}: nom sprint absent")

        if not stats.get("total"):
            errors += fail(f"{role}: total absent ou nul")

        if "tickets" not in doc:
            errors += fail(f"{role}: liste tickets absente")

        if stats.get("detailsTicketsDisponibles") is False:
            warn(f"{role}: détails tickets non disponibles, résumé sprint uniquement")

        ok(f"{role}: {sprint.get('nom')} | total={stats.get('total')} | flux={stats.get('flux')} | anomalies={stats.get('anomalies')}")

    by_role = {row.get("role"): row for row in comparison if isinstance(row, dict)}

    for role, doc in docs.items():
        row = by_role.get(role)
        stats = doc.get("statistiques") or {}

        if not row:
            errors += fail(f"comparaison: ligne manquante pour {role}")
            continue

        if int(row.get("total") or 0) != int(stats.get("total") or 0):
            errors += fail(f"comparaison: total incohérent pour {role}")

        if int(row.get("flux") or 0) != int(stats.get("flux") or 0):
            errors += fail(f"comparaison: flux incohérent pour {role}")

        if int(row.get("anomalies") or 0) != int(stats.get("anomalies") or 0):
            errors += fail(f"comparaison: anomalies incohérentes pour {role}")

    if errors:
        print(f"[KO] Architecture sprint invalide : {errors} erreur(s)")
        return errors

    print("[OK] Architecture sprint valide")
    return 0


if __name__ == "__main__":
    sys.exit(main())
