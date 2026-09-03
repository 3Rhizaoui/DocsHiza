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


def normalize_execution_qualification(
    row: dict,
    execution: dict,
) -> dict:

    normalized_execution = (
        normalize_execution(
            execution
        )
    )

    suite = (
        row.get("testSuite")
        or {}
    )

    suite_run = (
        row.get("suiteRun")
        or {}
    )

    octane_feature = (
        row.get("octaneFeature")
        or {}
    )

    status = (
        normalized_execution[
            "statut"
        ]
    )

    if normalized_execution["pass"]:
        etat = "Validé"

    elif normalized_execution["fail"]:
        etat = "Non validé"

    else:
        etat = (
            status
            or "Non déterminé"
        )

    release = text(
        normalized_execution.get(
            "release"
        )
        or suite_run.get(
            "release"
        )
        or row.get(
            "release"
        )
    )

    environnement = text(
        normalized_execution.get(
            "environnement"
        )
        or row.get(
            "environnement"
        )
        or row.get(
            "environment"
        )
    ).upper()

    sprint = text(
        normalized_execution.get(
            "sprint"
        )
        or suite_run.get(
            "sprint"
        )
    )

    jalon = text(
        normalized_execution.get(
            "jalon"
        )
        or suite_run.get(
            "jalon"
        )
        or suite_run.get(
            "milestone"
        )
    )

    execute_par = text(
        normalized_execution.get(
            "executePar"
        )
        or suite_run.get(
            "executePar"
        )
        or suite_run.get(
            "runBy"
        )
    )

    capability = text(
        normalized_execution.get(
            "nom"
        )
    )

    return {
        # Clé métier Octane destinée au futur
        # rapprochement avec la Capability JIRA.
        #
        # Elle correspond au "Nom du test (initial)"
        # observé dans l'interface Octane.
        "capability":
            capability,

        "capabilityOctane":
            capability,

        # Conservation du niveau supérieur pour
        # diagnostic et traçabilité.
        "qualificationParente": text(
            row.get("capability")
        ),

        "release":
            release,

        "environnement":
            environnement,

        "statut":
            status,

        "dateExecution":
            normalized_execution.get(
                "dateExecution"
            )
            or "",

        "sprint":
            sprint,

        "jalon":
            jalon,

        "executePar":
            execute_par,

        "etat":
            etat,

        "octaneFeature": {
            "id": text(
                octane_feature.get("id")
            ),
            "nom": text(
                octane_feature.get("nom")
                or octane_feature.get(
                    "name"
                )
            ),
        },

        "testSuite": {
            "id": text(
                suite.get("id")
            ),
            "nom": text(
                suite.get("nom")
                or suite.get("name")
            ),
            "testsPlanifies": int(
                suite.get(
                    "testsPlanifies"
                )
                or suite.get(
                    "plannedTests"
                )
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
            "release":
                release,
            "sprint":
                sprint,
            "jalon":
                jalon,
            "executePar":
                execute_par,
        },

        # On conserve executions[] pour compatibilité
        # avec le reste de la chaîne, mais désormais
        # une ligne métier = une seule exécution.
        "executions": [
            normalized_execution
        ],

        "resultats": {
            "total": 1,
            "pass": (
                1
                if normalized_execution[
                    "pass"
                ]
                else 0
            ),
            "fail": (
                1
                if normalized_execution[
                    "fail"
                ]
                else 0
            ),
            "autres": (
                0
                if (
                    normalized_execution[
                        "pass"
                    ]
                    or normalized_execution[
                        "fail"
                    ]
                )
                else 1
            ),
            "tousPass":
                normalized_execution[
                    "pass"
                ],
        },

        "derniereExecution":
            normalized_execution.get(
                "dateExecution"
            )
            or "",
    }


def build_payload(data: dict) -> dict:
    qualifications = []

    for row in (
        data.get("qualifications")
        or []
    ):

        if not isinstance(
            row,
            dict,
        ):
            continue

        executions = (
            row.get("executions")
            or []
        )

        for execution in executions:

            if not isinstance(
                execution,
                dict,
            ):
                continue

            qualifications.append(
                normalize_execution_qualification(
                    row,
                    execution,
                )
            )

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
