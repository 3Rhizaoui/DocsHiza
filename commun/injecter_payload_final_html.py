from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"
PAYLOAD = ROOT / "jira" / "presentation" / "payload_dashboard_final.json"

HTML_FILES = [
    COMMUN / "dashboard_gil.html",
    COMMUN / "dashboard_gil_sprint21.html",
]


def load_payload():
    if not PAYLOAD.exists():
        raise SystemExit(f"[ERREUR] Payload final absent : {PAYLOAD}")

    data = json.loads(PAYLOAD.read_text(encoding="utf-8", errors="replace"))

    required = [
        "architectureDashboardFinal",
        "santeFluxArrimage",
        "comparaisonSprints",
        "fluxPretsArrimage",
        "histoFlux",
        "anomaliesDetail",
        "prioritesHebdo",
    ]

    missing = []
    for key in required:
        value = data.get(key)
        if value is None:
            missing.append(key)
        elif isinstance(value, list) and len(value) == 0 and key in ["comparaisonSprints", "fluxPretsArrimage", "histoFlux"]:
            missing.append(key)

    if missing:
        raise SystemExit("[ERREUR] Payload final incomplet : " + ", ".join(missing))

    return data


def json_for_script(data):
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def remove_runtime(html: str) -> str:
    for script_id in [
        "stableFallbackLoader",
        "autoReloadAfterActionScript",
        "jiraOfficialComparisonFallbackScript",
        "jiraOfficialComparisonStaticScript",
        "jiraOfficialSprintRowsData",
    ]:
        html = re.sub(
            r'\n?<script\b[^>]*id="' + re.escape(script_id) + r'"[\s\S]*?</script>\n?',
            "\n",
            html,
            flags=re.S,
        )

    html = re.sub(
        r'\n?<script\b[^>]*src="runtime_dashboard\.js[^"]*"[^>]*></script>\n?',
        "\n",
        html,
        flags=re.S,
    )

    html = re.sub(
        r'\n?<meta name="gil-build-stamp" content="[^"]*">\n?',
        "\n",
        html,
        flags=re.S,
    )

    return html


def patch_static_titles(html: str, payload: dict) -> str:
    courant = payload.get("sprintCourant") or ""
    precedent = payload.get("sprintPrecedent") or ""

    if courant:
        html = html.replace("Biweekly GIL - Reporting Sprint 21", f"Biweekly GIL - Reporting {courant}")
        html = html.replace("Statut du Sprint 21", f"Statut du {courant}")
        html = html.replace("Statut général du Sprint 21", f"Statut général du {courant}")

    if precedent:
        html = html.replace("Sprint 20", precedent)

    if courant:
        html = html.replace("Sprint 21", courant)

    return html


def replace_fallback(html: str, payload_json: str) -> str:
    patterns = [
        re.compile(r"(const\s+fallbackData\s*=\s*)([\s\S]*?)(;\s*let\s+currentData)", re.S),
        re.compile(r"(const\s+fallbackData\s*=\s*)([\s\S]*?)(;\s*window\b)", re.S),
    ]

    for pattern in patterns:
        html2, count = pattern.subn(lambda m: m.group(1) + payload_json + m.group(3), html, count=1)
        if count:
            return html2

    raise SystemExit("[ERREUR] Bloc const fallbackData introuvable dans le HTML")


def patch_html(path: Path, payload: dict):
    if not path.exists():
        print("[INFO] HTML absent :", path)
        return

    html = path.read_text(encoding="utf-8", errors="replace")
    html = remove_runtime(html)
    html = patch_static_titles(html, payload)
    html = replace_fallback(html, json_for_script(payload))

    if "runtime_dashboard.js" in html:
        raise SystemExit(f"[ERREUR] runtime_dashboard.js encore présent dans {path}")

    path.write_text(html, encoding="utf-8")
    print("[OK] HTML autonome injecté :", path)


def main():
    payload = load_payload()

    for path in HTML_FILES:
        patch_html(path, payload)

    print()
    print("[OK] Injection HTML autonome terminée")
    print("Sprint courant   :", payload.get("sprintCourant"))
    print("Sprint précédent :", payload.get("sprintPrecedent"))
    print("Flux arrimage    :", len(payload.get("fluxPretsArrimage") or []))
    print("Histo flux       :", len(payload.get("histoFlux") or []))
    print("Comparaison      :", len(payload.get("comparaisonSprints") or []))


if __name__ == "__main__":
    main()
