import json
import re
import unicodedata
from pathlib import Path
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "jira" / "presentation" / "payload_dashboard_final.json"

GENERIC = {
    "",
    "none",
    "null",
    "non renseigné",
    "non renseigne",
    "non renseignée",
    "non renseignee",
    "non ventilé",
    "non ventile",
    "à qualifier",
    "a qualifier",
}

def plain(v):
    s = "" if v is None else str(v)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.upper()

def clean(v):
    return "" if v is None else str(v).strip()

def is_generic(v):
    return clean(v).lower() in GENERIC

def first(*values):
    for v in values:
        if not is_generic(v):
            return clean(v)
    return ""

def joined_text(x):
    parts = []
    for k in [
        "reference", "référence", "flux", "jiraKey", "key", "cle",
        "summary", "sommaire", "titre", "resume", "description",
        "domaine", "sousDomaine", "statut", "statutSource"
    ]:
        if isinstance(x, dict) and x.get(k):
            parts.append(str(x.get(k)))
    return " ".join(parts)

def infer_domain(text):
    t = plain(text)

    if any(k in t for k in [
        "ACQ", "ACQUISITION", "ACQUIRING", "CREDITCOM", "CREDIT COM",
        "PC06", "PC07", "PRECOMP", "PRE-COMP", "MM7"
    ]):
        return "Acquisition"

    if any(k in t for k in [
        "ISS", "ISSUING", "CMS", "OA3", "OA5", "DMS", "GED",
        "DISPUTE", "CNT", "F2F", "CFT"
    ]):
        return "Issuing"

    return "À qualifier"

def infer_subdomain(text):
    t = plain(text)

    if any(k in t for k in ["DISPUTE", "CONTESTATION", "CNT", "CNTEM"]):
        return "Contestation"

    if any(k in t for k in ["DMS", "GED", "COS", "PRESIGNED", "DOCUMENT"]):
        return "GED"

    if any(k in t for k in ["ONBOARDING", "CMS4", "CMS14", "CMS22", "MM7"]):
        return "Onboarding"

    if any(k in t for k in ["AUTHORIZE", "AUTORISATION", "AUTHORIZATION", "OA3", "OA5"]):
        return "Authorize"

    if any(k in t for k in ["CREDITCOM", "CREDIT COM", "PC06", "PC07", "PRECOMP", "PRE-COMP"]):
        return "Crédit commerçant"

    return "À qualifier"

def infer_env(text):
    t = plain(text)
    if "UAT" in t or "QUAL" in t or " QUA" in t:
        return "UAT"
    if "SIT" in t:
        return "SIT"
    if "DEV" in t:
        return "DEV"
    return "SIT"

def normalize_item(x, sprint="", forced_status=None, forced_type=None):
    y = deepcopy(x) if isinstance(x, dict) else {}
    text = joined_text(y)

    # La référence Jira et le flux métier sont deux informations
    # différentes. Une référence métier (OA5-2, CMS14_003, etc.)
    # ne doit jamais devenir la clé Jira.
    key = first(
        y.get("jiraKey"),
        y.get("jira_key"),
        y.get("epicKey"),
        y.get("epic_key"),
        y.get("key"),
        y.get("cle"),
    )

    business_flux = first(
        y.get("flux"),
        y.get("referenceFlux"),
        y.get("reference_flux"),
        y.get("id"),
        y.get("reference"),
    )

    # Si l'ancien payload a mis la clé Jira dans "flux",
    # on récupère la référence métier lorsqu'elle est différente.
    if (
        business_flux
        and str(business_flux).upper().startswith("AERL_GIL-")
    ):
        candidate = first(
            y.get("referenceFlux"),
            y.get("reference_flux"),
            y.get("id"),
            y.get("reference"),
        )

        if (
            candidate
            and not str(candidate).upper().startswith("AERL_GIL-")
        ):
            business_flux = candidate

    title = first(
        y.get("summary"),
        y.get("sommaire"),
        y.get("titre"),
        y.get("resume"),
    )

    if key:
        y["jiraKey"] = key
        y["key"] = key
        y["cle"] = key
        y["referenceJira"] = key

    if business_flux:
        y["flux"] = business_flux

    if title:
        y["summary"] = title
        y["sommaire"] = title
        y["titre"] = title
        y["resume"] = title

    if is_generic(y.get("domaine")):
        y["domaine"] = infer_domain(text)

    if is_generic(y.get("sousDomaine")):
        y["sousDomaine"] = infer_subdomain(text)

    if is_generic(y.get("environnement")):
        y["environnement"] = infer_env(text)

    if sprint and is_generic(y.get("sprint")):
        y["sprint"] = sprint

    if forced_status:
        y["statut"] = forced_status

    y["statutJira"] = first(y.get("statutJira"), y.get("statutSource"), y.get("statut"))

    if is_generic(y.get("responsable")):
        y["responsable"] = first(y.get("responsable"), y.get("partenaire"), "Non renseigné")

    if is_generic(y.get("severite")):
        y["severite"] = first(y.get("severity"), y.get("priorite"), y.get("priority"), "Non renseignée")

    if forced_type:
        y["type"] = forced_type

    return y

def has_octane_or_external_reference(x):
    ref = first(
        x.get("octane"),
        x.get("octaneId"),
        x.get("idOctane"),
        x.get("referenceOctane"),
        x.get("reference"),
        x.get("référence"),
    )
    if not ref:
        return False

    p = plain(ref)
    if p.startswith("SIMULATION DERIVEE"):
        return False
    if p.startswith("REPORTING AVRO"):
        return False
    if p.startswith("AERL_GIL-"):
        return False

    return True

def same_current_sprint(x, sprint_current):
    s = clean(x.get("sprint"))
    if not s:
        return False
    return s == sprint_current

def main():
    if not PAYLOAD.exists():
        raise SystemExit(f"[KO] Payload absent : {PAYLOAD}")

    data = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    sprint_current = clean(data.get("sprintCourant"))

    comparaison = data.get("comparaisonSprints") or []
    current_row = None
    for r in comparaison:
        if clean(r.get("sprint")) == sprint_current:
            current_row = r
            break
    if current_row is None and comparaison:
        current_row = comparaison[-1]

    # 1) Corrige les alias legacy de comparaison pour ne plus générer de détails synthétiques Non ventilé.
    for r in comparaison:
        sprint = clean(r.get("sprint"))
        mapping = [
            ("totalDetail", "fluxTotalDetail"),
            ("livresDetail", "fluxLivresDetail"),
            ("enCoursDetail", "fluxEnCoursDetail"),
            ("bloquesDetail", "fluxBloquesDetail"),
        ]
        for legacy_key, official_key in mapping:
            official = r.get(official_key) or []
            if isinstance(official, list):
                r[official_key] = [normalize_item(x, sprint=sprint) for x in official]
                r[legacy_key] = deepcopy(r[official_key])

    # 2) Reconstruit les anomalies du sprint courant depuis les vrais détails Jira.
    #    Refuse les lignes synthétiques BLOQUE-1 / ENCOURS-1.
    def is_synthetic_detail(x):
        if not isinstance(x, dict):
            return True
        vals = [
            clean(x.get("jiraKey")),
            clean(x.get("key")),
            clean(x.get("cle")),
            clean(x.get("reference")),
            clean(x.get("flux")),
        ]
        joined = " ".join(vals).upper()
        return any(token in joined for token in ["BLOQUE-", "ENCOURS-", "TOTAL-", "LIVRE-"])

    def has_real_jira_key(x):
        if not isinstance(x, dict):
            return False
        vals = [
            clean(x.get("jiraKey")),
            clean(x.get("key")),
            clean(x.get("cle")),
            clean(x.get("reference")),
            clean(x.get("flux")),
            clean(x.get("resume")),
            clean(x.get("summary")),
            clean(x.get("titre")),
        ]
        return any(re.search(r"\b[A-Z][A-Z0-9_]+-\d+\b", v) for v in vals)

    def load_comparaison_sprints():
        path = ROOT / "jira" / "presentation" / "comparaison_sprints.json"
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except Exception:
            return []

    def find_row(rows, sprint):
        for r in rows:
            if isinstance(r, dict) and clean(r.get("sprint")) == sprint:
                return r
        return None

    def best_details(*lists):
        candidates = []
        for arr in lists:
            if isinstance(arr, list):
                candidates.append(arr)
        if not candidates:
            return []

        real = []
        for arr in candidates:
            good = [x for x in arr if has_real_jira_key(x) and not is_synthetic_detail(x)]
            if len(good) > len(real):
                real = good

        if real:
            return real

        # Dernier recours seulement : garder les synthèses si rien de réel n'existe.
        return candidates[0]

    comparaison_file = load_comparaison_sprints()
    current_file_row = find_row(comparaison_file, sprint_current)

    if current_file_row:
        current_row = current_file_row

    anomalies_sprint = []

    bloques_source = best_details(
        current_file_row.get("fluxBloquesDetail") if current_file_row else None,
        current_file_row.get("bloquesDetail") if current_file_row else None,
        current_row.get("fluxBloquesDetail") if current_row else None,
        current_row.get("bloquesDetail") if current_row else None,
    )

    encours_source = best_details(
        current_file_row.get("fluxEnCoursDetail") if current_file_row else None,
        current_file_row.get("enCoursDetail") if current_file_row else None,
        current_row.get("fluxEnCoursDetail") if current_row else None,
        current_row.get("enCoursDetail") if current_row else None,
    )

    for x in bloques_source:
        y = normalize_item(
            x,
            sprint=sprint_current,
            forced_status="Ouverte",
            forced_type="Anomalie sprint",
        )
        y["source"] = "API Agile Jira officielle - anomalies sprint"
        if is_generic(y.get("severite")):
            y["severite"] = "Majeure"
        anomalies_sprint.append(y)

    for x in encours_source:
        y = normalize_item(
            x,
            sprint=sprint_current,
            forced_status="En cours",
            forced_type="Anomalie sprint",
        )
        y["source"] = "API Agile Jira officielle - anomalies sprint"
        if is_generic(y.get("severite")):
            y["severite"] = "Mineure"
        anomalies_sprint.append(y)

    # 3) Anomalies d'arrimage / Octane.
    #
    # Population indépendante du sprint :
    # - issue de la JQL Bugs avec Reference non vide ;
    # - pas de filtre sur le sprint courant ;
    # - une anomalie Octane peut également appartenir à un sprint.
    #
    # La clé dédiée anomaliesArrimageDetail reste la source de vérité.
    old_anomalies = data.get("anomaliesArrimageDetail") or []

    print(
        "[TRACE][NORMALISER][INPUT]",
        "old_anomalies=", len(old_anomalies)
    )

    anomalies_arrimage = []

    for x in old_anomalies:
        if not isinstance(x, dict):
            continue

        y = normalize_item(
            x,
            forced_type="Anomalie arrimage",
        )

        y["source"] = "Arrimage - Bug Octane / référence renseignée"
        anomalies_arrimage.append(y)

    # 4) Remplace anomaliesDetail par les anomalies du sprint courant.
    #    On garde les anomalies d'arrimage dans une clé dédiée.
    data["anomaliesDetail"] = anomalies_sprint
    data["anomaliesSprintDetail"] = anomalies_sprint
    data["anomaliesArrimageDetail"] = anomalies_arrimage

    print(
        "[TRACE][NORMALISER][RESULT]",
        "anomaliesArrimageDetail=", len(anomalies_arrimage)
    )

    # 5) Réinjecte les anomalies d'arrimage dans la ventilation flux/anomalies.
    ventilation = data.get("ventilation") or []
    if isinstance(ventilation, list):
        for row in ventilation:
            if isinstance(row, dict):
                row["anomaliesOuvertes"] = 0
                row["ko"] = 0
                row["referencesBloquees"] = []

        index = {}
        for row in ventilation:
            if not isinstance(row, dict):
                continue
            key = (
                clean(row.get("environnement")) or "SIT",
                clean(row.get("domaine")) or "À qualifier",
                clean(row.get("sousDomaine")) or "À qualifier",
            )
            index[key] = row

        for a in anomalies_arrimage:
            key = (
                clean(a.get("environnement")) or "SIT",
                clean(a.get("domaine")) or "À qualifier",
                clean(a.get("sousDomaine")) or "À qualifier",
            )
            if key not in index:
                row = {
                    "sprint": sprint_current,
                    "semaine": current_row.get("semaine") if current_row else "",
                    "environnement": key[0],
                    "domaine": key[1],
                    "sousDomaine": key[2],
                    "total": 0,
                    "prets": 0,
                    "anomaliesOuvertes": 0,
                    "ko": 0,
                    "enCours": 0,
                    "referencesFlux": [],
                    "referencesLivrees": [],
                    "referencesBloquees": [],
                    "responsable": "Non renseigné",
                }
                ventilation.append(row)
                index[key] = row

            row = index[key]
            row["anomaliesOuvertes"] = int(row.get("anomaliesOuvertes") or 0) + 1
            row["ko"] = int(row.get("ko") or 0) + 1
            ref = first(a.get("reference"), a.get("jiraKey"), a.get("flux"))
            if ref and ref not in row["referencesBloquees"]:
                row["referencesBloquees"].append(ref)

    # 6) Normalise les flux existants : domaine/sous-domaine/responsable/statut.
    histo = data.get("histoFlux") or []
    if isinstance(histo, list):
        for i, x in enumerate(histo):
            if isinstance(x, dict):
                histo[i] = normalize_item(x, sprint=sprint_current)

    data["diagnosticAnomaliesDashboard"] = {
        "sprintCourant": sprint_current,
        "anomaliesSprint": len(anomalies_sprint),
        "anomaliesArrimage": len(anomalies_arrimage),
        "regleAnomaliesArrimage": "Bug Octane / Reference non vide, indépendant du sprint",
        "regleAnomaliesSprint": "fluxBloquesDetail + fluxEnCoursDetail du sprint courant, hors legacy Sprint 20/21",
    }

    PAYLOAD.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[OK] Payload normalisé")
    print("sprintCourant =", sprint_current)
    print("anomaliesSprint =", len(anomalies_sprint))
    print("anomaliesArrimage =", len(anomalies_arrimage))
    print("comparaisonSprints =", len(comparaison))

if __name__ == "__main__":
    main()
