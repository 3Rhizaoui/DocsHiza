from pathlib import Path


# ---------------------------------------------------------------------------
# Architecture Portal GIL
#
# portal/
#   commun/
#     data/
#       jira/               <- données runtime JIRA
#     scripts/
#       extraction/
#         jira/             <- moteur d'extraction JIRA
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

EXTRACTION_DIR = SCRIPT_DIR.parent
SCRIPTS_DIR = EXTRACTION_DIR.parent
COMMUN_DIR = SCRIPTS_DIR.parent
PORTAL_DIR = COMMUN_DIR.parent
PROJECT_DIR = PORTAL_DIR.parent

DATA_DIR = COMMUN_DIR / "data"
PAYLOAD_BASE = DATA_DIR / "payload_base.json"

JIRA_DATA_DIR = DATA_DIR / "jira"

SPRINTS_DIR = JIRA_DATA_DIR / "sprints"
PRESENTATION_DIR = JIRA_DATA_DIR / "presentation"

JIRA_BRUT = JIRA_DATA_DIR / "jira_brut.json"
JIRA_DIAGNOSTIC = JIRA_DATA_DIR / "jira_diagnostic.json"
SPRINTS_DASHBOARD = JIRA_DATA_DIR / "sprints_dashboard.json"

SPRINT_COURANT = SPRINTS_DIR / "sprint_courant.json"
SPRINT_PRECEDENT = SPRINTS_DIR / "sprint_precedent.json"

COMPARAISON_SPRINTS = PRESENTATION_DIR / "comparaison_sprints.json"
KPIS_SPRINT = PRESENTATION_DIR / "kpis_sprint.json"
PAYLOAD_DASHBOARD_FINAL = PRESENTATION_DIR / "payload_dashboard_final.json"

DASHBOARD_GIL_DATA = JIRA_DATA_DIR / "dashboard_gil_data.json"

ARCHITECTURE_SPRINTS_DIAGNOSTIC = (
    JIRA_DATA_DIR / "architecture_sprints_diagnostic.json"
)


def ensure_runtime_dirs():
    JIRA_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    PRESENTATION_DIR.mkdir(parents=True, exist_ok=True)
