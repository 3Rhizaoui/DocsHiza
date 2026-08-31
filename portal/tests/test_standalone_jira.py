from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]

ENGINE = (
    ROOT
    / "commun"
    / "scripts"
    / "qualite"
    / "standalone"
    / "normalisation"
)

sys.path.insert(
    0,
    str(ENGINE),
)

from normaliser_jira import build_payload


FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "standalone"
    / "capabilities_brut.fixture.json"
)


def test_standalone_jira():

    source = json.loads(
        FIXTURE.read_text(
            encoding="utf-8"
        )
    )

    payload = build_payload(
        source
    )

    rows = payload[
        "capabilities"
    ]

    assert len(rows) == 2

    exchange = next(
        row
        for row in rows
        if row["capability"]
        == "Exchange Layer"
    )

    assert exchange["version"] == "V1"
    assert exchange["environnement"] == "SIT"
    assert exchange["jiraReadiness"]["total"] == 2
    assert exchange["jiraReadiness"]["readyForTest"] == 2
    assert exchange["jiraReadiness"]["pret"] is True

    protocol = next(
        row
        for row in rows
        if row["capability"]
        == "Protocol Conversion"
    )

    assert protocol["version"] == "V2"
    assert protocol["environnement"] == "UAT"
    assert protocol["jiraReadiness"]["total"] == 2
    assert protocol["jiraReadiness"]["readyForTest"] == 1
    assert protocol["jiraReadiness"]["pret"] is False


if __name__ == "__main__":

    test_standalone_jira()

    print("=" * 70)
    print(
        "TEST STANDALONE JIRA : OK"
    )
    print("=" * 70)

    print(
        "Exchange Layer | V1 | SIT | 2/2 Ready for Test"
    )

    print(
        "Protocol Conversion | V2 | UAT | 1/2 Ready for Test"
    )
