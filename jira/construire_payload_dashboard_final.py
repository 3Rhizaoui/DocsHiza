from pathlib import Path
import copy
import json

ROOT = Path(__file__).resolve().parents[1]
JIRA = ROOT / "jira"
COMMUN = ROOT / "commun"

BASE = JIRA / "dashboard_gil_data.json"
CUR = JIRA / "sprints" / "sprint_courant.json"
PREV = JIRA / "sprints" / "sprint_precedent.json"
COMP = JIRA / "presentation" / "comparaison_sprints.json"

OUT_PRESENTATION = JIRA / "presentation" / "payload_dashboard_final.json"
OUT_COMMUN = COMMUN / "dashboard_gil_data.json"


def load(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def first_int(*values, default=0):
    for value in values:
        try:
            if value not in (None, ""):
                return int(value)
        except Exception:
            pass
    return default


def sprint_name(doc, fallback):
    sprint = doc.get("sprint") or {}
    return sprint.get("nom") or sprint.get("name") or doc.get("nom") or doc.get("name") or fallback


def official_total(doc):
    stats = doc.get("statistiques") or {}
    return first_int(stats.get("total"), stats.get("flux"), default=0)


def current_health(payload):
    tendance = payload.get("tendanceHebdo") or {}
    current = tendance.get("current") or {}
    kpis = payload.get("kpis") or {}

    total = first_int(current.get("flux"), kpis.get("flux"), kpis.get("totalFlux"), default=0)
    ready = first_int(current.get("pretTester"), kpis.get("pretTester"), kpis.get("prets"), default=0)
    blocked = first_int(current.get("bugsBloquants"), kpis.get("bugsBloquants"), default=0)

    if total:
        score = round((ready / total) * 100 - min(35, blocked * 3))
    else:
        score = 100

    score = max(0, min(100, score))

    return {
        "source": "JQL Arrimage",
        "totalFluxOuverts": total,
        "prets": ready,
        "enCours": max(0, total - ready),
        "bloques": blocked,
        "score": score,
        "formule": "score = prêts / flux ouverts - pénalité bugs bloquants, formule historique conservée",
    }


def assert_comparison_consistency(comparison, current_doc, previous_doc):
    current_name = sprint_name(current_doc, "Sprint courant")
    previous_name = sprint_name(previous_doc, "Sprint précédent")

    expected = {
        current_name: official_total(current_doc),
        previous_name: official_total(previous_doc),
    }

    for row in comparison:
        name = row.get("sprint")
        if name in expected and int(row.get("fluxTotal", -1)) != expected[name]:
            raise SystemExit(
                f"[ERREUR] Comparaison incohérente pour {name} : "
                f"{row.get('fluxTotal')} au lieu du total officiel {expected[name]}"
            )


def main():
    if not BASE.exists():
        raise SystemExit(f"[ERREUR] Source dashboard absente : {BASE}")
    if not CUR.exists():
        raise SystemExit(f"[ERREUR] Sprint courant absent : {CUR}")
    if not PREV.exists():
        raise SystemExit(f"[ERREUR] Sprint précédent absent : {PREV}")
    if not COMP.exists():
        raise SystemExit(f"[ERREUR] Comparaison absente : {COMP}")

    base = load(BASE)
    current_doc = load(CUR)
    previous_doc = load(PREV)
    comparison = load(COMP, [])

    if not isinstance(comparison, list) or len(comparison) < 2:
        raise SystemExit("[ERREUR] comparaison_sprints.json doit contenir deux lignes")

    assert_comparison_consistency(comparison, current_doc, previous_doc)

    payload = copy.deepcopy(base)

    current_name = sprint_name(current_doc, "Sprint courant")
    previous_name = sprint_name(previous_doc, "Sprint précédent")

    payload["sprintCourant"] = current_name
    payload["sprintPrecedent"] = previous_name

    payload["sprintCourantDetail"] = current_doc
    payload["sprintPrecedentDetail"] = previous_doc

    payload["comparaisonSprints"] = comparison
    payload["comparaisonSprintsJiraOfficielle"] = comparison

    # Préserver la santé projet sur le périmètre JQL Arrimage.
    payload["santeFluxArrimage"] = current_health(payload)

    # Mettre à jour seulement les libellés sprint, jamais les valeurs de santé.
    tendance = payload.get("tendanceHebdo") or {}
    if isinstance(tendance.get("current"), dict):
        tendance["current"]["sprint"] = current_name

    rows = tendance.get("rows")
    if isinstance(rows, list) and rows:
        rows[-1]["sprint"] = current_name

    payload["tendanceHebdo"] = tendance

    # Données d’audit / future exploitation.
    categories_current = load(JIRA / "presentation" / "categories_sprint_courant.json", {})
    if categories_current:
        payload["categoriesSprintCourant"] = categories_current

    payload["architectureDashboardFinal"] = {
        "sourceSanteProjet": "JQL Arrimage",
        "sourceComparaisonSprint": "API Agile Jira officielle",
        "comparaisonRespecteTotauxOfficiels": True,
        "runtimeNeRecalculePasLeScore": True,
    }

    write(OUT_PRESENTATION, payload)
    write(OUT_COMMUN, payload)

    print("[OK] Payload dashboard final produit :")
    print(" -", OUT_PRESENTATION)
    print(" -", OUT_COMMUN)
    print()
    print("Santé projet GIL / JQL Arrimage :")
    sante = payload["santeFluxArrimage"]
    print(
        "- total:", sante["totalFluxOuverts"],
        "| prêts:", sante["prets"],
        "| en cours:", sante["enCours"],
        "| score:", sante["score"],
    )
    print()
    print("Comparaison officielle API Agile :")
    for row in comparison:
        print(
            "-",
            row.get("sprint"),
            "| total:", row.get("fluxTotal"),
            "| livrés:", row.get("fluxLivresTotal"),
            "| en cours:", row.get("fluxEnCoursTotal"),
            "| bloqués:", row.get("fluxBloquesTotal"),
        )


if __name__ == "__main__":
    main()
