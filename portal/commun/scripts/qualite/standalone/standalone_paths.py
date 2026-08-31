from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

QUALITE_SCRIPTS_DIR = SCRIPT_DIR.parent
SCRIPTS_DIR = QUALITE_SCRIPTS_DIR.parent
COMMUN_DIR = SCRIPTS_DIR.parent
PORTAL_DIR = COMMUN_DIR.parent
PROJECT_DIR = PORTAL_DIR.parent


DATA_DIR = COMMUN_DIR / "data"
STANDALONE_DATA_DIR = DATA_DIR / "standalone"

JIRA_DATA_DIR = STANDALONE_DATA_DIR / "jira"
OCTANE_DATA_DIR = STANDALONE_DATA_DIR / "octane"


JIRA_BRUT = JIRA_DATA_DIR / "capabilities_brut.json"
JIRA_NORMALISE = JIRA_DATA_DIR / "capabilities.json"

OCTANE_BRUT = OCTANE_DATA_DIR / "qualifications_brut.json"
OCTANE_NORMALISE = OCTANE_DATA_DIR / "qualifications.json"

PAYLOAD_STANDALONE = (
    STANDALONE_DATA_DIR
    / "payload_standalone.json"
)


def ensure_runtime_dirs():
    JIRA_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OCTANE_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
