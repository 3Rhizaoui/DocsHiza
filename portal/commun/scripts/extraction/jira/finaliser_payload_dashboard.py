# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PAYLOAD = ROOT / "jira" / "presentation" / "payload_dashboard_final.json"
COMPARAISON = ROOT / "jira" / "presentation" / "comparaison_sprints.json"

OUTPUTS = [
    PAYLOAD,
    ROOT / "jira" / "dashboard_gil_data.json",
    ROOT / "commun" / "dashboard_gil_data.json",
]

GENERIC = {
    "",
    "none",
    "null",
    "non renseigné",
    "non renseigne",
    "non ventilé",
    "non ventile",
    "à qualifier",
    "a qualifier",
    "n/a",
    "-",
}

SYNTHETIC_PREFIXES = ("BLOQUE-", "ENCOURS-", "TOTAL-", "LIVRE-")


def clean(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def fold(v: Any) -> str:
    s = clean(v)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def is_generic(v: Any) -> bool:
    return clean(v).lower() in GENERIC


def find_jira_key(*values: Any) -> str:
    text = " ".join(clean(v) for v in values)
    m = re.search(r"\b[A-Z][A-Z0-9_]+-\d+\b", text)
    return m.group(0) if m else ""


def is_synthetic(v: Any) -> bool:
    s = fold(v)
    return any(s.startswith(prefix) for prefix in SYNTHETIC_PREFIXES)


def item_is_synthetic(x: Any) -> bool:
    if not isinstance(x, dict):
        return True
    vals = [
        x.get("jiraKey"),
        x.get("key"),
        x.get("cle"),
        x.get("reference"),
        x.get("référence"),
        x.get("flux"),
    ]
    return any(is_synthetic(v) for v in vals if clean(v))


def item_jira_key(x: dict) -> str:
    return find_jira_key(
        x.get("jiraKey"),
        x.get("key"),
        x.get("cle"),
        x.get("reference"),
        x.get("référence"),
        x.get("flux"),
        x.get("resume"),
        x.get("summary"),
        x.get("titre"),
        x.get("libelle"),
    )


def normalize_domain_subdomain(x: dict) -> dict:
    y = dict(x)
    text = " ".join(
        clean(y.get(k))
        for k in [
            "resume",
            "summary",
            "titre",
            "libelle",
            "description",
            "flux",
            "reference",
            "jiraKey",
            "key",
            "cle",
        ]
    )
    t = fold(text)

    if is_generic(y.get("domaine")):
        if re.search(r"\bISS\b", t) or "ISSUING" in t:
            y["domaine"] = "Issuing"
        elif re.search(r"\bACQ\b", t) or "ACQUISITION" in t:
            y["domaine"] = "Acquisition"
        else:
            y["domaine"] = "À qualifier"

    if is_generic(y.get("sousDomaine")):
        if "ONBOARD" in t:
            y["sousDomaine"] = "Onboarding"
        elif "AUTHORIZE" in t or re.search(r"\bOA\d", t):
            y["sousDomaine"] = "Authorize"
        elif "DISPUTE" in t or "CONTEST" in t or re.search(r"\bCNT\b", t):
            y["sousDomaine"] = "Contestation"
        elif "GED" in t:
            y["sousDomaine"] = "GED"
        elif "PRECOMP" in t or re.search(r"\bPC\d", t):
            y["sousDomaine"] = "Précompensation"
        elif "CREDIT" in t or "COMMERCANT" in t or "MERCHANT" in t:
            y["sousDomaine"] = "Crédit commerçant"
        else:
            y["sousDomaine"] = "À qualifier"

    if is_generic(y.get("environnement")):
        for env in ["SIT", "UAT", "REC", "PROD"]:
            if re.search(rf"\b{env}\b", t):
                y["environnement"] = env
                y["env"] = env
                break

    if is_generic(y.get("evenement")):
        status = fold(y.get("statut") or y.get("statutJira") or y.get("status") or y.get("etat"))
        if "PRET" in status or "READY" in status or "LIVR" in status:
            y["evenement"] = "Livré"
        elif "BLOQ" in status or "KO" in status:
            y["evenement"] = "Bloqué"
        elif "AFFINAGE" in status or "EN COURS" in status:
            y["evenement"] = "En cours"
        elif "BACKLOG" in status:
            y["evenement"] = "Backlog"

    if is_generic(y.get("responsable")):
        y["responsable"] = "Non assigné Jira"

    key = item_jira_key(y)
    if key:
        for k in ["jiraKey", "key", "cle", "reference", "référence"]:
            if is_generic(y.get(k)) or is_synthetic(y.get(k)):
                y[k] = key
        if is_generic(y.get("flux")) or is_synthetic(y.get("flux")):
            y["flux"] = key

    return y


def normalize_list(arr: Any) -> list[dict]:
    if not isinstance(arr, list):
        return []
    out = []
    for x in arr:
        if isinstance(x, dict):
            out.append(normalize_domain_subdomain(x))
    return out


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    if path == PAYLOAD or path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rows_from_comparaison_file() -> list[dict]:
    raw = load_json(COMPARAISON)
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for k in ["comparaisonSprints", "rows", "sprints", "data"]:
            if isinstance(raw.get(k), list):
                return [x for x in raw[k] if isinstance(x, dict)]
    return []


def row_by_sprint(rows: list[dict], sprint: str) -> dict | None:
    for r in rows:
        if clean(r.get("sprint")) == sprint:
            return r
    return None


def best_real_detail(*arrays: Any) -> list[dict]:
    best: list[dict] = []

    for arr in arrays:
        if not isinstance(arr, list):
            continue

        normalized = normalize_list(arr)
        real = [
            x for x in normalized
            if item_jira_key(x) and not item_is_synthetic(x)
        ]

        if len(real) > len(best):
            best = real

    return best


def dedupe_by_key(arr: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for x in arr:
        k = item_jira_key(x) or clean(x.get("key")) or clean(x.get("reference")) or json.dumps(x, sort_keys=True, ensure_ascii=False)
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def patch_comparison(data: dict) -> None:
    rows = data.get("comparaisonSprints")
    if not isinstance(rows, list):
        return

    official_rows = rows_from_comparaison_file()
    patched_rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        sprint = clean(row.get("sprint"))
        official = row_by_sprint(official_rows, sprint) or {}

        merged = dict(row)
        for k, v in official.items():
            if k not in merged or is_generic(merged.get(k)) or k.endswith("Detail"):
                merged[k] = v

        flux_total = best_real_detail(
            official.get("fluxTotalDetail"),
            merged.get("fluxTotalDetail"),
            merged.get("totalDetail"),
        )
        flux_livres = best_real_detail(
            official.get("fluxLivresDetail"),
            merged.get("fluxLivresDetail"),
            merged.get("livresDetail"),
        )
        flux_bloques = best_real_detail(
            official.get("fluxBloquesDetail"),
            merged.get("fluxBloquesDetail"),
            merged.get("bloquesDetail"),
        )
        flux_encours = best_real_detail(
            official.get("fluxEnCoursDetail"),
            merged.get("fluxEnCoursDetail"),
            merged.get("enCoursDetail"),
        )

        if flux_total:
            merged["fluxTotalDetail"] = flux_total
            merged["totalDetail"] = flux_total
        if flux_livres:
            merged["fluxLivresDetail"] = flux_livres
            merged["livresDetail"] = flux_livres
        if flux_bloques:
            merged["fluxBloquesDetail"] = flux_bloques
            merged["bloquesDetail"] = flux_bloques
        if flux_encours:
            merged["fluxEnCoursDetail"] = flux_encours
            merged["enCoursDetail"] = flux_encours

        merged["source"] = "API Agile Jira officielle"
        merged["comparaisonOfficielle"] = True

        patched_rows.append(merged)

    data["comparaisonSprints"] = patched_rows
    data["comparaisonSprintsOfficielle"] = patched_rows
    data["comparaisonOfficielle"] = patched_rows
    data["comparisonOfficial"] = patched_rows

    diag = data.get("diagnosticSprintsJira")
    if not isinstance(diag, dict):
        diag = {}
    diag["comparaisonOfficielleInjectee"] = True
    diag["sourceComparaison"] = "API Agile Jira officielle"
    data["diagnosticSprintsJira"] = diag


def build_sprint_anomalies(data: dict) -> None:
    print(
        "[TRACE][FINALISER][INPUT]",
        "anomaliesArrimageDetail=", len(data.get("anomaliesArrimageDetail") or []),
        "anomaliesDetail=", len(data.get("anomaliesDetail") or [])
    )
    sprint_current = clean(data.get("sprintCourant"))
    rows = data.get("comparaisonSprints")
    if not isinstance(rows, list):
        return

    current = row_by_sprint([x for x in rows if isinstance(x, dict)], sprint_current)
    if not current:
        return

    anomalies = []

    for x in current.get("fluxBloquesDetail") or []:
        if not isinstance(x, dict) or not item_jira_key(x) or item_is_synthetic(x):
            continue
        y = normalize_domain_subdomain(x)
        y["sprint"] = sprint_current
        y["type"] = "Anomalie sprint"
        y["statut"] = "Ouverte"
        y["statutJira"] = y.get("statutJira") or "Bloqué"
        y["source"] = "API Agile Jira officielle - anomalies sprint"
        if is_generic(y.get("severite")):
            y["severite"] = "Majeure"
        anomalies.append(y)

    for x in current.get("fluxEnCoursDetail") or []:
        if not isinstance(x, dict) or not item_jira_key(x) or item_is_synthetic(x):
            continue
        y = normalize_domain_subdomain(x)
        y["sprint"] = sprint_current
        y["type"] = "Anomalie sprint"
        y["statut"] = "En cours"
        y["statutJira"] = y.get("statutJira") or "En cours"
        y["source"] = "API Agile Jira officielle - anomalies sprint"
        if is_generic(y.get("severite")):
            y["severite"] = "Mineure"
        anomalies.append(y)

    anomalies = dedupe_by_key(anomalies)

    data["anomaliesDetail"] = anomalies
    data["anomaliesSprintDetail"] = anomalies

    diag = data.get("diagnosticAnomaliesDashboard")
    if not isinstance(diag, dict):
        diag = {}
    diag["sprintCourant"] = sprint_current
    diag["anomaliesSprint"] = len(anomalies)
    diag["regleAnomaliesSprint"] = "fluxBloquesDetail + fluxEnCoursDetail réels du sprint courant, sans clés synthétiques"
    data["diagnosticAnomaliesDashboard"] = diag


def patch_histo_and_ventilation(data: dict) -> None:
    histo = normalize_list(data.get("histoFlux"))
    data["histoFlux"] = histo

    by_key = {}
    for x in histo:
        key = item_jira_key(x)
        if key:
            by_key[key] = x

    ventilation = data.get("ventilation")
    if not isinstance(ventilation, list):
        return

    patched = []
    for row in ventilation:
        if not isinstance(row, dict):
            continue

        y = dict(row)
        refs = []
        for k in ["referencesFlux", "referencesLivrees", "referencesBloquees"]:
            if isinstance(y.get(k), list):
                refs.extend(clean(v) for v in y[k])

        related = []
        for ref in refs:
            key = find_jira_key(ref)
            if key and key in by_key:
                related.append(by_key[key])

        if related:
            if is_generic(y.get("domaine")):
                c = Counter(clean(r.get("domaine")) for r in related if not is_generic(r.get("domaine")))
                if c:
                    y["domaine"] = c.most_common(1)[0][0]

            if is_generic(y.get("sousDomaine")):
                c = Counter(clean(r.get("sousDomaine")) for r in related if not is_generic(r.get("sousDomaine")))
                if c:
                    y["sousDomaine"] = c.most_common(1)[0][0]

        if is_generic(y.get("responsable")):
            y["responsable"] = "Non assigné Jira"

        patched.append(y)

    data["ventilation"] = patched


def patch_tendance(data: dict) -> None:
    prev = clean(data.get("sprintPrecedent"))
    if not prev:
        return

    th = data.get("tendanceHebdo")
    if not isinstance(th, dict):
        return

    targets = []
    if isinstance(th.get("previous"), dict):
        targets.append(th["previous"])
    if isinstance(th.get("rows"), list):
        targets.extend(x for x in th["rows"] if isinstance(x, dict))

    for x in targets:
        fm = clean(x.get("faitMarquant"))
        if "Sprint précédent" in fm:
            x["faitMarquant"] = fm.replace("Sprint précédent", prev)


def main() -> int:
    if not PAYLOAD.exists():
        print(f"[KO] Payload absent: {PAYLOAD}")
        return 1

    data = load_json(PAYLOAD)
    if not isinstance(data, dict):
        print("[KO] Payload invalide")
        return 1

    patch_comparison(data)
    build_sprint_anomalies(data)
    patch_histo_and_ventilation(data)
    patch_tendance(data)

    for path in OUTPUTS:
        write_json(path, data)

    anomalies = data.get("anomaliesSprintDetail") or []
    rows = data.get("comparaisonSprints") or []

    synthetic_count = 0
    for row in rows:
        if isinstance(row, dict):
            for k in ["totalDetail", "livresDetail", "bloquesDetail", "enCoursDetail"]:
                for x in row.get(k) or []:
                    if item_is_synthetic(x):
                        synthetic_count += 1

    print(
        "[OK] Payload dashboard finalisé "
        f"| anomaliesSprint={len(anomalies)} "
        f"| lignesSynthétiquesLegacy={synthetic_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
