from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
STANDALONE_DIR = SCRIPT_DIR.parent

sys.path.insert(
    0,
    str(STANDALONE_DIR),
)

from standalone_paths import (
    OCTANE_BRUT,
    OCTANE_NORMALISE,
    ensure_runtime_dirs,
)


PASS_STATUSES = {
    "réussi",
    "reussi",
    "passed",
    "pass",
    "success",
}


FAIL_STATUSES = {
    "échec",
    "echec",
    "failed",
    "fail",
}


def text(value) -> str:
    return str(value or "").strip()


def normalized(value) -> str:
    return text(value).lower()


def normalize_execution(execution: dict) -> dict:
    status = text(
        execution.get("statut")
        or execution.get("status")
    )

    normalized_status = normalized(status)

    error = (
        execution.get("erreur")
        if isinstance(
            execution.get("erreur"),
            dict,
        )
        else {}
    )

    return {
        "id": text(
            execution.get("id")
        ),

        "nom": text(
            execution.get("nom")
            or execution.get("name")
        ),

        "statut": status,

        "pass":
            normalized_status in PASS_STATUSES,

        "fail":
            normalized_status in FAIL_STATUSES,

        "dateExecution": text(
            execution.get("dateExecution")
            or execution.get("executionDate")
        ),

        "duree":
            execution.get("duree"),

        "release": text(
            execution.get("release")
        ),

        "environnement": text(
            execution.get("environnement")
            or execution.get("environment")
        ).upper(),

        "sprint": text(
            execution.get("sprint")
        ),

        "jalon": text(
            execution.get("jalon")
            or execution.get("milestone")
        ),

        "executePar": text(
            execution.get("executePar")
            or execution.get("runBy")
        ),

        "sousType": text(
            execution.get("sousType")
            or execution.get("subtype")
        ),

        "ordre":
            execution.get("ordre"),

        "erreur": {
            "type": text(
                error.get("type")
            ),
            "message": text(
                error.get("message")
            ),
            "details": text(
                error.get("details")
            ),
        },

        "preuves":
            execution.get("preuves") or [],
    }


def normalize_qualification(row: dict) -> dict:
    executions = [
        normalize_execution(execution)
        for execution in (
            row.get("executions") or []
        )
        if isinstance(execution, dict)
    ]

    passed = sum(
        1
        for execution in executions
        if execution["pass"]
    )

    failed = sum(
        1
        for execution in executions
        if execution["fail"]
    )

    suite = row.get("testSuite") or {}
    suite_run = row.get("suiteRun") or {}
    octane_feature = row.get("octaneFeature") or {}

    dates = [
        execution["dateExecution"]
        for execution in executions
        if execution["dateExecution"]
    ]

    return {
        "capability": text(
            row.get("capability")
        ),
        "release": text(
            row.get("release")
        ),
        "environnement": text(
            row.get("environnement")
            or row.get("environment")
        ).upper(),
        "octaneFeature": {
            "id": text(
                octane_feature.get("id")
            ),
            "nom": text(
                octane_feature.get("nom")
                or octane_feature.get("name")
            ),
        },
        "testSuite": {
            "id": text(suite.get("id")),
            "nom": text(
                suite.get("nom")
                or suite.get("name")
            ),
            "testsPlanifies": int(
                suite.get("testsPlanifies")
                or suite.get("plannedTests")
                or 0
            ),
        },
        "suiteRun": {
            "id": text(
                suite_run.get("id")
            ),

            "nom": text(
                suite_run.get("nom")
                or suite_run.get("name")
            ),

            "statut": text(
                suite_run.get("statut")
                or suite_run.get("status")
            ),

            "dateDebut": text(
                suite_run.get("dateDebut")
                or suite_run.get("started")
            ),

            "release": text(
                suite_run.get("release")
            ),

            "sprint": text(
                suite_run.get("sprint")
            ),

            "jalon": text(
                suite_run.get("jalon")
                or suite_run.get("milestone")
            ),

            "executePar": text(
                suite_run.get("executePar")
                or suite_run.get("runBy")
            ),
        },
        "executions": executions,
        "resultats": {
            "total": len(executions),
            "pass": passed,
            "fail": failed,
            "autres": (
                len(executions)
                - passed
                - failed
            ),
            "tousPass": (
                len(executions) > 0
                and passed == len(executions)
            ),
        },
        "derniereExecution": (
            max(dates)
            if dates
            else ""
        ),
    }


def build_payload(data: dict) -> dict:
    qualifications = [
        normalize_qualification(row)
        for row in (
            data.get("qualifications") or []
        )
        if isinstance(row, dict)
    ]

    qualifications.sort(
        key=lambda row: (
            row.get("release") or "",
            row.get("environnement") or "",
            row.get("capability") or "",
        )
    )

    return {
        "schemaVersion": 1,
        "generatedAt": data.get("generatedAt"),
        "source": "OCTANE",
        "qualifications": qualifications,
    }


def main(
    source: Path = OCTANE_BRUT,
    target: Path = OCTANE_NORMALISE,
) -> int:

    if not source.exists():
        raise SystemExit(
            f"Source absente : {source}"
        )

    data = json.loads(
        source.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    payload = build_payload(data)

    ensure_runtime_dirs()

    target.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "OK - qualifications Octane normalisées :",
        len(payload["qualifications"]),
    )

    print("Cible :", target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
