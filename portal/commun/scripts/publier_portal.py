from pathlib import Path
from gil_logging import log_event, log_exception
from extraction.jira.gil_paths import (
    PAYLOAD_DASHBOARD_FINAL,
    DASHBOARD_GIL_DATA,
)
from datetime import datetime
import json
import os
import shutil
import sys


HERE = Path(__file__).resolve()

PROJECT = None

for candidate in HERE.parents:

    if candidate.name == "portal":
        PROJECT = candidate
        break

if PROJECT is None:
    raise SystemExit(
        "[PORTAL][ERREUR] Racine portal introuvable"
    )


PORTAL = (
    PROJECT
)

DATA_DIR = (
    PORTAL
    / "commun"
    / "data"
)

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)


SOURCE_CANDIDATES = [
    PAYLOAD_DASHBOARD_FINAL,
    DASHBOARD_GIL_DATA,
]


SOURCE = next(
    (
        p
        for p in SOURCE_CANDIDATES
        if p.exists()
    ),
    None
)


if SOURCE is None:

    print(
        "[PORTAL][ERREUR] "
        "Aucun payload dashboard disponible"
    )

    for p in SOURCE_CANDIDATES:
        print(" -", p)

    sys.exit(2)


print(
    "[PORTAL] Source :",
    SOURCE
)

log_event(
    "publication",
    "INFO",
    "PORTAL_SOURCE_SELECTED",
    source=str(SOURCE),
)


# ------------------------------------------------------------
# Lecture + validation JSON
# ------------------------------------------------------------

try:

    data = json.loads(
        SOURCE.read_text(
            encoding="utf-8"
        )
    )

except Exception as exc:

    raise SystemExit(
        "[PORTAL][ERREUR] JSON source invalide : "
        + str(exc)
    )


if not isinstance(data, dict):

    raise SystemExit(
        "[PORTAL][ERREUR] "
        "Le payload racine doit être un objet JSON"
    )


# ------------------------------------------------------------
# Publication atomique du payload complet
# ------------------------------------------------------------

project_out = (
    DATA_DIR
    / "gil_project.json"
)

project_tmp = (
    DATA_DIR
    / "gil_project.json.tmp"
)

shutil.copyfile(
    SOURCE,
    project_tmp
)

os.replace(
    project_tmp,
    project_out
)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def number(value, default=0):

    try:
        return int(value)

    except Exception:
        return default


def recursive_dicts(value):

    if isinstance(value, dict):

        yield value

        for child in value.values():
            yield from recursive_dicts(child)

    elif isinstance(value, list):

        for child in value:
            yield from recursive_dicts(child)


def find_sprint_dates(payload, sprint_name):

    sprint_name_normalized = str(
        sprint_name or ""
    ).strip().lower()

    if not sprint_name_normalized:
        return None, None


    start_keys = (
        "startDate",
        "dateDebut",
        "start",
        "debut",
    )

    end_keys = (
        "endDate",
        "dateFin",
        "end",
        "fin",
    )


    for obj in recursive_dicts(payload):

        labels = [

            obj.get("name"),
            obj.get("nom"),
            obj.get("sprint"),
            obj.get("sprintName"),
        ]

        labels = [
            str(v).strip().lower()
            for v in labels
            if v
        ]


        if (
            sprint_name_normalized
            not in labels
        ):
            continue


        start = next(
            (
                obj.get(k)
                for k in start_keys
                if obj.get(k)
            ),
            None
        )

        end = next(
            (
                obj.get(k)
                for k in end_keys
                if obj.get(k)
            ),
            None
        )


        if start or end:
            return start, end


    return None, None


# ------------------------------------------------------------
# KPI GLOBAL D'ARRIMAGE
# ------------------------------------------------------------

health = data.get(
    "santeFluxArrimage"
)

if not isinstance(health, dict):
    health = {}


total = number(
    health.get("total")
)

delivered = number(
    health.get("prets")
)

in_progress = number(
    health.get("enCours")
)

blocked = number(
    health.get("bugsBloquants")
)

score = number(
    health.get("score")
)


# Fallback défensif
if total <= 0:

    histo = data.get(
        "histoFlux"
    )

    if isinstance(histo, list):
        total = len(histo)


# ------------------------------------------------------------
# SPRINT
# ------------------------------------------------------------

sprint_current = str(
    data.get("sprintCourant")
    or ""
)

sprint_previous = str(
    data.get("sprintPrecedent")
    or ""
)


comparison = data.get(
    "comparaisonSprints"
)

if not isinstance(comparison, list):
    comparison = []


current_row = None

for row in comparison:

    if not isinstance(row, dict):
        continue

    if (
        str(
            row.get("sprint")
            or ""
        ).strip()
        ==
        sprint_current.strip()
    ):
        current_row = row
        break


if (
    current_row is None
    and comparison
    and isinstance(
        comparison[-1],
        dict
    )
):
    current_row = comparison[-1]


if current_row is None:
    current_row = {}


sprint_total = number(
    current_row.get(
        "fluxTotal",
        current_row.get(
            "flux",
            0
        )
    )
)

sprint_delivered = number(
    current_row.get(
        "fluxLivresTotal",
        current_row.get(
            "pretTester",
            0
        )
    )
)

sprint_progress = number(
    current_row.get(
        "fluxEnCoursTotal",
        0
    )
)

sprint_blocked = number(
    current_row.get(
        "fluxBloquesTotal",
        current_row.get(
            "bugsBloquants",
            0
        )
    )
)


start_date, end_date = (
    find_sprint_dates(
        data,
        sprint_current
    )
)


# ------------------------------------------------------------
# META
# ------------------------------------------------------------

generated_at = (
    data.get("generatedAt")
    or datetime.now().astimezone().isoformat()
)


home_data = {

    "schemaVersion":
        "gil-portal-home-v1",

    "generatedAt":
        generated_at,

    "source":
        health.get(
            "source",
            "Payload GIL"
        ),

    "arrimage": {

        "total":
            total,

        "delivered":
            delivered,

        "inProgress":
            in_progress,

        "blocked":
            blocked,

        "score":
            score,

        "status":
            health.get(
                "statut",
                ""
            ),

        "deliveredPct":
            round(
                delivered
                / total
                * 100,
                1
            )
            if total
            else 0,

        "inProgressPct":
            round(
                in_progress
                / total
                * 100,
                1
            )
            if total
            else 0,
    },

    "sprint": {

        "current":
            sprint_current,

        "previous":
            sprint_previous,

        "startDate":
            start_date,

        "endDate":
            end_date,

        "total":
            sprint_total,

        "delivered":
            sprint_delivered,

        "inProgress":
            sprint_progress,

        "blocked":
            sprint_blocked,
    },

    "quality": {

        "anomaliesArrimage":
            len(
                data.get(
                    "anomaliesArrimageDetail"
                )
                or []
            )
    }
}


home_out = (
    DATA_DIR
    / "gil_home.json"
)

home_tmp = (
    DATA_DIR
    / "gil_home.json.tmp"
)

home_tmp.write_text(
    json.dumps(
        home_data,
        ensure_ascii=False,
        indent=2
    )
    + "\n",
    encoding="utf-8"
)

os.replace(
    home_tmp,
    home_out
)


print(
    "[PORTAL][OK] Payload complet :",
    project_out
)

log_event(
    "publication",
    "INFO",
    "GIL_PROJECT_WRITTEN",
    path=str(project_out),
    size=(
        project_out.stat().st_size
        if project_out.exists()
        else 0
    ),
)

print(
    "[PORTAL][OK] Home :",
    home_out
)

log_event(
    "publication",
    "INFO",
    "GIL_HOME_WRITTEN",
    path=str(home_out),
    size=(
        home_out.stat().st_size
        if home_out.exists()
        else 0
    ),
)

print(
    "[PORTAL][KPI]",
    "total=",
    total,
    "| livrés=",
    delivered,
    "| en cours=",
    in_progress,
    "| sprint=",
    sprint_current,
)


log_event(
    "publication",
    "INFO",
    "PORTAL_KPI_PUBLISHED",
    total=total,
    delivered=delivered,
    in_progress=in_progress,
    sprint=sprint_current,
)


log_event(
    "publication",
    "INFO",
    "PUBLICATION_SUCCESS",
    project_path=str(project_out),
    home_path=str(home_out),
)
