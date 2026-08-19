from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "dashboard_gil_data.json"
TEMPLATE_DATA = ROOT / "rapport_gil_v6_w28_data.json"
HTML = ROOT / "dashboard_gil.html"
GENERATOR_VERSION = "2026.08.11.2"

print(f"Generateur dashboard GIL - version {GENERATOR_VERSION}")


def load_payload_template():
    """Charge le modele JSON ou le restaure depuis les donnees integrees au HTML."""
    if TEMPLATE_DATA.exists():
        return json.loads(TEMPLATE_DATA.read_text(encoding="utf-8-sig"))

    if not HTML.exists():
        raise SystemExit(
            "Modele introuvable : copiez dashboard_gil.html dans le meme "
            "dossier que ce script."
        )

    html = HTML.read_text(encoding="utf-8")
    match = re.search(
        r"const fallbackData\s*=\s*([\s\S]*?);\s*let currentData\s*=\s*fallbackData\s*;",
        html,
    )
    if not match:
        raise SystemExit(
            "Le fichier rapport_gil_v6_w28_data.json est absent et le modele "
            "integre au HTML n'a pas pu etre lu. Recopiez le dossier de livraison complet."
        )

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Modele JSON integre au HTML invalide : {exc}") from exc

    TEMPLATE_DATA.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Modele JSON absent : restaure automatiquement depuis le HTML.")
    return payload


def total(rows, predicate=lambda r: True):
    return int(sum(float(r.get("nombre") or 0) for r in rows if predicate(r)))


def metrics(rows):
    flow_rows = [r for r in rows if r.get("type") != "Anomalie"]
    amount = total(flow_rows)
    ready = total(flow_rows, lambda r: r.get("etatFlux") == "Prêt")
    ko = total(rows, lambda r: r.get("etatAnomalie") == "KO")
    progress = total(flow_rows, lambda r: r.get("etatFlux") == "En cours")
    pending = max(0, amount - ready)
    rate = ready / amount if amount else 0
    level = "Vert" if rate >= .80 else ("Orange" if rate >= .60 else "Rouge")
    return dict(total=amount, ready=ready, ko=ko, progress=progress, pending=pending, rate=rate, level=level)


def report(identifier, title, rows):
    m = metrics(rows)
    return {"id": identifier, "titre": title, "total": m["total"], "pret": m["ready"],
            "bloque": m["pending"], "risques": f'{m["ko"]} KO et {m["progress"]} en cours',
            "niveau": m["level"], "interpretation": f'{m["ready"]} prêts sur {m["total"]} ({m["rate"]:.0%}).',
            "action": "Traiter les KO et les flux en cours." if m["pending"] else "Maintenir le suivi."}


def build_compatible_records(data):
    """Construit l'ancien format `records` depuis le JSON Confluence normalise."""
    flux = data.get("flux") or []
    anomalies = data.get("anomalies") or []
    if not flux:
        raise SystemExit(
            "Le JSON ne contient ni `records` ni liste `flux`. Relancez "
            "l'import Excel, Confluence ou JIRA avec le dossier de livraison complet."
        )

    generated_at = str(data.get("generated_at") or datetime.now().astimezone().isoformat())
    try:
        generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        generated_dt = datetime.now().astimezone()
    iso_year, iso_week, _ = generated_dt.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    sprint_no = 21 + ((iso_year - 2026) * 26) + ((iso_week - 31) // 2)
    sprint_label = f"Sprint {max(1, sprint_no)}"

    anomaly_index = {}
    for anomaly in anomalies:
        key = (str(anomaly.get("flux") or ""), str(anomaly.get("environnement") or ""))
        anomaly_index.setdefault(key, []).append(anomaly)

    result = []
    for item in flux:
        reference = str(item.get("reference_flux") or item.get("reference") or "")
        env = str(item.get("environnement") or "")
        related = anomaly_index.get((reference, env), [])
        has_open_blocker = any(
            bool(a.get("bloquante")) and str(a.get("statut") or "").casefold() not in {"resolue", "résolue"}
            for a in related
        )
        versions = item.get("versions") or []
        if isinstance(versions, str):
            versions = [versions]
        source = item.get("source") or {}
        result.append({
            "id": reference, "reference": reference,
            "type": "AVRO" if str(item.get("type_flux")) == "Event" else "Configuration",
            "domaine": item.get("domaine") or "Non renseigné",
            "sousDomaine": item.get("sous_domaine") or "Non renseigné",
            "environnement": env, "semaine": week_label, "sprint": sprint_label,
            "etatFlux": "Prêt" if item.get("pret_arrimage") else "En cours",
            "etatAnomalie": "KO" if has_open_blocker else "",
            "statut": "Livré" if item.get("configuration_deployee") else str(item.get("statut_configuration") or ""),
            "version": " / ".join(str(v) for v in versions), "nombre": 1,
            "commentaire": str(item.get("description") or ""),
            "source": str(item.get("partenaire") or ""),
            "date": generated_dt.date().isoformat(), "nature": "Confluence",
            "url_source": source.get("url", "") if isinstance(source, dict) else "",
        })

    for anomaly in anomalies:
        status = str(anomaly.get("statut") or "")
        resolved = status.casefold() in {"resolue", "résolue"}
        result.append({
            "id": anomaly.get("flux") or anomaly.get("reference") or "",
            "reference": anomaly.get("reference") or "",
            "type": "Anomalie", "domaine": anomaly.get("domaine") or "Non renseigné",
            "sousDomaine": anomaly.get("sous_domaine") or "Non renseigné",
            "environnement": anomaly.get("environnement") or "",
            "semaine": week_label, "sprint": sprint_label, "etatFlux": "",
            "etatAnomalie": "Corrigée" if resolved else "KO", "statut": status,
            "version": "", "nombre": 1,
            "commentaire": f"{anomaly.get('responsable') or ''} - {anomaly.get('severite') or ''}",
            "source": anomaly.get("responsable") or "", "date": generated_dt.date().isoformat(),
            "severite": anomaly.get("severite") or "", "responsable": anomaly.get("responsable") or "",
            "nature": "Confluence",
        })
    print(f"Compatibilite JSON : {len(result)} lignes `records` construites automatiquement.")
    return result


if not SOURCE.exists():
    raise SystemExit(
        "Source dashboard_gil_data.json introuvable. Lancez d'abord un import Excel, Confluence ou JIRA."
    )

data = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
payload = load_payload_template()
records = data.get("records") or build_compatible_records(data)
# La feuille Reporting est la seule source de calcul. Les anciens exemples et
# toute ligne dont l'environnement n'est pas SIT/UAT sont exclus.
records = [r for r in records if r.get("environnement") in {"SIT", "UAT"}]
weeks = sorted({r["semaine"] for r in records})
if not weeks:
    raise SystemExit("Aucune semaine disponible. Lancez d'abord generer_dashboard_gil.py et vérifiez Reporting / Reporting N-1.")
current_week = weeks[-1]
previous_week = weeks[-2] if len(weeks) > 1 else current_week
current = [r for r in records if r["semaine"] == current_week]
current_m = metrics(current)
current_sprint = current[0].get("sprint", "Sprint non défini") if current else "Sprint non défini"

def sprint_number(label):
    match = re.search(r"(\d+)", str(label or ""))
    return int(match.group(1)) if match else 1

current_sprint_number = sprint_number(current_sprint)
previous_sprint = f"Sprint {max(1, current_sprint_number - 1)}"
current_sprint_weeks = sorted({r["semaine"] for r in records if r.get("sprint") == current_sprint}) or [current_week]
previous_sprint_weeks = sorted({r["semaine"] for r in records if r.get("sprint") == previous_sprint}) or [previous_week]

def bug_owner(row):
    text = " ".join(str(row.get(k) or "") for k in ("commentaire", "reference", "source")).upper()
    for owner in ("ESTREEM", "BCEF", "BCFM", "GIL", "ASSETS", "SAA"):
        if owner in text:
            return owner
    return "ESTREEM" if str(row.get("domaine")) == "Issuing" else "BCEF"

# Le Sprint 21 contient exactement deux semaines. Aucun ancien exemple n'est
# conservé dans les calculs.
history_by_week = {}
for week in weeks:
    rows = [r for r in records if r["semaine"] == week]
    m = metrics(rows)
    history_by_week[week] = {
        "semaine": week, "dateRapport": max((r.get("date", "") for r in rows), default=""),
        "flux": m["total"], "pretTester": m["ready"], "nonPret": m["pending"],
        "bugsBloquants": m["ko"],
        "servicesRisque": len({(r["domaine"], r["sousDomaine"]) for r in rows if r.get("etatAnomalie") == "KO" or r.get("etatFlux") == "En cours"}),
        "testsKoBloques": m["ko"], "prioritesTraitees": m["ready"], "sante": m["level"],
        "faitMarquant": f'{rows[0].get("nature", "Données")} — recalcul automatique' if rows else "",
        "risque": f'{m["pending"]} éléments non prêts ({m["ko"]} KO, {m["progress"]} en cours)'
    }
history = [history_by_week[w] for w in sorted(history_by_week)]
hist_current = history_by_week[current_week]
hist_previous = history_by_week[previous_week]

payload.update({
    "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    "source": f"{str(data.get('source_type') or 'multisources').upper()} — source JSON normalisée — flux, tâches et anomalies",
    "semaineCourante": current_week, "semainePrecedente": previous_week,
    "sprintCourant": current_sprint, "semainesSprint": current_sprint_weeks,
    "kpis": {"flux": current_m["total"], "pretTester": current_m["ready"], "nonPret": current_m["pending"],
             "bugsBloquants": current_m["ko"], "servicesRougeOrange": hist_current["servicesRisque"],
             "testsKoBloques": current_m["ko"]},
    "tendanceHebdo": {"rows": history, "current": hist_current, "previous": hist_previous,
                       "deltaPret": current_m["ready"] - hist_previous["pretTester"],
                       "deltaBugs": current_m["ko"] - hist_previous["bugsBloquants"],
                       "deltaTestsKo": current_m["ko"] - hist_previous["testsKoBloques"]}
})
def anomaly_item(row):
    return {
        "reference": row.get("reference") or "",
        "flux": row.get("id") or "",
        "domaine": row.get("domaine") or "À qualifier",
        "sousDomaine": row.get("sousDomaine") or "À qualifier",
        "environnement": row.get("environnement") or "",
        "statut": row.get("etatAnomalie") or "",
        "statutJira": row.get("statut_jira") or row.get("statut") or "",
        "partenaire": row.get("responsable") or bug_owner(row),
        "nombre": int(float(row.get("nombre") or 0)),
        "severite": row.get("severite") or "",
        "resume": row.get("commentaire") or "",
        "description": row.get("description") or "",
        "url": row.get("url_source") or "",
        "epicParent": row.get("epic_parent") or "",
    }

def delivered_item(row):
    return {
        "reference": row.get("reference") or row.get("id") or "",
        "flux": row.get("id") or "",
        "jiraKey": row.get("jira_key") or row.get("epic_key") or "",
        "domaine": row.get("domaine") or "À qualifier",
        "sousDomaine": row.get("sousDomaine") or "À qualifier",
        "environnement": row.get("environnement") or "",
        "statut": "Livré",
        "statutJira": row.get("statut_jira") or row.get("statut") or "",
        "partenaire": row.get("responsable") or bug_owner(row),
        "nombre": int(float(row.get("nombre") or 0)),
        "version": row.get("version") or "",
        "resume": row.get("commentaire") or "",
        "description": row.get("description") or "",
        "url": row.get("url_source") or "",
        "tachesTotal": int(row.get("taches_total") or 0),
        "tachesTerminees": int(row.get("taches_terminees") or 0),
        "taches": row.get("taches") or [],
    }

def is_explicit_corrected_anomaly(row):
    if row.get("etatAnomalie") == "Corrigée":
        return True

    status = unicodedata.normalize(
        "NFKD",
        str(
            row.get("statut")
            or ""
        ).lower()
    )

    status = "".join(
        char
        for char in status
        if not unicodedata.combining(char)
    )

    return any(
        word in status
        for word in (
            "corrig",
            "resolu",
            "clos",
            "valide",
            "done"
        )
    )

def is_explicit_anomaly(row):
    if row.get("type") == "Anomalie":
        return True

    if row.get("etatAnomalie") in {
        "KO",
        "En cours",
        "Corrigée"
    }:
        return True

    if is_explicit_corrected_anomaly(row):
        return True

    text_value = " ".join(
        str(row.get(k) or "")
        for k in (
            "reference",
            "commentaire",
            "source",
            "statut"
        )
    ).lower()

    return any(
        word in text_value
        for word in (
            "anomal",
            "bug",
            "incident",
            "octane",
            "jira"
        )
    )

def sprint_comparison_row(
    history_row,
    sprint,
    data_type,
    week,
    display_weeks=None
):
    if display_weeks is None:
        display_weeks = (
            current_sprint_weeks
            if sprint == current_sprint
            else previous_sprint_weeks
        )

    sprint_rows = [
        r
        for r in records
        if r["semaine"] == week
    ]

    # ---------------------------------------------------------
    # COMPARAISON DES FLUX / DEMANDES
    #
    # Les anomalies ne sont plus mélangées à ce graphique.
    # Elles restent traitées dans l'histogramme des anomalies.
    # ---------------------------------------------------------

    flow_rows = [
        r
        for r in sprint_rows
        if r.get("type") != "Anomalie"
    ]

    def flow_item(row, label):
        return {
            "reference":
                row.get("reference")
                or row.get("id")
                or "",

            "flux":
                row.get("id")
                or "",

            "jiraKey":
                row.get("jira_key")
                or row.get("epic_key")
                or "",

            "domaine":
                row.get("domaine")
                or "À qualifier",

            "sousDomaine":
                row.get("sousDomaine")
                or "À qualifier",

            "environnement":
                row.get("environnement")
                or "",

            "statut":
                label,

            "statutSource":
                row.get("statut")
                or "",

            "partenaire":
                row.get("responsable")
                or row.get("source")
                or bug_owner(row),

            "nombre":
                int(
                    float(
                        row.get("nombre")
                        or 0
                    )
                ),

            "version":
                row.get("version")
                or "",

            "resume":
                row.get("commentaire")
                or "",

            "description":
                row.get("description")
                or "",

            "url":
                row.get("url_source")
                or "",
        }

    def normalized_status(row):
        raw = " ".join(
            str(
                row.get(key)
                or ""
            )
            for key in (
                "etatFlux",
                "etatAnomalie",
                "statut"
            )
        )

        value = unicodedata.normalize(
            "NFKD",
            raw.casefold()
        )

        return "".join(
            char
            for char in value
            if not unicodedata.combining(char)
        )

    def is_blocked(row):
        status = normalized_status(row)

        blocked_words = (
            "bloqu",
            "rejet",
            "refus",
            "ko",
            "a traiter",
            "non pret",
            "abandon",
            "annul"
        )

        return (
            row.get("etatAnomalie") == "KO"
            or any(
                word in status
                for word in blocked_words
            )
        )

    def is_progress(row):
        # Un flux bloqué/rejeté ne doit pas être
        # compté une deuxième fois comme En cours.
        if is_blocked(row):
            return False

        status = normalized_status(row)

        return (
            row.get("etatFlux") == "En cours"
            or "en cours" in status
            or "progress" in status
        )

    def is_delivered(row):
        # Catégories exclusives :
        # Bloqué > En cours > Livré
        if is_blocked(row):
            return False

        if is_progress(row):
            return False

        status = normalized_status(row)

        return (
            row.get("etatFlux") == "Prêt"
            or "livr" in status
            or "pret" in status
            or "done" in status
        )

    # ---------------------------------------------------------
    # 1 - TOTAL DES FLUX / DEMANDES
    # ---------------------------------------------------------

    total_flows = [
        flow_item(
            row,
            "Total"
        )
        for row in flow_rows
    ]

    # ---------------------------------------------------------
    # 2 - FLUX LIVRÉS
    # ---------------------------------------------------------

    delivered = [
        flow_item(
            row,
            "Livré"
        )
        for row in flow_rows
        if is_delivered(row)
    ]

    # ---------------------------------------------------------
    # 3 - FLUX EN COURS
    # ---------------------------------------------------------

    progress = [
        flow_item(
            row,
            "En cours"
        )
        for row in flow_rows
        if is_progress(row)
    ]

    # ---------------------------------------------------------
    # 4 - FLUX BLOQUÉS / REJETÉS
    # ---------------------------------------------------------

    blocked = [
        flow_item(
            row,
            "Bloqué / Rejeté"
        )
        for row in flow_rows
        if is_blocked(row)
    ]

    return {
        **history_row,

        "sprint":
            sprint,

        "typeDonnee":
            data_type,

        "semaines":
            display_weeks,

        # Détails utilisés par le graphe
        # et le tableau comparatif.
        "fluxTotalDetail":
            total_flows,

        "fluxLivresDetail":
            delivered,

        "fluxEnCoursDetail":
            progress,

        "fluxBloquesDetail":
            blocked,

        # Totaux.
        "fluxTotal":
            sum(
                x["nombre"]
                for x in total_flows
            ),

        "fluxLivresTotal":
            sum(
                x["nombre"]
                for x in delivered
            ),

        "fluxEnCoursTotal":
            sum(
                x["nombre"]
                for x in progress
            ),

        "fluxBloquesTotal":
            sum(
                x["nombre"]
                for x in blocked
            ),
    }

payload["comparaisonSprints"] = [
    sprint_comparison_row(hist_previous, previous_sprint, "Simulation N-1", previous_week),
    sprint_comparison_row(hist_current, current_sprint, "Réel", current_week),
]

# Phase 2 du Reporting : flux effectivement traités et prêts pour les ateliers
# d'arrimage. Cette liste est indépendante des totaux AVRO/Configuration et
# conserve systématiquement le domaine et le sous-domaine du flux.
payload["fluxPretsArrimage"] = []
seen_arrimage = set()

for row in current:
    # Les anomalies ne sont jamais des flux prêts pour arrimage.
    if row.get("type") == "Anomalie":
        continue

    if row.get("environnement") not in {"SIT", "UAT"}:
        continue

    # La décision est maintenant calculée en amont à partir :
    # Epic terminé + toutes les fiches rattachées terminées.
    if row.get("etatFlux") != "Prêt":
        continue

    flux = row.get("id") or row.get("reference") or ""
    environment = row.get("environnement") or ""

    key = (
        flux,
        environment
    )

    if key in seen_arrimage:
        continue

    seen_arrimage.add(key)

    payload["fluxPretsArrimage"].append({
        "sprint":
            row.get("sprint") or current_sprint,

        "semaine":
            row.get("semaine") or current_week,

        "environnement":
            environment,

        "domaine":
            row.get("domaine") or "À qualifier",

        "sousDomaine":
            row.get("sousDomaine") or "À qualifier",

        "flux":
            flux,

        "jiraKey":
            row.get("jira_key")
            or row.get("epic_key")
            or "",

        "pattern":
            row.get("nature")
            or "Epic JIRA",

        "version":
            row.get("version") or "",

        "statut":
            "Prêt pour arrimage",

        "statutJira":
            row.get("statut_jira")
            or row.get("statut")
            or "",

        "resume":
            row.get("commentaire")
            or "",

        "description":
            row.get("description")
            or "",

        "url":
            row.get("url_source")
            or "",

        "responsable":
            row.get("responsable")
            or row.get("source")
            or "",

        "tachesTotal":
            int(
                row.get(
                    "taches_total"
                )
                or 0
            ),

        "tachesTerminees":
            int(
                row.get(
                    "taches_terminees"
                )
                or 0
            ),

        "taches":
            row.get("taches")
            or [],

        "source":
            "JIRA — Epic + fiches rattachées",
    })

payload["fluxPretsArrimage"].sort(
    key=lambda x: (
        x["domaine"],
        x["sousDomaine"],
        x["flux"],
        x["environnement"]
    )
)
payload["histogrammes"] = {
    "statuts": {"prets": current_m["ready"], "anomaliesOuvertes": current_m["pending"],
                "ok": current_m["ready"], "ko": current_m["ko"]},
    "severites": {
        "Critique": total(current, lambda r: r.get("etatAnomalie") == "KO" and "rollback" in str(r.get("commentaire", "")).lower()),
        "Majeure": total(current, lambda r: r.get("etatAnomalie") == "KO" and "rollback" not in str(r.get("commentaire", "")).lower()),
        "Mineure": total(current, lambda r: r.get("etatFlux") == "En cours")
    }
}

payload["rapports"] = [
    report("AVRO", "Chaîne de valeur AVRO", [r for r in current if r["type"] == "AVRO"]),
    report("CONFIG", "Chaîne de valeur Configuration", [r for r in current if r["type"] == "Configuration"]),
]
payload["domaines"] = []
for domain in sorted({r["domaine"] for r in current}):
    m = metrics([r for r in current if r["domaine"] == domain])
    payload["domaines"].append({"domaine": domain, "flux": m["total"], "pret": m["ready"],
                                "nonPret": m["pending"], "bugsBloquants": m["ko"]})

# Ventilation demandée dans le dashboard : deux environnements visibles pour
# chaque semaine, puis domaine et sous-domaine avec leurs anomalies.
payload["ventilation"] = []
for week in weeks:
    for environment in ("SIT", "UAT"):
        env_rows = [r for r in records if r["semaine"] == week and r["environnement"] == environment]
        for domain in sorted({r["domaine"] for r in env_rows}):
            for subdomain in sorted({r["sousDomaine"] for r in env_rows if r["domaine"] == domain}):
                rows = [r for r in env_rows if r["domaine"] == domain and r["sousDomaine"] == subdomain]
                m = metrics(rows)
                references = []
                delivered_references = []
                blocked_references = []
                for row in rows:
                    try:
                        quantity = max(0, int(float(row.get("nombre") or 0)))
                    except (TypeError, ValueError):
                        quantity = 0
                    label = f'{row["id"]} ({row["type"]})'
                    references.extend([label] * quantity)
                    if row.get("etatFlux") == "Prêt":
                        delivered_references.extend([label] * quantity)
                    if row.get("etatAnomalie") == "KO":
                        blocked_references.extend([label] * quantity)
                payload["ventilation"].append({
                    "semaine": week, "environnement": environment, "domaine": domain,
                    "sousDomaine": subdomain, "total": m["total"], "prets": m["ready"],
                    "anomaliesOuvertes": m["pending"], "ko": m["ko"], "enCours": m["progress"],
                    "referencesFlux": references, "referencesLivrees": delivered_references,
                    "referencesBloquees": blocked_references
                })

payload["flux"] = []
payload["histoFlux"] = []
payload["avro"] = []
payload["config"] = []
payload["ateliers"] = []
for r in current:
    decision = "KO" if r["etatAnomalie"] == "KO" else ("EN COURS" if r["etatFlux"] == "En cours" else "PRÊT")
    item = {"id": r["id"], "domain": r["domaine"], "subdomain": r["sousDomaine"],
            "environment": r["environnement"], "type": r["type"], "version": r["version"],
            "status": r["statut"], "decision": decision}
    payload["flux"].append(item)
    payload["histoFlux"].append({"semaine": current_week, "flux": r["id"], "domaine": r["domaine"],
        "sousDomaine": r["sousDomaine"], "environnement": r["environnement"],
        "type": r["type"], "statut": decision, "versionLivree": r["version"],
        "bugsBloquants": int(r["nombre"]) if decision == "KO" else 0,
        "testsOk": int(r["nombre"]) if decision == "PRÊT" else 0, "evenement": r["statut"],
        "action": r["commentaire"], "responsable": r["source"]})
    detail = {"demande": r["id"], "flux": r["id"], "typeDemande": r["sousDomaine"],
        "environnement": r["environnement"],
        "typeFlux": r["type"], "statut": decision, "versionAttendue": r["version"],
        "versionLivree": r["version"], "pret": "Oui" if decision == "PRÊT" else "Non",
        "bug": r["commentaire"] if decision == "KO" else "", "commentaire": r["commentaire"], "echeance": r["date"]}
    payload["avro" if r["type"] == "AVRO" else "config"].append(detail)

bad = [r for r in current if r["etatAnomalie"] == "KO" or r["etatFlux"] == "En cours"]
def anomaly_status(r):
    if r["etatAnomalie"] == "KO":
        return "Ouverte"
    if r["etatFlux"] == "En cours":
        return "En cours"
    return "Corrigée"

def anomaly_severity(r):
    # La valeur explicite du fichier reste prioritaire lorsqu'elle existe.
    raw = next((r.get(k) for k in ("severite", "sévérité", "criticite", "criticité", "priorite", "priorité") if r.get(k)), "")
    if raw:
        return str(raw)
    if r["etatAnomalie"] == "KO":
        return "Critique" if "rollback" in str(r.get("commentaire", "")).lower() else "Majeure"
    if r["etatFlux"] == "En cours":
        return "Mineure"
    return "Non renseignée"

anomaly_records = [r for r in records if is_explicit_anomaly(r)]
payload["anomaliesDetail"] = [{
    # Numéro de l'anomalie Jira.
    "reference":
        r.get("reference")
        or r.get("jira_key")
        or "",

    # Référence métier du flux provenant du champ Reference Jira.
    "flux":
        r.get("id")
        or "",

    "jiraKey":
        r.get("jira_key")
        or r.get("reference")
        or "",

    "domaine":
        r.get("domaine")
        or "À qualifier",

    "sousDomaine":
        r.get("sousDomaine")
        or "À qualifier",

    "environnement":
        r.get("environnement")
        or "",

    "statut":
        (
            "Corrigée"
            if r.get("etatAnomalie") == "Corrigée"
            else (
                "En cours"
                if r.get("etatAnomalie") == "En cours"
                else "Ouverte"
            )
        ),

    "statutJira":
        r.get("statut_jira")
        or r.get("statut")
        or "",

    "affectation":
        r.get("responsable")
        or bug_owner(r),

    "version":
        r.get("version")
        or "",

    "resume":
        r.get("commentaire")
        or "",

    "commentaire":
        r.get("commentaire")
        or "",

    "description":
        r.get("description")
        or "",

    "severite":
        anomaly_severity(r),

    "url":
        r.get("url_source")
        or "",

    "epicParent":
        r.get("epic_parent")
        or "",

    "semaine":
        r.get("semaine")
        or "",

    "sprint":
        r.get("sprint")
        or (
            current_sprint
            if r.get("semaine") == current_week
            else previous_sprint
        ),
} for r in anomaly_records]
payload["prioritesHebdo"] = [{
    "semaineDecision": previous_week, "semaineSuivi": current_week,
    "priorite": "P0" if r["etatAnomalie"] == "KO" else "P1",
    "sujet": f'{"Traiter anomalie" if r["etatAnomalie"] == "KO" else "Finaliser flux"} {r["id"]} ({r["environnement"]})',
    "origine": r["source"], "statut": r["etatAnomalie"] if r["etatAnomalie"] == "KO" else r["etatFlux"],
    "objets": f'{r["id"]} / {r["version"]} / {r["environnement"]}',
    "responsable": f'{r["domaine"]} / {r["sousDomaine"]}', "echeance": r["date"],
    "decisionAction": r["commentaire"] or "Qualifier, prioriser et planifier le traitement",
    "niveau": "Rouge" if r["etatAnomalie"] == "KO" else "Orange"
} for r in bad]

TEMPLATE_DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
html = HTML.read_text(encoding="utf-8")
replacement = "const fallbackData = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n    let currentData = fallbackData;"
html, count = re.subn(r"const fallbackData = [\s\S]*?;\s*let currentData = fallbackData;", replacement, html, count=1)
if count != 1:
    raise SystemExit("Impossible d'injecter les données dans le dashboard classique.")
HTML.write_text(html, encoding="utf-8")
print(f"Dashboard classique actualisé : {current_week}, {current_m['ready']}/{current_m['total']} prêts.")
