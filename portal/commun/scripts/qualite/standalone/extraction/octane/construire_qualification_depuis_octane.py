from __future__ import annotations

import json
import sys
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


def text(value) -> str:
    return str(value or "").strip()


def capability_name(value: str) -> str:
    name = text(value)

    prefix = "GIL - "

    if name.lower().startswith(
        prefix.lower()
    ):
        return name[len(prefix):].strip()

    return name


def build_qualification(
    source: dict,
) -> dict:

    capability = (
        source.get("capability")
        or {}
    )

    release = (
        source.get("release")
        or {}
    )

    environment = (
        source.get("environment")
        or {}
    )

    suite = (
        source.get("testSuite")
        or {}
    )

    suite_run = (
        source.get("suiteRun")
        or {}
    )

    runs = []

    for row in source.get("runs") or []:

        if not isinstance(row, dict):
            continue

        runs.append({
            "id": text(
                row.get("id")
            ),
            "nom": text(
                row.get("name")
                or row.get("nom")
            ),
            "statut": text(
                row.get("status")
                or row.get("statut")
            ),
            "dateExecution": text(
                row.get("executionDate")
                or row.get("dateExecution")
            ),
            "release": text(
                row.get("release")
            ),
            "environnement": text(
                row.get("environment")
                or row.get("environnement")
            ).upper(),
            "preuves": (
                row.get("proofs")
                or row.get("preuves")
                or []
            ),
        })

    return {
        "capability": capability_name(
            capability.get("name")
        ),

        "octaneFeature": {
            "id": text(
                capability.get("id")
            ),
            "nom": text(
                capability.get("name")
            ),
        },

        "release": text(
            release.get("name")
        ),

        "environnement": text(
            environment.get("name")
        ).upper(),

        "testSuite": {
            "id": text(
                suite.get("id")
            ),
            "nom": text(
                suite.get("name")
            ),
            "testsPlanifies": int(
                suite.get(
                    "plannedTests",
                    0,
                )
                or 0
            ),
        },

        "suiteRun": {
            "id": text(
                suite_run.get("id")
            ),
            "nom": text(
                suite_run.get("name")
            ),
        },

        "executions": runs,
    }


def build_payload(
    source: dict,
) -> dict:

    qualification = (
        build_qualification(
            source
        )
    )

    return {
        "schemaVersion": 1,
        "generatedAt": source.get(
            "generatedAt"
        ),
        "source": {
            "type": "OCTANE",
        },
        "qualifications": [
            qualification
        ],
    }


def main(
    source_path: Path,
    target_path: Path = OCTANE_BRUT,
) -> int:

    source = json.loads(
        source_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    payload = build_payload(
        source
    )

    ensure_runtime_dirs()

    target_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "OK - qualification Octane construite"
    )

    print(
        "Cible :",
        target_path,
    )

    return 0


if __name__ == "__main__":

    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python construire_qualification_depuis_octane.py <source.json>"
        )

    raise SystemExit(
        main(
            Path(sys.argv[1])
        )
    )
