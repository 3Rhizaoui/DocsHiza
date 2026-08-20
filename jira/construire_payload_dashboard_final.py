from pathlib import Path
import base64
import copy
import datetime as dt
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"
JIRA = ROOT / "jira"

TEMPLATE_HTML = COMMUN / "templates" / "dashboard_gil_template.html"
CURRENT_HTML = COMMUN / "dashboard_gil.html"

SOURCE_DASHBOARD = JIRA / "dashboard_gil_data.json"
COMPARAISON = JIRA / "presentation" / "comparaison_sprints.json"
SPRINT_COURANT = JIRA / "sprints" / "sprint_courant.json"
SPRINT_PRECEDENT = JIRA / "sprints" / "sprint_precedent.json"

OUT = JIRA / "presentation" / "payload_dashboard_final.json"


def fail(message: str):
    raise SystemExit("[ERREUR] " + message)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        fail(f"JSON invalide {path} : {exc}")


def extract_fallback_from_html(path: Path):
    if not path.exists():
        return None

    html = path.read_text(encoding="utf-8", errors="replace")

    b64_patterns = [
        r'const\s+fallbackData\s*=\s*JSON\.parse\(atob\("([^"]+)"\)\)',
        r"const\s+fallbackData\s*=\s*JSON\.parse\(atob\('([^']+)'\)\)",
    ]

    for pattern in b64_patterns:
        m = re.search(pattern, html, flags=re.S)
        if m:
            return json.loads(base64.b64decode(m.group(1)).decode("utf-8"))

    json_patterns = [
        r"const\s+fallbackData\s*=\s*([\s\S]*?);\s*let\s+currentData",
        r"const\s+fallbackData\s*=\s*([\s\S]*?);\s*var\s+currentData",
        r"const\s+fallbackData\s*=\s*([\s\S]*?);\s*window",
    ]

    for pattern in json_patterns:
        m = re.search(pattern, html, flags=re.S)
        if m:
            return json.loads(m.group(1).strip())

    return None


def sprint_name(value, default=""):
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, dict):
        for key in ["name", "nom", "sprint", "label", "titre"]:
            if value.get(key):
                return str(value[key]).strip()
    return default


def pick_sprint_name(path: Path, fallback: str):
    data = read_json(path, {})
    return sprint_name(data, fallback)


def iso_week_now():
    today = dt.date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def get_source_metrics(source: dict):
    if not isinstance(source, dict):
        return 0, 0, 0, 0

    def as_int(value, default=0):
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if value.isdigit():
                return int(value)
            try:
                return int(float(value.replace(",", ".")))
            except Exception:
                return default
        return default

    def count_list(value):
        return len(value) if isinstance(value, list) else 0

    def first_list(*keys):
        for key in keys:
            value = source.get(key)
            if isinstance(value, list):
                return value
        return []

    rows = first_list("flux", "lignesDashboard", "lignes", "fluxPretsArrimage")

    sante = source.get("santeFluxArrimage")
    if isinstance(sante, dict):
        total = as_int(sante.get("total") or sante.get("flux") or sante.get("epics"))
        prets = as_int(sante.get("prets") or sante.get("pretTester") or sante.get("ready"))
        en_cours = as_int(sante.get("enCours") or sante.get("en_cours") or sante.get("inProgress"))
        bugs = as_int(sante.get("bugsBloquants") or sante.get("bloquants"))

        if total or prets or en_cours or bugs:
            return total, prets, en_cours, bugs

    total = (
        as_int(source.get("epics"))
        or as_int(source.get("fluxTotal"))
        or as_int(source.get("total"))
        or count_list(source.get("flux"))
        or count_list(source.get("lignesDashboard"))
        or count_list(source.get("lignes"))
        or count_list(source.get("fluxPretsArrimage"))
    )

    prets = (
        as_int(source.get("prets"))
        or count_list(source.get("prets"))
        or as_int(source.get("pretTester"))
        or count_list(source.get("pretTester"))
        or as_int(source.get("fluxPrets"))
        or count_list(source.get("fluxPrets"))
    )

    en_cours = (
        as_int(source.get("enCours"))
        or count_list(source.get("enCours"))
        or as_int(source.get("encours"))
        or count_list(source.get("encours"))
        or as_int(source.get("fluxEnCours"))
        or count_list(source.get("fluxEnCours"))
    )

    bugs = (
        as_int(source.get("bugsBloquants"))
        or count_list(source.get("bugsBloquants"))
        or as_int(source.get("bloquants"))
        or count_list(source.get("bloquants"))
    )

    if rows:
        if total <= 0:
            total = len(rows)

        if prets <= 0:
            prets = sum(
                1 for row in rows
                if isinstance(row, dict)
                and any(
                    token in str(row.get("statut", "") + " " + row.get("statutJira", "")).lower()
                    for token in ["prêt", "pret", "livré", "livre", "ready"]
                )
            )

        if en_cours <= 0:
            en_cours = sum(
                1 for row in rows
                if isinstance(row, dict)
                and any(
                    token in str(row.get("statut", "") + " " + row.get("statutJira", "")).lower()
                    for token in ["en cours", "progress"]
                )
            )

        if bugs <= 0:
            bugs = sum(
                1 for row in rows
                if isinstance(row, dict)
                and any(
                    token in str(row.get("statut", "") + " " + row.get("statutJira", "")).lower()
                    for token in ["bloqué", "bloque", "ko", "blocked"]
                )
            )

    return total, prets, en_cours, bugs



def compute_score(total: int, prets: int, bugs: int):
    base = 100 if total == 0 else prets / total * 100
    penalty = min(35, bugs * 3)
    return max(0, min(100, round(base - penalty)))


def normalize_comparison_rows(rows, courant, precedent, semaine_courante, semaine_precedente):
    if isinstance(rows, dict):
        rows = rows.get("comparaisonSprints") or rows.get("rows") or rows.get("lignes") or []

    if not isinstance(rows, list):
        rows = []

    normalized = []

    for idx, row in enumerate(rows[:2]):
        if not isinstance(row, dict):
            continue

        r = copy.deepcopy(row)

        if idx == 0:
            r["sprint"] = r.get("sprint") or precedent
            if precedent:
                r["sprint"] = precedent
            if semaine_precedente:
                r["semaine"] = r.get("semaine") or semaine_precedente
                r["semaines"] = r.get("semaines") or [semaine_precedente]

        if idx == 1:
            r["sprint"] = r.get("sprint") or courant
            if courant:
                r["sprint"] = courant
            if semaine_courante:
                r["semaine"] = r.get("semaine") or semaine_courante
                r["semaines"] = r.get("semaines") or [semaine_courante]

        total = r.get("fluxTotal", r.get("total", r.get("flux", 0)))
        livres = r.get("fluxLivresTotal", r.get("livres", r.get("livresTotal", 0)))
        en_cours = r.get("fluxEnCoursTotal", r.get("enCours", r.get("en_cours", 0)))
        bloques = r.get("fluxBloquesTotal", r.get("bloques", r.get("rejetes", 0)))

        r["fluxTotal"] = int(total or 0)
        r["fluxLivresTotal"] = int(livres or 0)
        r["fluxEnCoursTotal"] = int(en_cours or 0)
        r["fluxBloquesTotal"] = int(bloques or 0)

        for detail_key in [
            "fluxTotalDetail",
            "fluxLivresDetail",
            "fluxEnCoursDetail",
            "fluxBloquesDetail",
        ]:
            if not isinstance(r.get(detail_key), list):
                r[detail_key] = []

        normalized.append(r)

    return normalized


def normalize_payload_for_current(payload, courant, precedent, semaine_courante, semaine_precedente):
    payload["sprintCourant"] = courant
    payload["sprintPrecedent"] = precedent
    payload["semaineCourante"] = semaine_courante
    payload["semainePrecedente"] = semaine_precedente
    payload["architectureDashboardFinal"] = True

    for key in ["fluxPretsArrimage", "histoFlux", "anomaliesDetail", "ventilation"]:
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue

        for item in rows:
            if not isinstance(item, dict):
                continue

            item["sprint"] = courant
            if semaine_courante and ("semaine" in item or key in ["histoFlux", "ventilation"]):
                item["semaine"] = semaine_courante

    priorites = payload.get("prioritesHebdo")
    if isinstance(priorites, list):
        for item in priorites:
            if isinstance(item, dict):
                item["sprint"] = courant
                if semaine_courante:
                    item["semaineSuivi"] = semaine_courante

    rows = payload.get("comparaisonSprints")
    if isinstance(rows, list):
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue

            label = precedent if idx == 0 else courant
            semaine = semaine_precedente if idx == 0 else semaine_courante

            row["sprint"] = label
            if semaine:
                row["semaine"] = semaine
                row["semaines"] = [semaine]

            for detail_key in [
                "fluxTotalDetail",
                "fluxLivresDetail",
                "fluxEnCoursDetail",
                "fluxBloquesDetail",
            ]:
                details = row.get(detail_key)
                if isinstance(details, list):
                    for item in details:
                        if isinstance(item, dict):
                            item["sprint"] = label
                            if semaine:
                                item["semaine"] = semaine

    return payload


def main():
    # Base obligatoire : le bon dashboard Sprint 21 riche.
    base = extract_fallback_from_html(TEMPLATE_HTML)

    if not isinstance(base, dict):
        base = extract_fallback_from_html(CURRENT_HTML)

    if not isinstance(base, dict):
        fail("fallbackData riche introuvable dans le template HTML")

    required_sources = [
        (SOURCE_DASHBOARD, "source dashboard JQL Arrimage"),
        (COMPARAISON, "comparaison officielle Sprint N-1 / Sprint courant"),
        (SPRINT_COURANT, "sprint courant officiel"),
        (SPRINT_PRECEDENT, "sprint précédent officiel"),
    ]

    missing = [
        f"{label} : {path}"
        for path, label in required_sources
        if not path.exists()
    ]

    if missing:
        fail(
            "Sources Jira intermédiaires absentes. "
            "Le payload final ne doit pas être construit depuis le template seul.\n- "
            + "\n- ".join(missing)
        )

    source = read_json(SOURCE_DASHBOARD, {})
    comparison = read_json(COMPARAISON, [])

    courant = pick_sprint_name(SPRINT_COURANT, "")
    precedent = pick_sprint_name(SPRINT_PRECEDENT, "")

    comparison_rows = normalize_comparison_rows(
        comparison,
        courant or "Scrum Sprint 23",
        precedent or "Scrum Sprint 22",
        "",
        "",
    )

    if comparison_rows:
        if not precedent:
            precedent = comparison_rows[0].get("sprint") or "Scrum Sprint 22"
        if not courant and len(comparison_rows) > 1:
            courant = comparison_rows[1].get("sprint") or "Scrum Sprint 23"

    courant = courant or "Scrum Sprint 23"
    precedent = precedent or "Scrum Sprint 22"

    semaine_courante = (
        source.get("semaineCourante")
        or source.get("semaine")
        or source.get("constatSemaine")
        or iso_week_now()
    )
    semaine_precedente = source.get("semainePrecedente") or ""

    payload = copy.deepcopy(base)

    total, prets, en_cours, bugs = get_source_metrics(source)

    if total <= 0:
        keys = ", ".join(sorted(source.keys())) if isinstance(source, dict) else type(source).__name__
        fail(
            "Métriques JQL Arrimage absentes ou invalides dans jira/dashboard_gil_data.json. "
            f"Impossible de calculer la santé réelle. Clés disponibles : {keys}"
        )

    score = compute_score(total, prets, bugs)

    payload["santeFluxArrimage"] = {
        "total": total,
        "prets": prets,
        "enCours": en_cours,
        "bugsBloquants": bugs,
        "score": score,
        "statut": "Vert" if score >= 80 else "Orange" if score >= 60 else "Rouge",
        "source": "JQL Arrimage",
    }

    if comparison_rows:
        # On garde les détails legacy du template si la comparaison officielle n'en fournit pas.
        old_rows = payload.get("comparaisonSprints") if isinstance(payload.get("comparaisonSprints"), list) else []

        for idx, row in enumerate(comparison_rows):
            if idx < len(old_rows) and isinstance(old_rows[idx], dict):
                for detail_key in [
                    "fluxTotalDetail",
                    "fluxLivresDetail",
                    "fluxEnCoursDetail",
                    "fluxBloquesDetail",
                ]:
                    if not row.get(detail_key):
                        row[detail_key] = copy.deepcopy(old_rows[idx].get(detail_key) or [])

        payload["comparaisonSprints"] = comparison_rows

    payload = normalize_payload_for_current(
        payload,
        courant,
        precedent,
        semaine_courante,
        semaine_precedente,
    )

    required = ["fluxPretsArrimage", "histoFlux", "comparaisonSprints"]
    empty = [
        key for key in required
        if not isinstance(payload.get(key), list) or len(payload.get(key)) == 0
    ]

    if empty:
        fail("Payload final incomplet : blocs legacy vides : " + ", ".join(empty))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[OK] Payload dashboard final produit :", OUT)
    print("Sprint courant   :", payload.get("sprintCourant"))
    print("Sprint précédent :", payload.get("sprintPrecedent"))
    print("Semaine courante :", payload.get("semaineCourante"))
    print("Score            :", payload.get("santeFluxArrimage", {}).get("score"))
    print("Flux arrimage    :", len(payload.get("fluxPretsArrimage") or []))
    print("Histo flux       :", len(payload.get("histoFlux") or []))
    print("Comparaison      :", len(payload.get("comparaisonSprints") or []))


if __name__ == "__main__":
    main()
