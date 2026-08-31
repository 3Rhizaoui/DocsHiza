from pathlib import Path
import sys


ENGINE = (
    Path(__file__).resolve().parents[1]
    / "commun"
    / "scripts"
    / "extraction"
    / "jira"
)

sys.path.insert(
    0,
    str(ENGINE),
)

from join_arrimage import join_arrimage


def test_join_arrimage():

    sprint_tickets = [
        {
            "jiraKey": "TICKET-001",
            "epicKey": "EPIC-ARR-001",
            "statutJira": "Terminé",
        },
        {
            "jiraKey": "TICKET-002",
            "epicKey": "EPIC-ARR-001",
            "statutJira": "En cours",
        },
        {
            "jiraKey": "TICKET-003",
            "epicKey": "EPIC-ARR-002",
            "statutJira": "Done",
        },
        {
            "jiraKey": "TICKET-004",
            "epicKey": "EPIC-NON-ARRIMAGE",
            "statutJira": "Terminé",
        },
        {
            "jiraKey": "TICKET-005",
            "epicKey": "",
            "statutJira": "Terminé",
        },
        {
            "jiraKey": "TICKET-006",
            "epicKey": "EPIC-ARR-003",
            "statutJira": "À faire",
        },
    ]

    arrimage_epics = [
        {
            "jiraKey": "EPIC-ARR-001",
        },
        {
            "jiraKey": "EPIC-ARR-002",
        },
        {
            "jiraKey": "EPIC-ARR-003",
        },
    ]

    rows = join_arrimage(
        sprint_tickets,
        arrimage_epics,
    )

    assert len(rows) == 4

    done = [
        row
        for row in rows
        if row["termine"]
    ]

    assert len(done) == 2

    epics = {
        row["epicJiraKey"]
        for row in rows
    }

    assert epics == {
        "EPIC-ARR-001",
        "EPIC-ARR-002",
        "EPIC-ARR-003",
    }

    tickets = {
        row["ticketJiraKey"]
        for row in rows
    }

    assert tickets == {
        "TICKET-001",
        "TICKET-002",
        "TICKET-003",
        "TICKET-006",
    }


if __name__ == "__main__":

    test_join_arrimage()

    print("=" * 70)
    print("TEST CODE PRODUCTION JOIN ARRIMAGE : OK")
    print("=" * 70)
    print("6 tickets Sprint")
    print("4 contributions Arrimage")
    print("2 terminées")
    print("3 Epics distinctes")
