from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

ENGINE = (
    ROOT
    / "commun"
    / "scripts"
    / "qualite"
    / "standalone"
)

sys.path.insert(
    0,
    str(ENGINE),
)

from construire_payload import build_payload


def jira_row(
    capability,
    version,
    environnement,
    ready=True,
):
    return {
        "jiraKey": "AERL_GIL-100",
        "titre": (
            f"[FEATURE GIL] {capability}"
        ),
        "capability": capability,
        "version": version,
        "environnement": environnement,
        "taches": [],
        "jiraReadiness": {
            "total": 2,
            "readyForTest": (
                2 if ready else 1
            ),
            "nonReady": (
                0 if ready else 1
            ),
            "pret": ready,
        },
    }


def octane_row(
    capability,
    release,
    environnement,
    all_pass=True,
):
    return {
        "capability": capability,
        "release": release,
        "environnement": environnement,
        "testSuite": {
            "id": "901502",
            "nom": (
                f"TS-GIL - {capability}"
            ),
        },
        "executions": [],
        "resultats": {
            "total": 2,
            "pass": (
                2 if all_pass else 1
            ),
            "fail": (
                0 if all_pass else 1
            ),
            "autres": 0,
            "tousPass": all_pass,
        },
        "derniereExecution":
            "2026-04-29T10:00:00",
    }


def test_strict_join():

    jira = {
        "generatedAt":
            "2026-08-31T20:00:00",
        "capabilities": [
            jira_row(
                "Exchange Layer",
                "V1",
                "SIT",
            )
        ],
    }

    octane = {
        "generatedAt":
            "2026-08-31T20:00:00",
        "qualifications": [
            octane_row(
                "Exchange Layer",
                "V2",
                "SIT",
            ),
            octane_row(
                "Exchange Layer",
                "V1",
                "UAT",
            ),
            octane_row(
                "Exchange Layer",
                "V1",
                "SIT",
            ),
        ],
    }

    payload = build_payload(
        jira,
        octane,
    )

    row = payload[
        "capabilities"
    ][0]

    assert row[
        "matching"
    ]["trouve"] is True

    assert row[
        "matching"
    ]["ambigu"] is False

    assert row[
        "matching"
    ]["nombreCorrespondances"] == 1

    assert row[
        "octane"
    ]["release"] == "V1"

    assert row[
        "octane"
    ]["environnement"] == "SIT"

    assert row[
        "readyForUse"
    ] is True


def test_wrong_version_does_not_match():

    jira = {
        "capabilities": [
            jira_row(
                "Exchange Layer",
                "V1",
                "SIT",
            )
        ]
    }

    octane = {
        "qualifications": [
            octane_row(
                "Exchange Layer",
                "V2",
                "SIT",
            )
        ]
    }

    row = build_payload(
        jira,
        octane,
    )["capabilities"][0]

    assert row[
        "matching"
    ]["trouve"] is False

    assert row["octane"] is None
    assert row["readyForUse"] is False


def test_wrong_environment_does_not_match():

    jira = {
        "capabilities": [
            jira_row(
                "Exchange Layer",
                "V1",
                "SIT",
            )
        ]
    }

    octane = {
        "qualifications": [
            octane_row(
                "Exchange Layer",
                "V1",
                "UAT",
            )
        ]
    }

    row = build_payload(
        jira,
        octane,
    )["capabilities"][0]

    assert row[
        "matching"
    ]["trouve"] is False

    assert row["octane"] is None
    assert row["readyForUse"] is False


def test_failed_octane_blocks_ready():

    jira = {
        "capabilities": [
            jira_row(
                "Exchange Layer",
                "V1",
                "SIT",
            )
        ]
    }

    octane = {
        "qualifications": [
            octane_row(
                "Exchange Layer",
                "V1",
                "SIT",
                all_pass=False,
            )
        ]
    }

    row = build_payload(
        jira,
        octane,
    )["capabilities"][0]

    assert row[
        "matching"
    ]["trouve"] is True

    assert row[
        "readyForUse"
    ] is False


def test_jira_not_ready_blocks_ready():

    jira = {
        "capabilities": [
            jira_row(
                "Exchange Layer",
                "V1",
                "SIT",
                ready=False,
            )
        ]
    }

    octane = {
        "qualifications": [
            octane_row(
                "Exchange Layer",
                "V1",
                "SIT",
            )
        ]
    }

    row = build_payload(
        jira,
        octane,
    )["capabilities"][0]

    assert row[
        "matching"
    ]["trouve"] is True

    assert row[
        "readyForUse"
    ] is False


def test_duplicate_octane_is_ambiguous():

    jira = {
        "capabilities": [
            jira_row(
                "Exchange Layer",
                "V1",
                "SIT",
            )
        ]
    }

    octane = {
        "qualifications": [
            octane_row(
                "Exchange Layer",
                "V1",
                "SIT",
            ),
            octane_row(
                "Exchange Layer",
                "V1",
                "SIT",
            ),
        ]
    }

    row = build_payload(
        jira,
        octane,
    )["capabilities"][0]

    assert row[
        "matching"
    ]["trouve"] is False

    assert row[
        "matching"
    ]["ambigu"] is True

    assert row[
        "matching"
    ]["nombreCorrespondances"] == 2

    assert row["octane"] is None
    assert row["readyForUse"] is False


if __name__ == "__main__":

    test_strict_join()
    test_wrong_version_does_not_match()
    test_wrong_environment_does_not_match()
    test_failed_octane_blocks_ready()
    test_jira_not_ready_blocks_ready()
    test_duplicate_octane_is_ambiguous()

    print("=" * 70)
    print(
        "TEST PAYLOAD STANDALONE : OK"
    )
    print("=" * 70)
    print(
        "OK  Capability + Version + Env"
    )
    print(
        "OK  mauvaise Version rejetée"
    )
    print(
        "OK  mauvais Environnement rejeté"
    )
    print(
        "OK  FAIL Octane bloque Ready for use"
    )
    print(
        "OK  JIRA non Ready bloque Ready for use"
    )
    print(
        "OK  doublon Octane détecté comme ambigu"
    )
