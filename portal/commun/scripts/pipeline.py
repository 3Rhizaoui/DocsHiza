from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shutil
import subprocess
import sys
import time
import webbrowser


SCRIPT_DIR = Path(__file__).resolve().parent
COMMUN_DIR = SCRIPT_DIR.parent
PORTAL_DIR = COMMUN_DIR.parent
PROJECT_DIR = PORTAL_DIR.parent

JIRA_ENGINE = (
    SCRIPT_DIR
    / "extraction"
    / "jira"
)

PUBLICATION_SCRIPT = (
    SCRIPT_DIR
    / "publier_portal.py"
)

LOG_ROOT = (
    PORTAL_DIR
    / "logs"
)

PIPELINE_LOG_DIR = (
    LOG_ROOT
    / "pipeline"
)

JIRA_LOG_DIR = (
    LOG_ROOT
    / "jira"
)

ERROR_LOG_DIR = (
    LOG_ROOT
    / "errors"
)


def log_event(
    component: str,
    level: str,
    event: str,
    **details,
) -> None:

    now = datetime.now()

    folder = (
        LOG_ROOT
        / component
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        folder
        / f"{component}_{now:%Y-%m-%d}.log"
    )

    payload = {
        "timestamp": now.isoformat(
            timespec="seconds"
        ),
        "level": level,
        "event": event,
        **details,
    }

    with path.open(
        "a",
        encoding="utf-8",
    ) as fh:
        fh.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )
            + "\n"
        )


def resolve_executable(
    name: str,
) -> str:

    found = shutil.which(name)

    if not found:
        raise RuntimeError(
            f"Exécutable introuvable : {name}"
        )

    return found


def run_step(
    index: int,
    total: int,
    name: str,
    command: list[str],
    *,
    cwd: Path = JIRA_ENGINE,
) -> None:

    print()
    print("=" * 68)
    print(
        f"[{index}/{total}] {name}"
    )
    print("=" * 68)
    print(
        "Commande :",
        " ".join(
            str(part)
            for part in command
        ),
    )
    print()

    log_event(
        "pipeline",
        "INFO",
        "PIPELINE_STEP_START",
        step=index,
        total=total,
        name=name,
        command=command,
        cwd=str(cwd),
    )

    started = time.monotonic()

    result = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
    )

    duration = round(
        time.monotonic() - started,
        3,
    )

    if result.returncode != 0:

        log_event(
            "errors",
            "ERROR",
            "PIPELINE_STEP_FAILED",
            step=index,
            name=name,
            returncode=result.returncode,
            duration_seconds=duration,
        )

        raise RuntimeError(
            f"{name} en échec "
            f"(code {result.returncode})"
        )

    log_event(
        "pipeline",
        "INFO",
        "PIPELINE_STEP_SUCCESS",
        step=index,
        name=name,
        duration_seconds=duration,
    )


def main() -> int:

    print()
    print("=" * 68)
    print("GIL PORTAL - PIPELINE JIRA AUTONOME")
    print("=" * 68)
    print()
    print("Portal :", PORTAL_DIR)
    print("Moteur :", JIRA_ENGINE)
    print()

    if not JIRA_ENGINE.exists():
        raise RuntimeError(
            f"Moteur JIRA absent : {JIRA_ENGINE}"
        )

    node = resolve_executable("node")
    python = sys.executable

    steps = [
        (
            "Extraction JIRA via SSO",
            [
                node,
                str(
                    JIRA_ENGINE
                    / "capturer_jira_sso.js"
                ),
            ],
        ),
        (
            "Détection officielle des sprints JIRA",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "construire_sprints_jira.py"
                ),
            ],
        ),
        (
            "Construction architecture JSON des sprints",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "construire_architecture_sprints.py"
                ),
            ],
        ),
        (
            "Audit architecture des sprints",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "auditer_architecture_sprints.py"
                ),
            ],
        ),
        (
            "Préparation source dashboard",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "preparer_source_jira.py"
                ),
            ],
        ),
        (
            "Construction comparaison des sprints",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "construire_comparaison_dashboard.py"
                ),
            ],
        ),
        (
            "Construction payload dashboard final",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "construire_payload_dashboard_final.py"
                ),
            ],
        ),
        (
            "Enrichissement comparaison payload",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "enrichir_payload_comparaison.py"
                ),
            ],
        ),
        (
            "Normalisation payload dashboard",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "normaliser_payload_dashboard.py"
                ),
            ],
        ),
        (
            "Finalisation payload dashboard",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "finaliser_payload_dashboard.py"
                ),
            ],
        ),
        (
            "Contrôle final import JIRA",
            [
                python,
                str(
                    JIRA_ENGINE
                    / "controle_import_jira.py"
                ),
            ],
        ),
        (
            "Publication des données Portal",
            [
                python,
                str(
                    PUBLICATION_SCRIPT
                ),
            ],
        ),
    ]

    log_event(
        "pipeline",
        "INFO",
        "PIPELINE_START",
        steps=len(steps),
        portal=str(PORTAL_DIR),
        engine=str(JIRA_ENGINE),
    )

    try:

        for index, (
            name,
            command,
        ) in enumerate(
            steps,
            1,
        ):

            run_step(
                index,
                len(steps),
                name,
                command,
            )

    except Exception as exc:

        print()
        print("=" * 68)
        print("[ERREUR BLOQUANTE] PIPELINE JIRA INTERROMPU")
        print("=" * 68)
        print(exc)

        log_event(
            "errors",
            "ERROR",
            "PIPELINE_FAILED",
            error=str(exc),
        )

        log_event(
            "pipeline",
            "ERROR",
            "PIPELINE_FAILED",
            error=str(exc),
        )

        return 1

    print()
    print("=" * 68)
    print("PIPELINE JIRA TERMINE AVEC SUCCES")
    print("=" * 68)
    print()
    print(
        "Portal : http://127.0.0.1:8765/"
    )

    log_event(
        "pipeline",
        "INFO",
        "PIPELINE_SUCCESS",
        steps=len(steps),
    )

    refresh_ts = int(
        time.time() * 1000
    )

    refresh_url = (
        "http://127.0.0.1:8765/"
        f"?_gil_refresh={refresh_ts}"
    )

    log_event(
        "publication",
        "INFO",
        "PORTAL_REFRESH_REQUESTED",
        url=refresh_url,
    )

    print()
    print(
        "Ouverture Portal actualisé :",
        refresh_url,
    )

    webbrowser.open(
        refresh_url,
        new=2,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
