from pathlib import Path
import argparse
import datetime as dt
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


def copy_runtime_jsons():
    copied = []

    final_payload = JIRA / "presentation" / "payload_dashboard_final.json"
    base_payload = JIRA / "dashboard_gil_data.json"

    if final_payload.exists():
        shutil.copyfile(final_payload, COMMUN / "dashboard_gil_data.json")
        copied.append("commun/dashboard_gil_data.json")
    elif base_payload.exists():
        shutil.copyfile(base_payload, COMMUN / "dashboard_gil_data.json")
        copied.append("commun/dashboard_gil_data.json")

    optional = [
        (JIRA / "sprints" / "sprint_courant.json", COMMUN / "sprint_courant.json"),
        (JIRA / "sprints" / "sprint_precedent.json", COMMUN / "sprint_precedent.json"),
        (JIRA / "presentation" / "comparaison_sprints.json", COMMUN / "comparaison_sprints.json"),
    ]

    for src, dst in optional:
        if src.exists():
            shutil.copyfile(src, dst)
            copied.append(str(dst.relative_to(ROOT)))

    return copied


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


def inject_runtime(html: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    meta = f'<meta name="gil-build-stamp" content="{stamp}">'
    script = f'<script id="stableFallbackLoader" data-runtime="final-payload" src="runtime_dashboard.js?v={stamp}"></script>'

    if "</head>" in html:
        html = html.replace("</head>", meta + "\n</head>", 1)
    else:
        html = meta + "\n" + html

    if "</body>" in html:
        html = html.replace("</body>", script + "\n</body>", 1)
    else:
        html = html + "\n" + script

    return html


def patch_html(path: Path):
    if not path.exists():
        return False

    html = path.read_text(encoding="utf-8", errors="replace")
    html = clean_runtime(html)
    html = inject_runtime(html)
    path.write_text(html, encoding="utf-8")
    return True


def main():
    copied = copy_runtime_jsons()

    prepared = []
    for path in HTML_FILES:
        if patch_html(path):
            prepared.append(str(path.relative_to(ROOT)))

    if not prepared:
        raise SystemExit("[ERREUR] Aucun HTML dashboard trouvé à préparer.")

    print("[OK] Dashboard runtime préparé :")
    for item in prepared:
        print(" -", item)

    if copied:
        print("[OK] JSON runtime copiés dans commun/ :")
        for item in copied:
            print(" -", item)

    if args.after_import:
        required = [
            COMMUN / "dashboard_gil_data.json",
            COMMUN / "sprint_courant.json",
            COMMUN / "sprint_precedent.json",
            COMMUN / "comparaison_sprints.json",
        ]

        missing = [path for path in required if not path.exists()]
        if missing:
            print("[ERREUR] JSON runtime manquants :")
            for path in missing:
                print(" -", path)
            raise SystemExit(1)

        text = (COMMUN / "dashboard_gil_data.json").read_text(encoding="utf-8", errors="replace")
        if "architectureDashboardFinal" not in text:
            raise SystemExit("[ERREUR] commun/dashboard_gil_data.json n'est pas le payload final")

        print("[OK] Architecture runtime disponible pour le dashboard HTML.")


if __name__ == "__main__":
    main()
