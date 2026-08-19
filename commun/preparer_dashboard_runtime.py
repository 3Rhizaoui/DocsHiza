from pathlib import Path
import argparse
import datetime as dt
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"
JIRA = ROOT / "jira"

parser = argparse.ArgumentParser()
parser.add_argument("--bootstrap", action="store_true")
parser.add_argument("--after-import", action="store_true")
args = parser.parse_args()

HTML_FILES = [
    COMMUN / "dashboard_gil.html",
    COMMUN / "dashboard_gil_sprint21.html",
]


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def copy_runtime_jsons():
    copied = []

    mappings = [
        (JIRA / "dashboard_gil_data.json", COMMUN / "dashboard_gil_data.json"),
        (JIRA / "sprints" / "sprint_courant.json", COMMUN / "sprint_courant.json"),
        (JIRA / "sprints" / "sprint_precedent.json", COMMUN / "sprint_precedent.json"),
        (JIRA / "presentation" / "comparaison_sprints.json", COMMUN / "comparaison_sprints.json"),
        (JIRA / "sprint_courant.json", COMMUN / "sprint_courant.json"),
        (JIRA / "sprint_precedent.json", COMMUN / "sprint_precedent.json"),
        (JIRA / "comparaison_sprints.json", COMMUN / "comparaison_sprints.json"),
    ]

    for src, dst in mappings:
        if copy_if_exists(src, dst):
            copied.append(str(dst.relative_to(ROOT)))

    return copied


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


def inject_runtime(html: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    meta = f'<meta name="gil-build-stamp" content="{stamp}">'

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
        html = html.replace("</body>", js_tag + "\n</body>", 1)
    else:
        html = html + "\n" + js_tag

    return html


def patch_html(path: Path) -> bool:
    if not path.exists():
        return False

    html = path.read_text(encoding="utf-8", errors="replace")
    html = clean_runtime(html)
    html = inject_runtime(html)

    path.write_text(html, encoding="utf-8")
    return True


def main():
    copied = copy_runtime_jsons()

    done = []
    for path in HTML_FILES:
        if patch_html(path):
            done.append(str(path.relative_to(ROOT)))

    if not done:
        raise SystemExit("[ERREUR] Aucun HTML dashboard trouvé à préparer.")

    print("[OK] Dashboard runtime préparé :")
    for item in done:
        print(" -", item)

    if copied:
        print("[OK] JSON runtime copiés dans commun/ :")
        for item in copied:
            print(" -", item)
    else:
        print("[INFO] Aucun JSON runtime à copier pour l'instant.")


if __name__ == "__main__":
    main()
