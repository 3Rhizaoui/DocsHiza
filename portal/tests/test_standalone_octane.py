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

sys.path.insert(0, str(ENGINE))

from normaliser_octane import build_payload


FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "standalone"
    / "qualifications_octane.fixture.json"
)


def test_standalone_octane():

    source = json.loads(
        FIXTURE.read_text(
            encoding="utf-8"
        )
    )

    payload = build_payload(source)
    rows = payload["qualifications"]

    assert len(rows) == 2

    exchange = next(
        row
        for row in rows
        if row["capability"] == "Exchange Layer"
    )

    assert exchange["release"] == "V1"
    assert exchange["environnement"] == "SIT"
    assert exchange["resultats"]["total"] == 3
    assert exchange["resultats"]["pass"] == 2
    assert exchange["resultats"]["fail"] == 1
    assert exchange["resultats"]["tousPass"] is False

    protocol = next(
        row
        for row in rows
        if row["capability"] == "Protocol Conversion"
    )

    assert protocol["release"] == "V2"
    assert protocol["environnement"] == "UAT"
    assert protocol["resultats"]["total"] == 2
    assert protocol["resultats"]["pass"] == 2
    assert protocol["resultats"]["fail"] == 0
    assert protocol["resultats"]["tousPass"] is True


if __name__ == "__main__":

    test_standalone_octane()

    print("=" * 70)
    print("TEST STANDALONE OCTANE : OK")
    print("=" * 70)
    print("Exchange Layer | V1 | SIT | 2 PASS / 1 FAIL")
    print("Protocol Conversion | V2 | UAT | 2 PASS / 0 FAIL")
