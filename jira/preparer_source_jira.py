from __future__ import annotations

import argparse
import json
import re
import unicodedata

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent


def text(value):
    if value is None:
        return ""

    if isinstance(value, dict):
        return str(
            value.get("value")
            or value.get("name")
            or value.get("displayName")
            or value.get("key")
            or ""
        )

    if isinstance(value, list):
        return " / ".join(
            filter(
                None,
                (text(item) for item in value)
            )
        )

    return str(value)


def folded(value):
    value = unicodedata.normalize(
        "NFKD",
        text(value)
    )

    value = value.encode(
        "ascii",
        "ignore"
    ).decode("ascii")

    return value.casefold()


def configured(fields, field_id):
    return (
        fields.get(field_id)
        if field_id
        else None
    )


def named_field(
    fields,
    names,
    configured_id,
    expected_name
):
    if configured_id:
        return fields.get(configured_id)

    wanted = folded(expected_name)

    for field_id, label in names.items():
        if wanted in folded(label):
            value = fields.get(field_id)

            if value not in (
                None,
                "",
                []
            ):
                return value

    return None


def find_named_field(
    fields,
    names,
    *expected_names
):
    """
    Recherche un champ Jira à partir
    de son libellé humain.
    """

    for expected_name in expected_names:
        wanted = folded(expected_name)

        for field_id, label in names.items():
            if wanted in folded(label):
                value = fields.get(field_id)

                if value not in (
                    None,
                    "",
                    []
                ):
                    return value

    return None


def sprint_name(value, fallback):
    raw = text(value)

    match = re.search(
        r"name=([^,\]]+)",
        raw
    )

    if match:
        return match.group(1).strip()

    match = re.search(
        r"Sprint\s*[-_ ]?\s*(\d+)",
        raw,
        re.I
    )

    if match:
        return f"Sprint {match.group(1)}"

    return raw.strip() or fallback


def environment(value, fallback):
    raw = folded(value)
    found = []

    if (
        "sit" in raw
        or "qua" in raw
    ):
        found.append("SIT")

    if "uat" in raw:
        found.append("UAT")

    return found or [fallback]


def classify(
    issue,
    rules,
    inherited=None
):
    fields = issue.get("fields") or {}
    cfg = rules["champs"]

    explicit_domain = text(
        configured(
            fields,
            cfg.get("domaine")
        )
    )

    explicit_subdomain = text(
        configured(
            fields,
            cfg.get("sous_domaine")
        )
    )

    domain = (
        explicit_domain
        or (inherited or {}).get(
            "domaine",
            ""
        )
    )

    subdomain = (
        explicit_subdomain
        or (inherited or {}).get(
            "sous_domaine",
            ""
        )
    )

    corpus = " ".join([
        text(fields.get("summary")),
        text(fields.get("description")),
        text(fields.get("labels")),
        text(fields.get("components")),
        text(fields.get("epic")),
        text(fields.get("parent")),
    ])

    for mapping in rules.get(
        "mappings",
        []
    ):
        if any(
            folded(token)
            in folded(corpus)
            for token
            in mapping.get(
                "contient",
                []
            )
        ):
            domain = (
                domain
                or mapping.get(
                    "domaine",
                    ""
                )
            )

            subdomain = (
                subdomain
                or mapping.get(
                    "sous_domaine",
                    ""
                )
            )

    defaults = rules[
        "valeurs_par_defaut"
    ]

    return {
        "domaine":
            domain
            or defaults["domaine"],

        "sous_domaine":
            subdomain
            or defaults[
                "sous_domaine"
            ]
    }


def parent_key(issue, epic_field):
    fields = issue.get("fields") or {}

    parent = (
        fields.get("parent")
        or {}
    )

    if (
        isinstance(parent, dict)
        and parent.get("key")
    ):
        return parent["key"]

    epic = (
        fields.get(epic_field)
        if epic_field
        else None
    )

    if isinstance(epic, dict):
        return epic.get(
            "key",
            ""
        )

    return text(epic)


def status_category(fields):
    status = fields.get("status")

    if isinstance(status, dict):
        return text(
            status.get(
                "statusCategory"
            )
        )

    return ""


def is_resolved(fields, rules):
    status = text(
        fields.get("status")
    )

    category = status_category(
        fields
    )

    resolution = text(
        fields.get("resolution")
    )

    corpus = folded(
        " ".join([
            status,
            category,
            resolution
        ])
    )

    return (
        any(
            folded(item) in corpus
            for item
            in rules.get(
                "statuts_resolus",
                []
            )
        )
        or folded(category) == "done"
    )


def anomaly_state(fields, rules):
    """
    Retourne :
      Corrigée
      En cours
      KO
    """

    if is_resolved(fields, rules):
        return "Corrigée"

    status = folded(
        text(fields.get("status"))
    )

    category = folded(
        status_category(fields)
    )

    if any(
        token in status
        for token in (
            "progress",
            "cours",
            "analyse",
            "investigation",
            "traitement",
            "develop",
            "correction"
        )
    ):
        return "En cours"

    if category in (
        "indeterminate",
        "in progress"
    ):
        return "En cours"

    return "KO"


def extract_reference(
    fields,
    names
):
    value = find_named_field(
        fields,
        names,
        "Reference",
        "Référence"
    )

    # Jira Group n'expose pas toujours le libellé du champ
    # "Reference" dans expand=names ou /rest/api/2/field.
    # Le champ utilisé par les anomalies Octane est
    # customfield_23820.
    if not text(value).strip():
        value = fields.get(
            "customfield_23820"
        )

    return text(value).strip()


def description(fields):
    return text(
        fields.get("description")
    ).strip()


def issue_url(origin, key):
    if origin:
        return f"{origin}/browse/{key}"

    return key


def compact_issue(
    issue,
    names,
    rules,
    origin
):
    fields = issue.get("fields") or {}
    key = issue.get("key") or ""

    return {
        "cle":
            key,

        "type":
            text(
                fields.get(
                    "issuetype"
                )
            ),

        "resume":
            text(
                fields.get(
                    "summary"
                )
            ),

        "description":
            description(fields),

        "statut":
            text(
                fields.get(
                    "status"
                )
            ),

        "terminee":
            is_resolved(
                fields,
                rules
            ),

        "responsable":
            text(
                fields.get(
                    "assignee"
                )
            )
            or "Non affecté",

        "reporter":
            text(
                fields.get(
                    "reporter"
                )
            ),

        "priorite":
            text(
                fields.get(
                    "priority"
                )
            ),

        "versions":
            text(
                fields.get(
                    "fixVersions"
                )
            ),

        "reference":
            extract_reference(
                fields,
                names
            ),

        "updated":
            text(
                fields.get(
                    "updated"
                )
            ),

        "url":
            issue_url(
                origin,
                key
            )
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Normalise l'export JIRA SSO "
            "pour le dashboard GIL."
        )
    )

    parser.add_argument(
        "--input",
        default=ROOT / "jira_brut.json",
        type=Path
    )

    parser.add_argument(
        "--rules",
        default=ROOT / "regles_domaines.json",
        type=Path
    )

    parser.add_argument(
        "--output",
        default=ROOT / "dashboard_gil_data.json",
        type=Path
    )

    args = parser.parse_args()

    raw = json.loads(
        args.input.read_text(
            encoding="utf-8-sig"
        )
    )

    rules = json.loads(
        args.rules.read_text(
            encoding="utf-8-sig"
        )
    )

    searches = (
        raw.get("recherches")
        or raw.get("searches")
        or []
    )

    names = dict(
        raw.get("names")
        or {}
    )

    for search in searches:
        names.update(
            search.get("names")
            or {}
        )

    cfg = rules["champs"]
    defaults = rules[
        "valeurs_par_defaut"
    ]

    epic_types = {
        folded(x)
        for x
        in rules["types"]["epic"]
    }

    bug_types = {
        folded(x)
        for x
        in rules["types"]["bug"]
    }

    source_urls = [
        x.get("url", "")
        for x in searches
        if x.get("url")
    ]

    origin = ""

    if source_urls:
        part = urlsplit(
            source_urls[0]
        )

        origin = (
            f"{part.scheme}://"
            f"{part.netloc}"
        )
    elif raw.get("jira_base_url"):
        origin = str(
            raw.get(
                "jira_base_url"
            )
        ).rstrip("/")

    iso = datetime.now().isocalendar()

    default_week = (
        f"{iso.year}-"
        f"W{iso.week:02d}"
    )

    #
    # 1. Identifier explicitement
    # les résultats des deux requêtes.
    #
    epic_search = next(
        (
            search
            for search in searches
            if folded(
                search.get("name")
            ) == "epics"
        ),
        None
    )

    anomaly_search = next(
        (
            search
            for search in searches
            if folded(
                search.get("name")
            ) == "anomalies_resolues"
        ),
        None
    )

    if anomaly_search is None:
        anomaly_search = next(
            (
                search
                for search in searches
                if "anomal" in folded(
                    search.get("name")
                )
                or "bug" in folded(
                    search.get("name")
                )
                or "octane" in folded(
                    search.get("name")
                )
            ),
            None
        )

    if anomaly_search is None:
        #
        # Fallback robuste :
        # chercher directement une requête contenant des Bugs/Bogues.
        #
        anomaly_search = next(
            (
                search
                for search in searches
                if any(
                    folded(
                        text(
                            (
                                issue.get("fields")
                                or {}
                            ).get("issuetype")
                        )
                    )
                    in bug_types
                    for issue
                    in search.get(
                        "issues",
                        []
                    )
                )
            ),
            None
        )

    print(
        "[JIRA][ANOMALIES] searches=",
        [
            (
                search.get("name"),
                len(search.get("issues", []))
            )
            for search in searches
        ]
    )

    print(
        "[JIRA][ANOMALIES] selection=",
        (anomaly_search or {}).get("name"),
        " issues=",
        len(
            (anomaly_search or {}).get(
                "issues",
                []
            )
        )
    )

    if epic_search is None:
        #
        # Fallback :
        # recherche d'une requête
        # contenant des Epics.
        #
        epic_search = next(
            (
                search
                for search in searches
                if any(
                    folded(
                        text(
                            (
                                issue.get(
                                    "fields"
                                )
                                or {}
                            ).get(
                                "issuetype"
                            )
                        )
                    )
                    in epic_types
                    for issue
                    in search.get(
                        "issues",
                        []
                    )
                )
            ),
            None
        )

    selected_epics = {}

    for issue in (
        (epic_search or {}).get(
            "issues",
            []
        )
    ):
        fields = (
            issue.get("fields")
            or {}
        )

        if (
            folded(
                text(
                    fields.get(
                        "issuetype"
                    )
                )
            )
            not in epic_types
        ):
            continue

        key = issue.get("key")

        if key:
            selected_epics[key] = issue

    #
    # 2. Récupérer les fiches
    # rattachées à chaque Epic.
    #
    children_by_epic = defaultdict(
        dict
    )

    for detail in raw.get(
        "epic_details",
        []
    ):
        epic_key = str(
            detail.get(
                "epic_key"
            )
            or ""
        )

        for issue in detail.get(
            "issues",
            []
        ):
            key = issue.get("key")

            if epic_key and key:
                children_by_epic[
                    epic_key
                ][key] = issue

    #
    # Compatibilité si les enfants
    # étaient déjà présents dans
    # les résultats principaux.
    #
    for search in searches:
        for issue in search.get(
            "issues",
            []
        ):
            key = issue.get("key")

            if not key:
                continue

            parent = parent_key(
                issue,
                cfg.get(
                    "epic_link"
                )
            )

            if parent in selected_epics:
                children_by_epic[
                    parent
                ][key] = issue

    #
    # 3. Classification des Epics.
    #
    classifications = {}

    for key, issue in (
        selected_epics.items()
    ):
        classifications[key] = classify(
            issue,
            rules
        )

    #
    # 4. Construire UN flux par Epic.
    #
    records = []
    epics = []
    taches = []
    anomalies = []

    for epic_key, epic in sorted(
        selected_epics.items()
    ):
        fields = (
            epic.get("fields")
            or {}
        )

        classification = (
            classifications[
                epic_key
            ]
        )

        children = list(
            children_by_epic[
                epic_key
            ].values()
        )

        epic_done = is_resolved(
            fields,
            rules
        )

        child_states = [
            is_resolved(
                child.get(
                    "fields"
                )
                or {},
                rules
            )
            for child in children
        ]

        #
        # Règle métier :
        #
        # - Epic terminé
        # - ET toutes les fiches
        #   rattachées terminées
        #
        # => flux prêt/livré.
        #
        # S'il n'y a aucune fiche,
        # on conserve le statut Epic
        # mais on le signale dans
        # le détail.
        #
        children_done = (
            all(child_states)
            if children
            else epic_done
        )

        ready = (
            epic_done
            and children_done
        )

        sprint = sprint_name(
            named_field(
                fields,
                names,
                cfg.get("sprint"),
                "Sprint"
            ),
            defaults["sprint"]
        )

        envs = environment(
            named_field(
                fields,
                names,
                cfg.get(
                    "environnement"
                ),
                "Environnement"
            ),
            defaults[
                "environnement"
            ]
        )

        versions = text(
            fields.get(
                "fixVersions"
            )
        )

        summary = text(
            fields.get(
                "summary"
            )
        )

        epic_description = (
            description(fields)
        )

        responsible = (
            text(
                fields.get(
                    "assignee"
                )
            )
            or text(
                fields.get(
                    "reporter"
                )
            )
            or "Non affecté"
        )

        reference = (
            extract_reference(
                fields,
                names
            )
            or epic_key
        )

        child_details = [
            compact_issue(
                child,
                names,
                rules,
                origin
            )
            for child in sorted(
                children,
                key=lambda x:
                    x.get(
                        "key",
                        ""
                    )
            )
        ]

        done_count = sum(
            1
            for child
            in child_details
            if child["terminee"]
        )

        total_count = len(
            child_details
        )

        epic_item = {
            "cle":
                epic_key,

            "reference_flux":
                reference,

            "resume":
                summary,

            "description":
                epic_description,

            "type":
                "Epic",

            "statut":
                text(
                    fields.get(
                        "status"
                    )
                ),

            "termine":
                epic_done,

            "pret":
                ready,

            "domaine":
                classification[
                    "domaine"
                ],

            "sous_domaine":
                classification[
                    "sous_domaine"
                ],

            "sprint":
                sprint,

            "responsable":
                responsible,

            "versions":
                versions,

            "url":
                issue_url(
                    origin,
                    epic_key
                ),

            "taches_total":
                total_count,

            "taches_terminees":
                done_count,

            "taches":
                child_details
        }

        epics.append(
            epic_item
        )

        for child_detail in (
            child_details
        ):
            taches.append({
                **child_detail,
                "epic_parent":
                    epic_key,

                "reference_flux":
                    reference,

                "domaine":
                    classification[
                        "domaine"
                    ],

                "sous_domaine":
                    classification[
                        "sous_domaine"
                    ],

                "sprint":
                    sprint
            })

        for env in envs:
            records.append({
                #
                # IMPORTANT :
                # l'id du flux est
                # la référence métier
                # lorsqu'elle existe.
                #
                "id":
                    reference,

                "reference":
                    reference,

                "jira_key":
                    epic_key,

                "type":
                    "AVRO",

                "domaine":
                    classification[
                        "domaine"
                    ],

                "sousDomaine":
                    classification[
                        "sous_domaine"
                    ],

                "environnement":
                    env,

                "semaine":
                    default_week,

                "sprint":
                    sprint,

                "etatFlux":
                    (
                        "Prêt"
                        if ready
                        else "En cours"
                    ),

                "etatAnomalie":
                    "",

                "statut":
                    (
                        "Livré"
                        if ready
                        else text(
                            fields.get(
                                "status"
                            )
                        )
                    ),

                "statut_jira":
                    text(
                        fields.get(
                            "status"
                        )
                    ),

                "version":
                    versions,

                "nombre":
                    1,

                "commentaire":
                    summary,

                "description":
                    epic_description,

                "source":
                    responsible,

                "date":
                    text(
                        fields.get(
                            "updated"
                        )
                    )
                    or datetime.now()
                    .date()
                    .isoformat(),

                "nature":
                    "Epic JIRA",

                "url_source":
                    issue_url(
                        origin,
                        epic_key
                    ),

                "responsable":
                    responsible,

                "epic_key":
                    epic_key,

                "epic_statut":
                    text(
                        fields.get(
                            "status"
                        )
                    ),

                "epic_termine":
                    epic_done,

                "taches_total":
                    total_count,

                "taches_terminees":
                    done_count,

                "taches":
                    child_details
            })

    #
    # 5. Anomalies :
    # uniquement celles sélectionnées
    # par la deuxième requête.
    #
    anomaly_issues = (
        (anomaly_search or {})
        .get(
            "issues",
            []
        )
    )

    print(
        "[JIRA][ANOMALIES] anomaly_issues=",
        len(anomaly_issues)
    )

    print(
        "[TRACE][PREPARER][BEFORE_LOOP]",
        "anomaly_issues=", len(anomaly_issues),
        "names=", len(names or {})
    )

    #
    # Jira n'expose pas toujours le libellé exact du champ
    # "Reference" dans expand=names ou /rest/api/2/field.
    #
    # La JQL utilisée ici impose Reference IS NOT EMPTY.
    # Si aucun champ nommé exactement "Reference" n'est connu,
    # on identifie dynamiquement le custom field numérique commun
    # à tous les résultats de cette requête.
    #
    anomaly_names = dict(names or {})

    has_named_reference = any(
        folded(text(label)) == "reference"
        for label in anomaly_names.values()
    )

    reference_field_id = None

    if not has_named_reference and anomaly_issues:
        candidate_counts = {}

        for anomaly_issue in anomaly_issues:
            anomaly_fields = (
                anomaly_issue.get("fields")
                or {}
            )

            issue_candidates = set()

            for field_id, field_value in anomaly_fields.items():
                if not str(field_id).startswith(
                    "customfield_"
                ):
                    continue

                raw = text(field_value).strip()

                if (
                    raw.isdigit()
                    and 4 <= len(raw) <= 12
                ):
                    issue_candidates.add(
                        field_id
                    )

            for field_id in issue_candidates:
                candidate_counts[field_id] = (
                    candidate_counts.get(
                        field_id,
                        0
                    ) + 1
                )

        common_candidates = [
            field_id
            for field_id, count
            in candidate_counts.items()
            if count == len(anomaly_issues)
        ]

        if len(common_candidates) == 1:
            reference_field_id = (
                common_candidates[0]
            )

            anomaly_names[
                reference_field_id
            ] = "Reference"

    print(
        "[JIRA][ANOMALIES] reference_field_id=",
        reference_field_id
        or "champ nommé Reference"
        if has_named_reference
        else "NON DETECTE"
    )

    for issue in sorted(
        anomaly_issues,
        key=lambda x:
            x.get(
                "key",
                ""
            )
    ):
        fields = (
            issue.get("fields")
            or {}
        )

        issue_type = text(
            fields.get(
                "issuetype"
            )
        )

        if (
            folded(issue_type)
            not in bug_types
        ):
            continue

        key = (
            issue.get("key")
            or ""
        )

        reference = (
            extract_reference(
                fields,
                anomaly_names
            )
        )

        #
        # La requête impose normalement
        # Reference IS NOT EMPTY.
        # Sécurité supplémentaire ici.
        #
        if not reference:
            print(
                "[TRACE][PREPARER][DROP_NO_REFERENCE]",
                key
            )
            continue

        parent = parent_key(
            issue,
            cfg.get(
                "epic_link"
            )
        )

        inherited = (
            classifications.get(
                parent
            )
        )

        classification = classify(
            issue,
            rules,
            inherited
        )

        sprint = sprint_name(
            named_field(
                fields,
                names,
                cfg.get("sprint"),
                "Sprint"
            ),
            defaults["sprint"]
        )

        envs = environment(
            named_field(
                fields,
                names,
                cfg.get(
                    "environnement"
                ),
                "Environnement"
            ),
            defaults[
                "environnement"
            ]
        )

        severity = text(
            named_field(
                fields,
                names,
                cfg.get(
                    "severite"
                ),
                "Sévérité"
            )
            or fields.get(
                "priority"
            )
        )

        responsible = (
            text(
                fields.get(
                    "assignee"
                )
            )
            or text(
                fields.get(
                    "reporter"
                )
            )
            or "Non affecté"
        )

        state = anomaly_state(
            fields,
            rules
        )

        summary = text(
            fields.get(
                "summary"
            )
        )

        anomaly_description = (
            description(fields)
        )

        item = {
            "cle":
                key,

            "reference":
                key,

            "flux":
                reference,

            "resume":
                summary,

            "description":
                anomaly_description,

            "type":
                issue_type,

            "statut":
                text(
                    fields.get(
                        "status"
                    )
                ),

            "etat":
                state,

            "domaine":
                classification[
                    "domaine"
                ],

            "sous_domaine":
                classification[
                    "sous_domaine"
                ],

            "epic_parent":
                parent,

            "sprint":
                sprint,

            "responsable":
                responsible,

            "severite":
                severity,

            "version":
                text(
                    fields.get(
                        "fixVersions"
                    )
                ),

            "url":
                issue_url(
                    origin,
                    key
                )
        }

        anomalies.append(
            item
        )

        for env in envs:
            records.append({
                #
                # Pour une anomalie :
                # id = flux métier
                # reference = numéro Jira
                #
                "id":
                    reference,

                "reference":
                    key,

                "jira_key":
                    key,

                "type":
                    "Anomalie",

                "domaine":
                    classification[
                        "domaine"
                    ],

                "sousDomaine":
                    classification[
                        "sous_domaine"
                    ],

                "environnement":
                    env,

                "semaine":
                    default_week,

                "sprint":
                    sprint,

                "etatFlux":
                    "",

                "etatAnomalie":
                    state,

                "statut":
                    text(
                        fields.get(
                            "status"
                        )
                    ),

                "statut_jira":
                    text(
                        fields.get(
                            "status"
                        )
                    ),

                "version":
                    text(
                        fields.get(
                            "fixVersions"
                        )
                    ),

                "nombre":
                    1,

                "commentaire":
                    summary,

                "description":
                    anomaly_description,

                "source":
                    "JIRA SSO",

                "date":
                    text(
                        fields.get(
                            "updated"
                        )
                    )
                    or datetime.now()
                    .date()
                    .isoformat(),

                "nature":
                    issue_type,

                "url_source":
                    issue_url(
                        origin,
                        key
                    ),

                "responsable":
                    responsible,

                "severite":
                    severity,

                "epic_parent":
                    parent
            })

    payload = {
        "schema_version":
            "2.0",

        "source_type":
            "jira",

        "generated_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "source": {
            "type":
                "JIRA SSO",

            "urls":
                source_urls
        },

        "records":
            records,

        "epics":
            epics,

        "taches":
            taches,

        "anomalies":
            anomalies,

        "indicateurs": {
            "epics":
                len(epics),

            "flux_prets":
                sum(
                    1
                    for epic
                    in epics
                    if epic["pret"]
                ),

            "flux_en_cours":
                sum(
                    1
                    for epic
                    in epics
                    if not epic["pret"]
                ),

            "taches":
                len(taches),

            "taches_terminees":
                sum(
                    1
                    for task
                    in taches
                    if task[
                        "terminee"
                    ]
                ),

            "bugs":
                len(anomalies),

            "anomalies_ouvertes":
                sum(
                    1
                    for anomaly
                    in anomalies
                    if anomaly[
                        "etat"
                    ] == "KO"
                ),

            "anomalies_en_cours":
                sum(
                    1
                    for anomaly
                    in anomalies
                    if anomaly[
                        "etat"
                    ] == "En cours"
                ),

            "anomalies_corrigees":
                sum(
                    1
                    for anomaly
                    in anomalies
                    if anomaly[
                        "etat"
                    ] == "Corrigée"
                ),

            "domaines":
                dict(
                    Counter(
                        epic["domaine"]
                        for epic
                        in epics
                    )
                )
        }
    }

    args.output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"Source JIRA prête : "
        f"{args.output.name}"
    )

    print(
        f"Epics/flux : {len(epics)}"
    )

    print(
        "Prêts : "
        f"{payload['indicateurs']['flux_prets']}"
    )

    print(
        "En cours : "
        f"{payload['indicateurs']['flux_en_cours']}"
    )

    print(
        f"Tâches : {len(taches)}"
    )

    print(
        f"Anomalies : {len(anomalies)}"
    )

    print(
        f"Lignes dashboard : {len(records)}"
    )


if __name__ == "__main__":
    main()