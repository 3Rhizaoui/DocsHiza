from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
STANDALONE_DIR = SCRIPT_DIR.parent

sys.path.insert(
    0,
    str(STANDALONE_DIR),
)

from standalone_paths import (
    JIRA_BRUT,
    JIRA_NORMALISE,
    ensure_runtime_dirs,
)


READY_STATUSES = {
    "ready for test",
    "termine",
    "terminé",
    "done",
}


def text(value) -> str:
    return str(value or "").strip()


def normalize_status(value) -> str:
    return text(value).lower()


def capability_name(summary: str) -> str:
    value = re.sub(
        r"^\s*\[\s*FEATURE\s+GIL\s*\]\s*[-:]?\s*",
        "",
        text(summary),
        flags=re.I,
    )

    return value.strip()


def version_from_fields(fields: dict) -> str:
    versions = fields.get("fixVersions") or []

    if isinstance(versions, dict):
        versions = [versions]

    if isinstance(versions, list):
        names = []

        for item in versions:
            if isinstance(item, dict):
                name = text(
                    item.get("name")
                )
            else:
                name = text(item)

            if name:
                names.append(name)

        return " / ".join(names)

    return text(versions)


def environment_field_ids(field_names: dict) -> list[str]:
    result = []

    for field_id, label in (
        field_names or {}
    ).items():
        normalized = text(label).lower()

        if (
            "environnement" in normalized
            or "environment" in normalized
        ):
            result.append(field_id)

    return result


def environment_from_fields(
    fields: dict,
    field_names: dict,
) -> str:

    candidates = []

    for field_id in environment_field_ids(
        field_names
    ):
        candidates.append(
            fields.get(field_id)
        )

    candidates.extend(
        [
            fields.get("environment"),
            fields.get("environnement"),
        ]
    )

    for value in candidates:
        if isinstance(value, dict):
            value = (
                value.get("value")
                or value.get("name")
                or value.get("label")
            )

        if isinstance(value, list):
            values = []

            for item in value:
                if isinstance(item, dict):
                    item = (
                        item.get("value")
                        or item.get("name")
                        or item.get("label")
                    )

                item = text(item)

                if item:
                    values.append(item)

            value = " / ".join(values)

        value = text(value).upper()

        if value in {"SIT", "UAT"}:
            return value

        if "SIT" in value:
            return "SIT"

        if "UAT" in value:
            return "UAT"

    return ""


def issue_status(issue: dict) -> str:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}

    if isinstance(status, dict):
        return text(
            status.get("name")
            or status.get("value")
        )

    return text(status)


def normalize_task(issue: dict) -> dict:
    fields = issue.get("fields") or {}
    status = issue_status(issue)

    return {
        "jiraKey": text(issue.get("key")),
        "titre": text(
            fields.get("summary")
        ),
        "statut": status,
        "readyForTest": (
            normalize_status(status)
            in READY_STATUSES
        ),
    }


def normalize_capability(
    row: dict,
    field_names: dict,
) -> dict:

    epic = row.get("epic") or {}
    fields = epic.get("fields") or {}

    tasks = [
        normalize_task(issue)
        for issue in (
            row.get("children") or []
        )
        if isinstance(issue, dict)
    ]

    ready_count = sum(
        1
        for task in tasks
        if task["readyForTest"]
    )

    total = len(tasks)

    return {
        "jiraKey": text(
            epic.get("key")
        ),
        "titre": text(
            fields.get("summary")
        ),
        "capability": capability_name(
            fields.get("summary")
        ),
        "version": version_from_fields(
            fields
        ),
        "environnement": environment_from_fields(
            fields,
            field_names,
        ),
        "taches": tasks,
        "jiraReadiness": {
            "total": total,
            "readyForTest": ready_count,
            "nonReady": (
                total - ready_count
            ),
            "pret": (
                total > 0
                and ready_count == total
            ),
        },
    }


def build_payload(data: dict) -> dict:
    field_names = (
        data.get("fields") or {}
    )

    capabilities = [
        normalize_capability(
            row,
            field_names,
        )
        for row in (
            data.get("capabilities") or []
        )
        if isinstance(row, dict)
    ]

    capabilities.sort(
        key=lambda row: (
            row.get("version") or "",
            row.get("environnement") or "",
            row.get("capability") or "",
        )
    )

    return {
        "schemaVersion": 1,
        "generatedAt": data.get(
            "generatedAt"
        ),
        "source": "JIRA",
        "capabilities": capabilities,
    }


def main(
    source: Path = JIRA_BRUT,
    target: Path = JIRA_NORMALISE,
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
        "OK - capabilities JIRA normalisées :",
        len(
            payload.get(
                "capabilities"
            ) or []
        ),
    )

    print(
        "Cible :",
        target,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
