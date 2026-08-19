from pathlib import Path
import argparse
import datetime as dt
import json
import re

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"

parser = argparse.ArgumentParser()
parser.add_argument("--bootstrap", action="store_true")
parser.add_argument("--after-import", action="store_true")
args = parser.parse_args()

HTML_FILES = [
    COMMUN / "dashboard_gil.html",
    COMMUN / "dashboard_gil_sprint21.html",
]


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def official_rows():
    path = ROOT / "jira" / "sprints_dashboard.json"

    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []

    rows = []

    for key in ["precedent", "courant"]:
        item = data.get(key) or {}
        if not isinstance(item, dict):
            continue

        name = (
            item.get("nom")
            or item.get("name")
            or item.get("sprint")
            or item.get("label")
            or ("Sprint précédent" if key == "precedent" else "Sprint courant")
        )

        flux = safe_int(item.get("flux"))
        anomalies = safe_int(item.get("anomalies"))
        total = safe_int(item.get("total"), flux + anomalies)

        if not total:
            total = flux + anomalies

        rows.append({
            "sprint": name,
            "flux": flux,
            "anomalies": anomalies,
            "total": total,
            "type": key,
        })

    return rows


def clean_runtime(html: str) -> str:
    ids = [
        "stableFallbackLoader",
        "autoReloadAfterActionScript",
        "jiraOfficialComparisonFallbackScript",
        "jiraOfficialComparisonStaticScript",
        "jiraOfficialSprintRowsData",
    ]

    for script_id in ids:
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


def inject_runtime(html: str, rows: list) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")

    meta = f'<meta name="gil-build-stamp" content="{stamp}">'

    safe_json = (
        json.dumps(rows, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    data_tag = f'<script id="jiraOfficialSprintRowsData" type="application/json">{safe_json}</script>'

    js_tag = (
        f'<script id="stableFallbackLoader" '
        f'data-auto="autoReloadAfterActionScript" '
        f'data-comparison="jiraOfficialComparisonStaticScript" '
        f'src="runtime_dashboard.js?v={stamp}"></script>'
    )

    if "</head>" in html:
        html = html.replace("</head>", meta + "\n</head>", 1)
    else:
        html = meta + "\n" + html

    if "</body>" in html:
        html = html.replace("</body>", data_tag + "\n" + js_tag + "\n</body>", 1)
    else:
        html = html + "\n" + data_tag + "\n" + js_tag

    return html


def patch_html(path: Path, rows: list) -> bool:
    if not path.exists():
        return False

    html = path.read_text(encoding="utf-8", errors="replace")
    html = clean_runtime(html)
    html = inject_runtime(html, rows)

    path.write_text(html, encoding="utf-8")
    return True


def main():
    rows = official_rows()
    done = []

    for path in HTML_FILES:
        if patch_html(path, rows):
            done.append(str(path.relative_to(ROOT)))

    if not done:
        raise SystemExit("[ERREUR] Aucun HTML dashboard trouvé à préparer.")

    print("[OK] Dashboard runtime préparé :")
    for item in done:
        print(" -", item)

    if rows:
        print("[OK] Comparaison officielle injectée :")
        for row in rows:
            print(f" - {row['sprint']} | total:{row['total']} | flux:{row['flux']} | anomalies:{row['anomalies']}")
    else:
        print("[INFO] Aucun sprints_dashboard.json disponible : comparaison officielle non injectée.")


if __name__ == "__main__":
    main()
