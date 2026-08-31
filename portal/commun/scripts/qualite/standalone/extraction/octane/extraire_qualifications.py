from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
STANDALONE_DIR = SCRIPT_DIR.parents[1]

sys.path.insert(
    0,
    str(STANDALONE_DIR),
)

from standalone_paths import (
    OCTANE_BRUT,
    ensure_runtime_dirs,
)


CONFIG_FILE = (
    SCRIPT_DIR
    / "octane_config_standalone.json"
)


def text(value) -> str:
    return str(value or "").strip()


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise SystemExit(
            f"Configuration Octane absente : {CONFIG_FILE}"
        )

    data = json.loads(
        CONFIG_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    # Les variables d'environnement ont priorité.
    # Aucun secret ni paramètre BNP n'est committé.
    base_url = text(
        os.environ.get("GIL_OCTANE_BASE_URL")
        or data.get("base_url")
    ).rstrip("/")

    shared_space = text(
        os.environ.get("GIL_OCTANE_SHARED_SPACE")
        or data.get("shared_space")
    )

    workspace = text(
        os.environ.get("GIL_OCTANE_WORKSPACE")
        or data.get("workspace")
    )

    return {
        "baseUrl": base_url,
        "sharedSpace": shared_space,
        "workspace": workspace,
        "businessRules": (
            data.get("business_rules")
            or {}
        ),
    }


def validate_config(config: dict) -> list[str]:
    missing = []

    if not config["baseUrl"]:
        missing.append("GIL_OCTANE_BASE_URL")

    if not config["sharedSpace"]:
        missing.append("GIL_OCTANE_SHARED_SPACE")

    if not config["workspace"]:
        missing.append("GIL_OCTANE_WORKSPACE")

    return missing


def workspace_api(config: dict) -> str:
    return (
        f'{config["baseUrl"]}'
        f'/api/shared_spaces/'
        f'{config["sharedSpace"]}'
        f'/workspaces/'
        f'{config["workspace"]}'
    )


def build_empty_payload(
    config: dict,
    diagnostic: dict,
) -> dict:
    return {
        "schemaVersion": 1,
        "generatedAt": (
            datetime.now()
            .astimezone()
            .isoformat(
                timespec="seconds"
            )
        ),
        "source": {
            "type": "OCTANE",
            "baseUrl": config["baseUrl"],
            "sharedSpace": config["sharedSpace"],
            "workspace": config["workspace"],
        },
        "businessRules": (
            config["businessRules"]
        ),
        "qualifications": [],
        "diagnostic": diagnostic,
    }


def main() -> int:
    config = load_config()

    missing = validate_config(
        config
    )

    print()
    print("=" * 70)
    print(
        "GIL STANDALONE - EXTRACTION OCTANE"
    )
    print("=" * 70)
    print()

    if missing:
        print(
            "Configuration Octane incomplète."
        )
        print()
        print(
            "Variables requises :"
        )

        for name in missing:
            print(" -", name)

        print()
        print(
            "Aucune connexion Octane n'a été tentée."
        )

        return 2

    api = workspace_api(config)

    print(
        "Base Octane :",
        config["baseUrl"],
    )

    print(
        "Shared space :",
        config["sharedSpace"],
    )

    print(
        "Workspace :",
        config["workspace"],
    )

    print(
        "API workspace :",
        api,
    )

    # ---------------------------------------------------------
    # IMPORTANT
    #
    # Pas encore de requête réseau ici.
    #
    # Il faut d'abord confirmer sur l'environnement BNP :
    # - méthode d'authentification,
    # - noms réels des entités,
    # - champs Capability / Release / Environment,
    # - relation campagne -> tests -> runs -> pièces jointes.
    # ---------------------------------------------------------

    ensure_runtime_dirs()

    payload = build_empty_payload(
        config,
        {
            "status": "CONFIGURED_NOT_EXTRACTED",
            "workspaceApi": api,
            "message": (
                "Configuration validée. "
                "Connecteur métier Octane à compléter "
                "après identification de l'API réelle."
            ),
        },
    )

    OCTANE_BRUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "OK - configuration technique validée"
    )

    print(
        "Diagnostic écrit dans :",
        OCTANE_BRUT,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
