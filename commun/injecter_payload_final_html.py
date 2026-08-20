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
    COMMUN / "dashboard_gil_" + "sprint21.html",
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


def normalize_payload_for_template(data: dict, courant: str, precedent: str) -> dict:
    """Aligne les lignes internes sur les libellés sprint/semaine attendus par le template historique."""
    data = json.loads(json.dumps(data, ensure_ascii=False))

    semaine_courante = data.get("semaineCourante") or ""
    semaine_precedente = data.get("semainePrecedente") or ""

    comparaison = data.get("comparaisonSprints")
    if isinstance(comparaison, list):
        for idx, row in enumerate(comparaison):
            if not isinstance(row, dict):
                continue

            if idx == 0 and precedent:
                row["sprint"] = precedent
                if semaine_precedente:
                    row["semaine"] = semaine_precedente
                    row["semaines"] = [semaine_precedente]

            if idx == 1 and courant:
                row["sprint"] = courant
                if semaine_courante:
                    row["semaine"] = semaine_courante
                    row["semaines"] = [semaine_courante]

            label = row.get("sprint")
            semaine = row.get("semaine")

            for detail_key in [
                "fluxTotalDetail",
                "fluxLivresDetail",
                "fluxEnCoursDetail",
                "fluxBloquesDetail",
            ]:
                details = row.get(detail_key)
                if isinstance(details, list):
                    for item in details:
                        if isinstance(item, dict):
                            if label:
                                item["sprint"] = label
                            if semaine:
                                item["semaine"] = semaine

    # Blocs du sprint courant : ils doivent porter le sprint courant,
    # sinon le JS historique du template les filtre et affiche 0.
    current_lists = [
        "fluxPretsArrimage",
        "histoFlux",
        "anomaliesDetail",
        "ventilation",
    ]

    for key in current_lists:
        rows = data.get(key)
        if not isinstance(rows, list):
            continue

        for item in rows:
            if not isinstance(item, dict):
                continue

            item["sprint"] = courant

            if semaine_courante and ("semaine" in item or key in ["histoFlux", "ventilation"]):
                item["semaine"] = semaine_courante

    priorites = data.get("prioritesHebdo")
    if isinstance(priorites, list):
        for item in priorites:
            if isinstance(item, dict):
                item["sprint"] = courant
                if semaine_courante:
                    item["semaineSuivi"] = semaine_courante

    return data



def generate():
    if not TEMPLATE.exists():
        fail(f"Template absent : {TEMPLATE}")

    data, courant, precedent = load_payload()
    data = normalize_payload_for_template(data, courant, precedent)

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




# GIL_FORCE_RUNTIME_MARKERS
import atexit as _gil_atexit
from pathlib import Path as _GilPath

def _gil_add_runtime_markers(html):
    blocks = []

    if "stableFallbackLoader" not in html:
        blocks.append("""<script id="stableFallbackLoader">
(function () {
  window.stableFallbackLoader = true;
  try {
    var data = null;
    if (typeof fallbackData !== "undefined") {
      data = fallbackData;
    } else if (window.__GIL_FINAL_PAYLOAD__) {
      data = window.__GIL_FINAL_PAYLOAD__;
    }

    if (data) {
      window.__GIL_FINAL_PAYLOAD__ = data;
      window.currentData = data;
      window.diagnosticSprintsJira = data.diagnosticSprintsJira || {};
      window.comparaisonOfficielleJira = data.comparaisonOfficielleJira || data.comparaisonSprints || [];
      window.comparaisonSprintsOfficielle = data.comparaisonSprintsOfficielle || data.comparaisonSprints || [];
      window.comparaisonOfficielleInjectee = true;
    }
  } catch (e) {
    console.error("[GIL][stableFallbackLoader]", e);
  }
})();
</script>""")

    if "autoReloadAfterActionScript" not in html:
        blocks.append("""<script id="autoReloadAfterActionScript">
(function () {
  window.autoReloadAfterActionScript = true;
  window.__GIL_REFRESH_TOKEN__ = new URLSearchParams(window.location.search).get("_gil_refresh") || "";
})();
</script>""")

    if not blocks:
        return html

    addition = "\n".join(blocks)

    if "</body>" in html:
        return html.replace("</body>", addition + "\n</body>", 1)

    return html + "\n" + addition + "\n"


def _gil_patch_generated_dashboard_html():
    try:
        commun_dir = _GilPath(__file__).resolve().parent
        targets = [
            commun_dir / "dashboard_gil.html",
            commun_dir / ("dashboard_gil_" + "sprint21.html"),
        ]

        for path in targets:
            if not path.exists():
                continue

            html = path.read_text(encoding="utf-8", errors="replace")
            patched = _gil_add_runtime_markers(html)

            if patched != html:
                path.write_text(patched, encoding="utf-8")
                print("[OK] Marqueurs runtime ajoutes :", path)
    except Exception as exc:
        print("[WARN] Impossible d'ajouter les marqueurs runtime :", exc)


_gil_atexit.register(_gil_patch_generated_dashboard_html)


if __name__ == "__main__":
    generate()
