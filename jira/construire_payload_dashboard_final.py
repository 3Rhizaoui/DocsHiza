from pathlib import Path
import base64
import copy
import json
import re

ROOT = Path(__file__).resolve().parents[1]
JIRA = ROOT / "jira"
COMMUN = ROOT / "commun"

BASE_JSON = JIRA / "dashboard_gil_data.json"
BASE_HTML = COMMUN / "dashboard_gil.html"

CUR = JIRA / "sprints" / "sprint_courant.json"
PREV = JIRA / "sprints" / "sprint_precedent.json"
COMP = JIRA / "presentation" / "comparaison_sprints.json"

OUT_PRESENTATION = JIRA / "presentation" / "payload_dashboard_final.json"
OUT_COMMUN = COMMUN / "dashboard_gil_data.json"


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_fallback_from_html(path: Path):
    if not path.exists():
        return None

    html = path.read_text(encoding="utf-8", errors="replace")

    # Cas fallback encodé en base64.
    m = re.search(r'atob\("([^"]+)"\)', html)
    if m:
        try:
            return json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
        except Exception:
            pass

    # Cas fallbackData JSON direct.
    patterns = [
        r"const fallbackData\s*=\s*([\s\S]*?);\s*let currentData",
        r"const fallbackData\s*=\s*([\s\S]*?);\s*window",
    ]

    for pattern in patterns:
        m = re.search(pattern, html)
        if not m:
            continue
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    return None


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


def get_current_row(payload):
    tendance = payload.setdefault("tendanceHebdo", {})
    current = tendance.get("current")

    if isinstance(current, dict):
        return current

    rows = tendance.get("rows")
    if isinstance(rows, list) and rows:
        current = rows[-1]
        tendance["current"] = current
        return current

    current = {}
    tendance["current"] = current
    return current


def compute_health_from_legacy(payload):
    current = get_current_row(payload)
    kpis = payload.get("kpis") or {}

    total = first_int(
        current.get("flux"),
        current.get("fluxTotal"),
        kpis.get("flux"),
        kpis.get("totalFlux"),
        default=0,
    )

    ready = first_int(
        current.get("pretTester"),
        current.get("prets"),
        kpis.get("pretTester"),
        kpis.get("prets"),
        default=0,
    )

    blocked = first_int(
        current.get("bugsBloquants"),
        kpis.get("bugsBloquants"),
        default=0,
    )

    if total:
        score = round((ready / total) * 100 - min(35, blocked * 3))
    else:
        score = 100

    score = max(0, min(100, score))

    if score >= 80:
        niveau = "Vert"
    elif score >= 60:
        niveau = "Orange"
    else:
        niveau = "Rouge"

    return {
        "source": "JQL Arrimage",
        "totalFluxOuverts": total,
        "prets": ready,
        "enCours": max(0, total - ready),
        "bloques": blocked,
        "score": score,
        "niveau": niveau,
        "formule": "score historique conservé : prêts / flux ouverts - pénalité bugs bloquants",
    }


def force_legacy_health_fields(payload, current_name):
    sante = compute_health_from_legacy(payload)
    current = get_current_row(payload)

    current["sprint"] = current_name
    current["flux"] = sante["totalFluxOuverts"]
    current["pretTester"] = sante["prets"]
    current["nonPret"] = sante["enCours"]
    current["bugsBloquants"] = sante["bloques"]
    current["sante"] = sante["niveau"]

    tendance = payload.setdefault("tendanceHebdo", {})
    rows = tendance.get("rows")
    if isinstance(rows, list) and rows:
        rows[-1]["sprint"] = current_name
        rows[-1]["flux"] = sante["totalFluxOuverts"]
        rows[-1]["pretTester"] = sante["prets"]
        rows[-1]["nonPret"] = sante["enCours"]
        rows[-1]["bugsBloquants"] = sante["bloques"]
        rows[-1]["sante"] = sante["niveau"]

    kpis = payload.setdefault("kpis", {})
    kpis["flux"] = sante["totalFluxOuverts"]
    kpis["pretTester"] = sante["prets"]
    kpis["prets"] = sante["prets"]
    kpis["enCours"] = sante["enCours"]
    kpis["bugsBloquants"] = sante["bloques"]

    payload["santeFluxArrimage"] = sante


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


def assert_legacy_blocks(payload):
    required_lists = [
        "comparaisonSprints",
        "fluxPretsArrimage",
        "histoFlux",
        "anomaliesDetail",
        "prioritesHebdo",
    ]

    warnings = []

    for key in required_lists:
        value = payload.get(key)
        if not isinstance(value, list) or len(value) == 0:
            warnings.append(key)

    # Les anomalies peuvent être à 0 selon le périmètre, mais les flux ne doivent pas être vides.
    blocking = []
    for key in ["fluxPretsArrimage", "histoFlux"]:
        value = payload.get(key)
        if not isinstance(value, list) or len(value) == 0:
            blocking.append(key)

    if blocking:
        raise SystemExit(
            "[ERREUR] Payload final incomplet : blocs legacy vides : "
            + ", ".join(blocking)
            + ". Le payload doit être construit depuis fallbackData HTML, pas depuis un JSON minimal."
        )

    return warnings


def main():
    html_payload = extract_fallback_from_html(BASE_HTML)
    json_payload = load_json(BASE_JSON, {})

    if html_payload:
        base = html_payload
        base_source = "fallbackData HTML publié"
    elif json_payload:
        base = json_payload
        base_source = "jira/dashboard_gil_data.json"
    else:
        raise SystemExit("[ERREUR] Aucune base dashboard exploitable trouvée")

    current_doc = load_json(CUR)
    previous_doc = load_json(PREV)
    comparison = load_json(COMP, [])

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

    force_legacy_health_fields(payload, current_name)

    categories_current = load_json(JIRA / "presentation" / "categories_sprint_courant.json", {})
    if categories_current:
        payload["categoriesSprintCourant"] = categories_current

    payload["architectureDashboardFinal"] = {
        "baseSource": base_source,
        "sourceSanteProjet": "JQL Arrimage",
        "sourceComparaisonSprint": "API Agile Jira officielle",
        "comparaisonRespecteTotauxOfficiels": True,
        "runtimeNeRecalculePasLeScore": True,
    }

    warnings = assert_legacy_blocks(payload)

    write_json(OUT_PRESENTATION, payload)
    write_json(OUT_COMMUN, payload)

    print("[OK] Payload dashboard final produit :")
    print(" -", OUT_PRESENTATION)
    print(" -", OUT_COMMUN)
    print("Base utilisée :", base_source)

    sante = payload["santeFluxArrimage"]
    print()
    print("Santé projet GIL / JQL Arrimage :")
    print(
        "- total:", sante["totalFluxOuverts"],
        "| prêts:", sante["prets"],
        "| en cours:", sante["enCours"],
        "| score:", sante["score"],
        "| niveau:", sante["niveau"],
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

    print()
    print("Blocs legacy préservés :")
    for key in ["fluxPretsArrimage", "histoFlux", "anomaliesDetail", "prioritesHebdo"]:
        value = payload.get(key)
        print("-", key, ":", len(value) if isinstance(value, list) else "absent")

    if warnings:
        print()
        print("[WARN] Blocs à surveiller :", ", ".join(warnings))


if __name__ == "__main__":
    main()
