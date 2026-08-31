from __future__ import annotations


def normalize(value):
    return str(value or "").strip()


def is_done(ticket):
    status = normalize(
        ticket.get("statutJira")
        or ticket.get("statut")
        or ticket.get("status")
    ).lower()

    return status in {
        "terminé",
        "termine",
        "done",
    }


def join_arrimage(
    sprint_tickets,
    arrimage_epics,
):
    """
    Jointure métier :

    ticket du sprint
        -> epicKey
        -> Epic Arrimage

    Retourne une liste minimale contenant les deux clés Jira
    et l'état terminé/non terminé.
    """

    epics_by_key = {
        normalize(epic.get("jiraKey")): epic
        for epic in arrimage_epics
        if isinstance(epic, dict)
        and normalize(epic.get("jiraKey"))
    }

    rows = []

    for ticket in sprint_tickets:

        if not isinstance(ticket, dict):
            continue

        ticket_key = normalize(
            ticket.get("jiraKey")
        )

        epic_key = normalize(
            ticket.get("epicKey")
        )

        if not epic_key:
            continue

        epic = epics_by_key.get(
            epic_key
        )

        if not isinstance(epic, dict):
            continue

        rows.append(
            {
                "ticket": ticket,
                "epic": epic,
                "ticketJiraKey": ticket_key,
                "epicJiraKey": epic_key,
                "termine": is_done(ticket),
            }
        )

    return rows
