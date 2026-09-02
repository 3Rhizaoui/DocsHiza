from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(
    0,
    str(SCRIPT_DIR),
)

from standalone_paths import (
    JIRA_NORMALISE,
    OCTANE_NORMALISE,
    PAYLOAD_STANDALONE,
    ensure_runtime_dirs,
)


def text(value) -> str:
    return str(value or "").strip()


def normalize_key_part(value) -> str:
    value = text(value)

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def join_key(
    capability,
    version_release,
    environment,
) -> tuple[str, str, str]:

    return (
        normalize_key_part(capability),
        normalize_key_part(version_release),
        normalize_key_part(environment),
    )


def index_octane(
    qualifications: list[dict],
) -> dict:

    index = {}

    for row in qualifications:

        key = join_key(
            row.get("capability"),
            row.get("release"),
            row.get("environnement"),
        )

        if not all(key):
            continue

        index.setdefault(
            key,
            [],
        ).append(row)

    return index


def build_row(
    jira: dict,
    octane_matches: list[dict],
) -> dict:

    jira_readiness = (
        jira.get("jiraReadiness")
        or {}
    )

    ambiguous = (
        len(octane_matches) > 1
    )

    octane = (
        octane_matches[0]
        if len(octane_matches) == 1
        else None
    )

    octane_found = (
        octane is not None
    )

    jira_capability = text(
        jira.get("capability")
    )

    jira_version = text(
        jira.get("version")
    )

    jira_environment = text(
        jira.get("environnement")
    ).upper()

    octane_capability = text(
        octane.get("capability")
        if octane
        else ""
    )

    octane_release = text(
        octane.get("release")
        if octane
        else ""
    )

    octane_environment = text(
        octane.get("environnement")
        if octane
        else ""
    ).upper()

    capability_match = (
        octane_found
        and normalize_key_part(
            jira_capability
        )
        == normalize_key_part(
            octane_capability
        )
    )

    version_release_match = (
        octane_found
        and normalize_key_part(
            jira_version
        )
        == normalize_key_part(
            octane_release
        )
    )

    environment_match = (
        octane_found
        and normalize_key_part(
            jira_environment
        )
        == normalize_key_part(
            octane_environment
        )
    )

    coherent = (
        octane_found
        and not ambiguous
        and capability_match
        and version_release_match
        and environment_match
    )

    octane_results = (
        octane.get("resultats") or {}
        if octane
        else {}
    )

    all_pass = bool(
        octane_results.get(
            "tousPass"
        )
    )

    jira_ready = bool(
        jira_readiness.get(
            "pret"
        )
    )

    reasons = []

    if not jira_capability:
        reasons.append(
            "Capability JIRA absente"
        )

    if not jira_version:
        reasons.append(
            "Version JIRA absente"
        )

    if not jira_environment:
        reasons.append(
            "Environnement JIRA absent"
        )

    if ambiguous:
        reasons.append(
            "Plusieurs qualifications Octane correspondent"
        )

    elif not octane_found:
        reasons.append(
            "Qualification Octane correspondante absente"
        )

    else:

        if not capability_match:
            reasons.append(
                "Capability JIRA / Octane incohérente"
            )

        if not version_release_match:
            reasons.append(
                "Version JIRA / Release Octane incohérente"
            )

        if not environment_match:
            reasons.append(
                "Environnement JIRA / Octane incohérent"
            )

    if not jira_ready:
        reasons.append(
            "JIRA non Ready for Test"
        )

    if octane_found and not all_pass:
        reasons.append(
            "Tests Octane non tous PASS"
        )

    # Les preuves restent informatives pour le moment.
    # Leur absence ne bloque pas encore Ready for Use.
    ready_for_use = (
        coherent
        and jira_ready
        and all_pass
    )

    return {
        "capability":
            jira_capability,

        "jiraKey": text(
            jira.get("jiraKey")
        ),

        "version":
            jira_version,

        "environnement":
            jira_environment,

        "joinKey": {
            "capability":
                normalize_key_part(
                    jira_capability
                ),
            "versionRelease":
                normalize_key_part(
                    jira_version
                ),
            "environnement":
                normalize_key_part(
                    jira_environment
                ),
        },

        "jira": {
            "capability":
                jira_capability,
            "titre": text(
                jira.get("titre")
            ),
            "version":
                jira_version,
            "environnement":
                jira_environment,
            "taches": (
                jira.get("taches")
                or []
            ),
            "readiness":
                jira_readiness,
        },

        "octane":
            octane,

        "matching": {
            "trouve":
                octane_found,

            "ambigu":
                ambiguous,

            "nombreCorrespondances":
                len(octane_matches),

            "capability": {
                "jira":
                    jira_capability,
                "octane":
                    octane_capability,
                "match":
                    capability_match,
            },

            "versionRelease": {
                "jira":
                    jira_version,
                "octane":
                    octane_release,
                "match":
                    version_release_match,
            },

            "environnement": {
                "jira":
                    jira_environment,
                "octane":
                    octane_environment,
                "match":
                    environment_match,
            },

            "coherent":
                coherent,
        },

        "readiness": {
            "jiraReadyForTest":
                jira_ready,
            "octaneAllPass":
                all_pass,
            "sourcesCoherentes":
                coherent,
        },

        "readyForUse":
            ready_for_use,

        "raisonsNonReady":
            (
                []
                if ready_for_use
                else reasons
            ),
    }


def build_payload(
    jira_data: dict,
    octane_data: dict,
) -> dict:

    jira_rows = (
        jira_data.get("capabilities")
        or []
    )

    octane_rows = (
        octane_data.get("qualifications")
        or []
    )

    octane_index = index_octane(
        octane_rows
    )

    rows = []

    for jira in jira_rows:

        key = join_key(
            jira.get("capability"),
            jira.get("version"),
            jira.get("environnement"),
        )

        matches = (
            octane_index.get(
                key,
                [],
            )
            if all(key)
            else []
        )

        rows.append(
            build_row(
                jira,
                matches,
            )
        )

    rows.sort(
        key=lambda row: (
            normalize_key_part(
                row.get("version")
            ),
            normalize_key_part(
                row.get("environnement")
            ),
            normalize_key_part(
                row.get("capability")
            ),
        )
    )

    ready = sum(
        1
        for row in rows
        if row["readyForUse"]
    )

    matched = sum(
        1
        for row in rows
        if row["matching"]["trouve"]
    )

    ambiguous = sum(
        1
        for row in rows
        if row["matching"]["ambigu"]
    )

    return {
        "schemaVersion": 1,
        "generatedAt": (
            jira_data.get("generatedAt")
            or octane_data.get(
                "generatedAt"
            )
        ),
        "source": {
            "jira": "JIRA",
            "octane": "OCTANE",
        },
        "joinRule": [
            "capability",
            "versionRelease",
            "environnement",
        ],
        "kpis": {
            "total": len(rows),
            "octaneTrouve": matched,
            "octaneAbsent": (
                len(rows)
                - matched
                - ambiguous
            ),
            "octaneAmbigu": ambiguous,
            "readyForUse": ready,
            "nonReadyForUse": (
                len(rows) - ready
            ),
        },
        "capabilities": rows,
    }


def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Source absente : {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )


def main() -> int:

    jira_data = load_json(
        JIRA_NORMALISE
    )

    octane_data = load_json(
        OCTANE_NORMALISE
    )

    payload = build_payload(
        jira_data,
        octane_data,
    )

    ensure_runtime_dirs()

    PAYLOAD_STANDALONE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "OK - payload Standalone construit"
    )

    print(
        "Capabilities :",
        payload["kpis"]["total"],
    )

    print(
        "Octane trouvées :",
        payload["kpis"]["octaneTrouve"],
    )

    print(
        "Ready for use :",
        payload["kpis"]["readyForUse"],
    )

    print(
        "Cible :",
        PAYLOAD_STANDALONE,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
