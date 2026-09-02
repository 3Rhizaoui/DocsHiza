from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

CONFIG_FILE = (
    SCRIPT_DIR
    / "standalone_config.json"
)

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


def load_standalone_config() -> dict:

    if not CONFIG_FILE.exists():
        return {
            "matching_enabled": True,
        }

    data = json.loads(
        CONFIG_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    return {
        "matching_enabled": bool(
            data.get(
                "matching_enabled",
                True,
            )
        ),
    }


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

    exact = {}
    without_environment = {}

    for row in qualifications:

        capability = normalize_key_part(
            row.get("capability")
        )

        release = normalize_key_part(
            row.get("release")
        )

        environment = normalize_key_part(
            row.get("environnement")
        )

        # Capability + Release restent obligatoires.
        # L'environnement peut être absent dans Octane :
        # dans ce cas la qualification reste visible,
        # mais elle ne sera jamais considérée cohérente.
        if not capability or not release:
            continue

        if environment:

            exact.setdefault(
                (
                    capability,
                    release,
                    environment,
                ),
                [],
            ).append(row)

        else:

            without_environment.setdefault(
                (
                    capability,
                    release,
                ),
                [],
            ).append(row)

    return {
        "exact": exact,
        "withoutEnvironment":
            without_environment,
    }


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


def build_octane_only_row(
    octane: dict,
) -> dict:

    capability = text(
        octane.get("capability")
    )

    release = text(
        octane.get("release")
    )

    environnement = text(
        octane.get("environnement")
    ).upper()

    results = (
        octane.get("resultats")
        or {}
    )

    all_pass = bool(
        results.get("tousPass")
    )

    return {
        "sourceType": "OCTANE",
        "diagnosticOnly": True,

        "capability": capability,
        "jiraKey": "",
        "version": "",
        "environnement": "",

        "joinKey": {
            "capability":
                normalize_key_part(
                    capability
                ),
            "versionRelease":
                normalize_key_part(
                    release
                ),
            "environnement":
                normalize_key_part(
                    environnement
                ),
        },

        "jira": {
            "capability": "",
            "titre": "",
            "version": "",
            "environnement": "",
            "taches": [],
            "readiness": {
                "pret": False,
            },
        },

        "octane": octane,

        "matching": {
            "enabled": False,
            "trouve": False,
            "ambigu": False,
            "nombreCorrespondances": 0,

            "capability": {
                "jira": "",
                "octane": capability,
                "match": False,
            },

            "versionRelease": {
                "jira": "",
                "octane": release,
                "match": False,
            },

            "environnement": {
                "jira": "",
                "octane":
                    environnement,
                "match": False,
            },

            "coherent": False,
        },

        "readiness": {
            "jiraReadyForTest": False,
            "octaneAllPass": all_pass,
            "sourcesCoherentes": False,
        },

        "readyForUse": False,

        "raisonsNonReady": [
            "Mode diagnostic - matching désactivé"
        ],
    }


def build_payload(
    jira_data: dict,
    octane_data: dict,
    matching_enabled: bool = True,
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

    if matching_enabled:

        for jira in jira_rows:

            key = join_key(
                jira.get("capability"),
                jira.get("version"),
                jira.get("environnement"),
            )

            matches = []

            if all(key):

                # 1. Priorité au rapprochement strict :
                # Capability + Release + Environnement.
                matches = (
                    octane_index
                    .get("exact", {})
                    .get(
                        key,
                        [],
                    )
                )

            # 2. Si aucun match exact, accepter une
            # qualification Octane dont l'environnement
            # est réellement absent.
            #
            # Aucun SIT/UAT n'est inventé.
            if (
                not matches
                and key[0]
                and key[1]
            ):

                matches = (
                    octane_index
                    .get(
                        "withoutEnvironment",
                        {},
                    )
                    .get(
                        (
                            key[0],
                            key[1],
                        ),
                        [],
                    )
                )

            row = build_row(
                jira,
                matches,
            )

            row["sourceType"] = (
                "MATCHED"
                if row["matching"]["trouve"]
                else "JIRA"
            )

            row["matching"][
                "enabled"
            ] = True

            rows.append(row)

    else:

        # ---------------------------------------------
        # MODE DIAGNOSTIC
        #
        # Les deux sources sont volontairement
        # affichées indépendamment.
        #
        # La logique de matching reste intacte et
        # pourra être réactivée par configuration.
        # ---------------------------------------------

        for jira in jira_rows:

            row = build_row(
                jira,
                [],
            )

            row["sourceType"] = "JIRA"
            row["diagnosticOnly"] = True

            row["matching"][
                "enabled"
            ] = False

            row["raisonsNonReady"] = [
                "Mode diagnostic - matching désactivé"
            ]

            rows.append(row)

        for octane in octane_rows:

            rows.append(
                build_octane_only_row(
                    octane
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

        "matchingEnabled":
            matching_enabled,

        "diagnosticMode":
            not matching_enabled,

        "sourceCounts": {
            "jira":
                len(jira_rows),
            "octane":
                len(octane_rows),
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

    config = (
        load_standalone_config()
    )

    matching_enabled = bool(
        config.get(
            "matching_enabled",
            True,
        )
    )

    print(
        "Matching :",
        (
            "ACTIVE"
            if matching_enabled
            else "DESACTIVE - MODE DIAGNOSTIC"
        ),
    )

    payload = build_payload(
        jira_data,
        octane_data,
        matching_enabled=
            matching_enabled,
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
