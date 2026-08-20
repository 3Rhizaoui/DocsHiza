from pathlib import Path
import re

ROOT = Path.cwd()

# -------------------------------------------------------------------
# 1. Ignorer le profil navigateur SSO local
# -------------------------------------------------------------------
gitignore = ROOT / ".gitignore"
txt = gitignore.read_text(encoding="utf-8", errors="replace") if gitignore.exists() else ""

for line in [
    "jira/.jira_sso_profile_manuel/",
    "audit_reports/",
    "node_modules/",
]:
    if line not in txt.splitlines():
        txt += "\n" + line

gitignore.write_text("\n".join(dict.fromkeys(txt.splitlines())) + "\n", encoding="utf-8")


# -------------------------------------------------------------------
# 2. Désactiver le refresh automatique injecté par le publisher
# -------------------------------------------------------------------
publisher = ROOT / "commun" / "publier_jira_dashboard.py"

if publisher.exists():
    txt = publisher.read_text(encoding="utf-8", errors="replace")

    # Si le publisher appelle encore l'injection auto-refresh, on remplace par un nettoyage non destructif.
    txt = re.sub(
        r'^\s*html\s*=\s*inject_auto_reload_after_actions\(html\)\s*$',
        '    html = remove_auto_reload_after_actions(html)',
        txt,
        flags=re.M,
    )

    # Neutraliser les marqueurs dangereux restants dans les anciens blocs JS.
    txt = txt.replace("_gil_poll", "_gil_disabled_poll")
    txt = txt.replace("_gil_refresh", "_gil_disabled_refresh")
    txt = txt.replace("window.location.replace", "window.__gil_disabled_replace")
    txt = txt.replace("window.location.reload", "window.__gil_disabled_reload")

    # Le publisher ne doit plus bloquer si stableFallbackLoader est absent :
    # il est ajouté ensuite par preparer_dashboard_runtime.py.
    txt = re.sub(
        r'\n\s*if\s+"stableFallbackLoader"\s+not\s+in\s+html:\s*\n\s*stop\("stableFallbackLoader absent après publication"\)\s*',
        "\n",
        txt,
        flags=re.S,
    )

    helper = r'''

def remove_auto_reload_after_actions(html: str) -> str:
    """Supprime les scripts de refresh automatique. L'ouverture finale est gérée par Importer_JIRA.cmd."""
    html = re.sub(
        r'\n?<script\b[^>]*id="autoReloadAfterActionScript"[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )
    html = re.sub(
        r'\n?<script\b[^>]*id="jiraOfficialComparisonStaticScript"[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )
    return html
'''

    if "def remove_auto_reload_after_actions(" not in txt:
        idx = txt.find("\ndef main")
        if idx == -1:
            idx = len(txt)
        txt = txt[:idx] + helper + "\n" + txt[idx:]

    publisher.write_text(txt, encoding="utf-8")
    print("[OK] Publisher nettoyé : plus de refresh automatique injecté")


# -------------------------------------------------------------------
# 3. Désactiver le polling dans runtime_dashboard.js
# -------------------------------------------------------------------
runtime = ROOT / "commun" / "runtime_dashboard.js"

if runtime.exists():
    txt = runtime.read_text(encoding="utf-8", errors="replace")

    # Supprimer complètement la fonction installAutoReload si elle existe.
    marker = "  function installAutoReload() {"
    start = txt.find(marker)

    if start != -1:
        brace_start = txt.find("{", start)
        depth = 0
        end = None

        for i in range(brace_start, len(txt)):
            ch = txt[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end:
            txt = (
                txt[:start]
                + "  // Auto-refresh désactivé : Importer_JIRA.cmd ouvre la page une seule fois en fin de pipeline.\n"
                + txt[end:]
            )

    # Supprimer tout appel restant.
    txt = re.sub(
        r'\n\s*installAutoReload\(\);\s*',
        "\n    // Auto-refresh désactivé.\n",
        txt,
    )

    txt = txt.replace("_gil_poll", "_gil_disabled_poll")
    txt = txt.replace("_gil_refresh", "_gil_disabled_refresh")
    txt = txt.replace("window.location.replace", "window.__gil_disabled_replace")
    txt = txt.replace("window.location.reload", "window.__gil_disabled_reload")

    runtime.write_text(txt, encoding="utf-8")
    print("[OK] Runtime nettoyé : plus de polling navigateur")


print("[OK] Patch refresh multiple terminé")
