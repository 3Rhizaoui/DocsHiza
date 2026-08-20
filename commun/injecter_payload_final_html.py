from pathlib import Path
import base64
import datetime as dt
import json
import re

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"

TEMPLATE = COMMUN / "templates" / "dashboard_gil_template.html"
PAYLOAD = ROOT / "jira" / "presentation" / "payload_dashboard_final.json"

OUTPUTS = [
    COMMUN / "dashboard_gil.html",
    COMMUN / "dashboard_gil_sprint21.html",
]


def fail(message: str):
    raise SystemExit("[ERREUR] " + message)


def sprint_label(value):
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in ["name", "nom", "sprint", "label", "titre"]:
            if value.get(key):
                return str(value[key]).strip()

    return ""


def load_payload():
    if not PAYLOAD.exists():
        fail(f"Payload final absent : {PAYLOAD}")

    try:
        data = json.loads(PAYLOAD.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        fail(f"Payload final JSON invalide : {exc}")

    if not isinstance(data, dict):
        fail("Payload final invalide : objet JSON attendu")

    courant = sprint_label(data.get("sprintCourant"))
    precedent = sprint_label(data.get("sprintPrecedent"))

    if not courant:
        fail("sprintCourant absent du payload final")

    required_lists = [
        "comparaisonSprints",
        "fluxPretsArrimage",
        "histoFlux",
    ]

    for key in required_lists:
        value = data.get(key)
        if not isinstance(value, list):
            fail(f"{key} absent ou non-liste dans le payload final")
        if len(value) == 0:
            fail(f"{key} vide dans le payload final")

    optional_lists = [
        "anomaliesDetail",
        "prioritesHebdo",
        "ventilation",
    ]

    for key in optional_lists:
        value = data.get(key)
        if value is not None and not isinstance(value, list):
            fail(f"{key} doit être une liste si présent")

    return data, courant, precedent


def clean_runtime(html: str) -> str:
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


def patch_static_sprint_labels(html: str, courant: str, precedent: str) -> str:
    # Titres principaux.
    html = re.sub(
        r"Biweekly GIL\s*-\s*Reporting\s+(?:Scrum\s+)?Sprint\s+\d+",
        f"Biweekly GIL - Reporting {courant}",
        html,
    )

    html = re.sub(
        r"Statut du\s+(?:Scrum\s+)?Sprint\s+\d+",
        f"Statut du {courant}",
        html,
    )

    html = re.sub(
        r"Statut général du\s+(?:Scrum\s+)?Sprint\s+\d+",
        f"Statut général du {courant}",
        html,
    )

    # Remplacement générique sur le template Sprint 21.
    if precedent:
        html = re.sub(r"\bSprint 20\b", precedent, html)

    html = re.sub(r"\bSprint 21\b", courant, html)

    return html


def payload_expression(data: dict) -> str:
    # ensure_ascii=True évite les problèmes Unicode avec atob().
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return f'JSON.parse(atob("{encoded}"))'


def replace_fallback_data(html: str, expr: str) -> str:
    patterns = [
        re.compile(
            r"(const\s+fallbackData\s*=\s*)([\s\S]*?)(;\s*let\s+currentData\b)",
            re.S,
        ),
        re.compile(
            r"(const\s+fallbackData\s*=\s*)([\s\S]*?)(;\s*var\s+currentData\b)",
            re.S,
        ),
        re.compile(
            r"(const\s+fallbackData\s*=\s*)([\s\S]*?)(;\s*window\b)",
            re.S,
        ),
    ]

    for pattern in patterns:
        html2, count = pattern.subn(lambda m: m.group(1) + expr + m.group(3), html, count=1)
        if count:
            return html2

    fail("Bloc JavaScript const fallbackData introuvable dans le template")


def verify_html(html: str, courant: str):
    forbidden = [
        "runtime_dashboard.js",
        "dashboard_gil_data.json",
        "_gil_poll",
        "Payload dashboard final absent",
        "stableFallbackLoader",
    ]

    found = [token for token in forbidden if token in html]
    if found:
        fail("HTML généré contient encore des éléments runtime interdits : " + ", ".join(found))

    if "const fallbackData" not in html:
        fail("HTML généré ne contient pas const fallbackData")

    m = re.search(r'const\s+fallbackData\s*=\s*JSON\.parse\(atob\("([^"]+)"\)\)', html)
    if not m:
        fail("fallbackData encodé en base64 introuvable dans le HTML généré")

    try:
        decoded = base64.b64decode(m.group(1)).decode("utf-8")
        data = json.loads(decoded)
    except Exception as exc:
        fail(f"fallbackData généré illisible : {exc}")

    if data.get("sprintCourant") != courant:
        fail(
            "fallbackData généré ne contient pas le bon sprint courant : "
            f"attendu={courant} | obtenu={data.get('sprintCourant')}"
        )


def generate():
    if not TEMPLATE.exists():
        fail(f"Template absent : {TEMPLATE}")

    data, courant, precedent = load_payload()

    template_html = TEMPLATE.read_text(encoding="utf-8", errors="replace")
    html = clean_runtime(template_html)
    html = patch_static_sprint_labels(html, courant, precedent)
    html = replace_fallback_data(html, payload_expression(data))

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = html.replace(
        "</head>",
        f'<meta name="gil-generated-at" content="{stamp}">\n</head>',
        1,
    )

    verify_html(html, courant)

    for output in OUTPUTS:
        output.write_text(html, encoding="utf-8")
        print("[OK] HTML généré depuis template :", output.relative_to(ROOT))

    print()
    print("[OK] Dashboard HTML autonome généré")
    print("Template          :", TEMPLATE.relative_to(ROOT))
    print("Payload           :", PAYLOAD.relative_to(ROOT))
    print("Sprint courant    :", courant)
    print("Sprint précédent  :", precedent or "Non renseigné")
    print("Comparaison       :", len(data.get("comparaisonSprints") or []))
    print("Flux arrimage     :", len(data.get("fluxPretsArrimage") or []))
    print("Histo flux        :", len(data.get("histoFlux") or []))
    print("Anomalies détail  :", len(data.get("anomaliesDetail") or []))
    print("Priorités hebdo   :", len(data.get("prioritesHebdo") or []))


if __name__ == "__main__":
    generate()
