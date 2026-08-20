from pathlib import Path
import json
import base64
import re

ROOT = Path.cwd()

FILES = [
    ROOT / "jira" / "dashboard_gil_data.json",
    ROOT / "jira" / "presentation" / "payload_dashboard_final.json",
    ROOT / "commun" / "dashboard_gil_data.json",
]

HTML = ROOT / "commun" / "dashboard_gil.html"

KEYS = [
    "sprintCourant",
    "sprintPrecedent",
    "architectureDashboardFinal",
    "santeFluxArrimage",
    "comparaisonSprints",
    "comparaisonSprintsJiraOfficielle",
    "fluxPretsArrimage",
    "histoFlux",
    "anomaliesDetail",
    "prioritesHebdo",
    "ventilation",
    "tendanceHebdo",
    "kpis",
]


def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return {"__error__": str(e)}


def extract_fallback(path):
    if not path.exists():
        return None

    html = path.read_text(encoding="utf-8", errors="replace")

    m = re.search(r'atob\("([^"]+)"\)', html)
    if m:
        try:
            return json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
        except Exception:
            pass

    for pattern in [
        r"const fallbackData\s*=\s*([\s\S]*?);\s*let currentData",
        r"const fallbackData\s*=\s*([\s\S]*?);\s*window",
    ]:
        m = re.search(pattern, html)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

    return None


def count_value(value):
    if isinstance(value, list):
        return f"list len={len(value)}"
    if isinstance(value, dict):
        return f"dict keys={len(value)}"
    if value is None:
        return "absent"
    return repr(value)[:160]


def show_payload(name, data):
    print()
    print("=" * 80)
    print(name)
    print("=" * 80)

    if data is None:
        print("ABSENT")
        return

    if "__error__" in data:
        print("JSON INVALIDE :", data["__error__"])
        return

    for key in KEYS:
        print(f"{key:35} = {count_value(data.get(key))}")

    comp = data.get("comparaisonSprints")
    if isinstance(comp, list):
        print()
        print("comparaisonSprints détail :")
        for row in comp:
            if isinstance(row, dict):
                print(
                    "-",
                    row.get("sprint"),
                    "| fluxTotal=", row.get("fluxTotal"),
                    "| livrés=", row.get("fluxLivresTotal"),
                    "| enCours=", row.get("fluxEnCoursTotal"),
                    "| bloqués=", row.get("fluxBloquesTotal"),
                    "| totalDetail=", len(row.get("fluxTotalDetail") or []),
                )

    sante = data.get("santeFluxArrimage")
    if isinstance(sante, dict):
        print()
        print("santeFluxArrimage :")
        for k, v in sante.items():
            print(f"- {k}: {v}")


for path in FILES:
    show_payload(str(path.relative_to(ROOT)), load_json(path))

show_payload("fallbackData dans commun/dashboard_gil.html", extract_fallback(HTML))
