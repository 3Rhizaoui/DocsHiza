from pathlib import Path
import argparse
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

RUNTIME_JSONS = [
    COMMUN / "dashboard_gil_data.json",
    COMMUN / "sprint_courant.json",
    COMMUN / "sprint_precedent.json",
    COMMUN / "comparaison_sprints.json",
]


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


def main():
    removed = []

    for path in RUNTIME_JSONS:
        if path.exists():
            path.unlink()
            removed.append(str(path.relative_to(ROOT)))

    patched = []
    for path in HTML_FILES:
        if not path.exists():
            continue

        html = path.read_text(encoding="utf-8", errors="replace")
        html = clean_runtime(html)
        path.write_text(html, encoding="utf-8")
        patched.append(str(path.relative_to(ROOT)))

    if removed:
        print("[OK] JSON runtime obsolètes supprimés :")
        for item in removed:
            print(" -", item)

    print("[OK] HTML nettoyé du runtime navigateur :")
    for item in patched:
        print(" -", item)


if __name__ == "__main__":
    main()
