from __future__ import annotations

import re

ARRIMAGE_SUMMARY_RE = re.compile(
    r"\[[^\]]*Arrimage[^\]]*\]",
    re.IGNORECASE,
)


def is_arrimage_epic(issue: dict) -> bool:
    """
    Vrai uniquement si le titre contient
    un bloc [...] dans lequel apparaît Arrimage.
    """

    if not isinstance(issue, dict):
        return False

    summary = str(
        issue.get("summary")
        or issue.get("fields", {}).get("summary")
        or ""
    ).strip()

    return bool(
        ARRIMAGE_SUMMARY_RE.search(summary)
    )
