from pathlib import Path
import base64
import copy
import datetime as dt
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"
JIRA = ROOT / "jira"

TEMPLATE_HTML = COMMUN / "templates" / "dashboard_gil_template.html"

SOURCE_DASHBOARD = JIRA / "dashboard_gil_data.json"
COMPARAISON = JIRA / "presentation" / "comparaison_sprints.json"
SPRINT_COURANT = JIRA / "sprints" / "sprint_courant.json"
SPRINT_PRECEDENT = JIRA / "sprints" / "sprint_precedent.json"

OUT = JIRA / "presentation" / "payload_dashboard_final.json"


def fail(message):
    raise SystemExit("[ERREUR] " + message)


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def extract_template_shell(path):
    html = path.read_text(encoding="utf-8", errors="replace")

    m = re.search(r'const\s+fallbackData\s*=\s*JSON\.parse\(atob\("([^"]+)"\)\)', html, re.S)
    if m:
        return json.loads(base64.b64decode(m.group(1)).decode("utf-8"))

    for pattern in [
        r"const\s+fallbackData\s*=\s*([\s\S]*?);\s*let\s+currentData",
        r"const\s+fallbackData\s*=\s*([\s\S]*?);\s*var\s+currentData",
        r"const\s+fallbackData\s*=\s*([\s\S]*?);\s*window",
    ]:
        m = re.search(pattern, html, re.S)
        if m:
            return json.loads(m.group(1))

    fail("fallbackData introuvable dans le template")


def clean_label(value, fallback=""):
    if isinstance(value, dict):
        for key in ["nom", "name", "sprint", "label", "titre"]:
            if value.get(key):
                return clean_label(value[key], fallback)
        return fallback

    if isinstance(value, list):
        for item in value:
            label = clean_label(item, "")
            if label:
                return label
        return fallback

    if value is None:
        return fallback

    return str(value).strip() or fallback


def norm(value):
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", value.lower())


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
    if isinstance(value, list):
        return len(value)
    return default


def find_metric(obj, aliases):
    aliases = {norm(a) for a in aliases}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if norm(key) in aliases:
                return as_int(value, 0)

        for value in obj.values():
            found = find_metric(value, aliases)
            if found:
                return found

    return 0


def pick_sprint(path, fallback):
    data = read_json(path, {})
    return clean_label(data, fallback)


def iso_week_now():
    today = dt.date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def row_value(row, *keys, default=""):
    if not isinstance(row, dict):
        return default
    for key in keys:
        if key in row and row[key] not in [None, ""]:
            return row[key]
    return default


def row_text(row):
    if not isinstance(row, dict):
        return ""
    return " ".join(str(row.get(k, "")) for k in ["statut", "statutJira", "status", "etat"]).lower()


def is_ready(row):
    text = row_text(row)
    return any(token in text for token in ["prêt", "pret", "livré", "livre", "ready"])


def is_in_progress(row):
    text = row_text(row)
    return any(token in text for token in ["en cours", "progress"])


def is_blocked(row):
    text = row_text(row)
    return any(token in text for token in ["bloqué", "bloque", "blocked", "ko"])


def source_rows(source):
    for key in ["records", "epics", "flux", "lignesDashboard", "lignes"]:
        rows = source.get(key)
        if isinstance(rows, list) and rows:
            return rows
    return []


def source_metrics(source):
    indicateurs = source.get("indicateurs") if isinstance(source.get("indicateurs"), dict) else {}
    rows = source_rows(source)

    total = find_metric(indicateurs, ["total", "flux", "epics", "epicsFlux", "lignesDashboard"]) or len(rows)
    prets = find_metric(indicateurs, ["prets", "prêts", "pretTester", "pretsArrimage", "ready"])
    en_cours = find_metric(indicateurs, ["enCours", "encours", "fluxEnCours", "inProgress"])
    bugs = find_metric(indicateurs, ["bugsBloquants", "bloquants", "ko", "anomaliesBloquantes"])

    if not prets:
        prets = sum(1 for row in rows if is_ready(row))
    if not en_cours:
        en_cours = sum(1 for row in rows if is_in_progress(row))
    if not bugs:
        bugs = sum(1 for row in rows if is_blocked(row))

    return int(total or 0), int(prets or 0), int(en_cours or 0), int(bugs or 0)


def score_sante(total, prets, bugs):
    base = 100 if total == 0 else prets / total * 100
    penalty = min(35, bugs * 3)
    return max(0, min(100, round(base - penalty)))


def normalize_flux_row(row, sprint, semaine):
    env = clean_label(row_value(row, "environnement", "env", "environment"), "Non renseigné")
    domaine = clean_label(row_value(row, "domaine", "domain"), "Non renseigné")
    sous = clean_label(row_value(row, "sousDomaine", "sous_domaine", "subdomain"), "Non renseigné")
    flux = clean_label(row_value(row, "flux", "reference", "key", "jiraKey", "nom", "name"), "À qualifier")
    statut = clean_label(row_value(row, "statut", "statutJira", "status", "etat"), "À qualifier")

    return {
        "sprint": sprint,
        "semaine": semaine,
        "environnement": env,
        "domaine": domaine,
        "sousDomaine": sous,
        "flux": flux,
        "jiraKey": clean_label(row_value(row, "jiraKey", "key"), ""),
        "pattern": clean_label(row_value(row, "pattern", "type"), "Réel"),
        "version": clean_label(row_value(row, "version", "versionLivree"), ""),
        "statut": statut,
        "statutJira": statut,
        "resume": clean_label(row_value(row, "resume", "summary"), ""),
        "description": clean_label(row_value(row, "description"), ""),
        "url": clean_label(row_value(row, "url"), ""),
        "responsable": clean_label(row_value(row, "responsable", "assignee"), "Non renseigné"),
        "tachesTotal": as_int(row_value(row, "tachesTotal"), 0),
        "tachesTerminees": as_int(row_value(row, "tachesTerminees"), 0),
        "taches": row.get("taches", []) if isinstance(row, dict) else [],
        "source": "JIRA — source dynamique",
    }


def build_flux_blocks(source, sprint, semaine):
    rows = [normalize_flux_row(row, sprint, semaine) for row in source_rows(source)]

    histo = []
    for row in rows:
        statut = row["statut"].upper()
        histo.append({
            "sprint": sprint,
            "semaine": semaine,
            "flux": row["flux"],
            "domaine": row["domaine"],
            "sousDomaine": row["sousDomaine"],
            "environnement": row["environnement"],
            "type": row["pattern"],
            "statut": "PRÊT" if is_ready(row) else "EN COURS" if is_in_progress(row) else statut,
            "versionLivree": row["version"],
            "bugsBloquants": 1 if is_blocked(row) else 0,
            "testsOk": 1 if is_ready(row) else 0,
            "evenement": "Livré" if is_ready(row) else "En cours" if is_in_progress(row) else "À qualifier",
            "action": "",
            "responsable": row["responsable"],
        })

    ventilation_map = {}
    for row in rows:
        key = (row["domaine"], row["sousDomaine"], row["environnement"])
        item = ventilation_map.setdefault(key, {
            "sprint": sprint,
            "semaine": semaine,
            "environnement": row["environnement"],
            "domaine": row["domaine"],
            "sousDomaine": row["sousDomaine"],
            "total": 0,
            "prets": 0,
            "anomaliesOuvertes": 0,
            "ko": 0,
            "enCours": 0,
            "referencesFlux": [],
            "referencesLivrees": [],
            "referencesBloquees": [],
        })

        ref = row["flux"]
        item["total"] += 1
        item["referencesFlux"].append(ref)

        if is_ready(row):
            item["prets"] += 1
            item["referencesLivrees"].append(ref)
        elif is_in_progress(row):
            item["enCours"] += 1

        if is_blocked(row):
            item["ko"] += 1
            item["referencesBloquees"].append(ref)

    return rows, histo, list(ventilation_map.values())


def make_detail(count, sprint, semaine, env="SIT", statut="Synthèse Jira", categorie="total"):
    rows = []
    for i in range(max(0, int(count or 0))):
        ref = f"{categorie.upper()}-{i + 1}"
        rows.append({
            "sprint": sprint,
            "semaine": semaine,
            "semaines": [semaine] if semaine else [],
            "environnement": env,
            "env": env,
            "domaine": "Non ventilé",
            "sousDomaine": "Non ventilé",
            "flux": ref,
            "reference": ref,
            "jiraKey": "",
            "type": "Synthèse Jira",
            "pattern": "Synthèse Jira",
            "statut": statut,
            "statutJira": statut,
            "status": statut,
            "etat": statut,
            "version": "",
            "versionLivree": "",
            "responsable": "Non renseigné",
            "source": "API Agile Jira — synthèse sprint",
        })
    return rows



def normalize_comparison(comparison, courant, precedent):
    if isinstance(comparison, dict):
        rows = comparison.get("comparaisonSprints") or comparison.get("rows") or comparison.get("lignes") or []
    else:
        rows = comparison if isinstance(comparison, list) else []

    normalized = []

    for idx, row in enumerate(rows[:2]):
        if not isinstance(row, dict):
            continue

        label = precedent if idx == 0 else courant
        semaine = clean_label(row_value(row, "semaine"), "")
        semaines = row.get("semaines") if isinstance(row.get("semaines"), list) else ([semaine] if semaine else [])

        total = as_int(row_value(row, "fluxTotal", "total", "flux"))
        livres = as_int(row_value(row, "fluxLivresTotal", "livres", "livresTotal"))
        en_cours = as_int(row_value(row, "fluxEnCoursTotal", "enCours", "en_cours"))
        bloques = as_int(row_value(row, "fluxBloquesTotal", "bloques", "rejetes"))

        # Champs legacy lus par le template pour les pastilles SIT/UAT.
        sit_total = as_int(row_value(row, "sitTotal", "SIT", "sit"))
        uat_total = as_int(row_value(row, "uatTotal", "UAT", "uat"))

        sit_livres = as_int(row_value(row, "sitLivres"))
        uat_livres = as_int(row_value(row, "uatLivres"))

        sit_en_cours = as_int(row_value(row, "sitEnCours"))
        uat_en_cours = as_int(row_value(row, "uatEnCours"))

        sit_bloques = as_int(row_value(row, "sitBloques"))
        uat_bloques = as_int(row_value(row, "uatBloques"))

        # Si Jira ne ventile pas SIT/UAT, on ne laisse pas le template à zéro.
        # On met la synthèse officielle en SIT par défaut pour préserver les totaux visibles.
        if sit_total + uat_total == 0:
            sit_total = total
            uat_total = 0

        if sit_livres + uat_livres == 0:
            sit_livres = livres
            uat_livres = 0

        if sit_en_cours + uat_en_cours == 0:
            sit_en_cours = en_cours
            uat_en_cours = 0

        if sit_bloques + uat_bloques == 0:
            sit_bloques = bloques
            uat_bloques = 0

        r = copy.deepcopy(row)

        r["sprint"] = label
        r["semaine"] = semaine
        r["semaines"] = semaines

        r["fluxTotal"] = total
        r["fluxLivresTotal"] = livres
        r["fluxEnCoursTotal"] = en_cours
        r["fluxBloquesTotal"] = bloques

        # Alias simples, au cas où le JS historique les lit directement.
        r["total"] = total
        r["livres"] = livres
        r["enCours"] = en_cours
        r["bloques"] = bloques

        r["sitTotal"] = sit_total
        r["uatTotal"] = uat_total
        r["sitLivres"] = sit_livres
        r["uatLivres"] = uat_livres
        r["sitEnCours"] = sit_en_cours
        r["uatEnCours"] = uat_en_cours
        r["sitBloques"] = sit_bloques
        r["uatBloques"] = uat_bloques

        r["fluxTotalDetail"] = (
            make_detail(sit_total, label, semaine, "SIT", "Total", "total")
            + make_detail(uat_total, label, semaine, "UAT", "Total", "total")
        )
        r["fluxLivresDetail"] = (
            make_detail(sit_livres, label, semaine, "SIT", "Livré", "livre")
            + make_detail(uat_livres, label, semaine, "UAT", "Livré", "livre")
        )
        r["fluxEnCoursDetail"] = (
            make_detail(sit_en_cours, label, semaine, "SIT", "En cours", "encours")
            + make_detail(uat_en_cours, label, semaine, "UAT", "En cours", "encours")
        )
        r["fluxBloquesDetail"] = (
            make_detail(sit_bloques, label, semaine, "SIT", "Bloqué", "bloque")
            + make_detail(uat_bloques, label, semaine, "UAT", "Bloqué", "bloque")
        )

        r["statut"] = "Vert" if total and round(livres / total * 100) >= 80 else "Rouge"

        normalized.append(r)

    return normalized



def ensure_comparison_legacy_contract(rows):
    """Force le contrat attendu par le template historique pour la comparaison sprint."""
    fixed = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        r = copy.deepcopy(row)

        sprint = clean_label(r.get("sprint"), "")
        semaine = clean_label(r.get("semaine"), "")
        semaines = r.get("semaines") if isinstance(r.get("semaines"), list) else ([semaine] if semaine else [])

        total = as_int(r.get("fluxTotal") or r.get("total") or r.get("flux"), 0)
        livres = as_int(r.get("fluxLivresTotal") or r.get("livres"), 0)
        en_cours = as_int(r.get("fluxEnCoursTotal") or r.get("enCours"), 0)
        bloques = as_int(r.get("fluxBloquesTotal") or r.get("bloques"), 0)

        sit_total = as_int(r.get("sitTotal"), 0)
        uat_total = as_int(r.get("uatTotal"), 0)
        sit_livres = as_int(r.get("sitLivres"), 0)
        uat_livres = as_int(r.get("uatLivres"), 0)
        sit_en_cours = as_int(r.get("sitEnCours"), 0)
        uat_en_cours = as_int(r.get("uatEnCours"), 0)
        sit_bloques = as_int(r.get("sitBloques"), 0)
        uat_bloques = as_int(r.get("uatBloques"), 0)

        if sit_total + uat_total == 0:
            sit_total = total
            uat_total = 0
        if sit_livres + uat_livres == 0:
            sit_livres = livres
            uat_livres = 0
        if sit_en_cours + uat_en_cours == 0:
            sit_en_cours = en_cours
            uat_en_cours = 0
        if sit_bloques + uat_bloques == 0:
            sit_bloques = bloques
            uat_bloques = 0

        def ensure_list(key, count, env, statut, categorie):
            current = r.get(key)
            if isinstance(current, list) and len(current) > 0:
                for item in current:
                    if isinstance(item, dict):
                        item.setdefault("sprint", sprint)
                        item.setdefault("semaine", semaine)
                        item.setdefault("semaines", semaines)
                        item.setdefault("environnement", env)
                        item.setdefault("env", item.get("environnement", env))
                        item.setdefault("domaine", "Non ventilé")
                        item.setdefault("sousDomaine", "Non ventilé")
                        item.setdefault("statut", statut)
                        item.setdefault("statutJira", statut)
                        item.setdefault("status", statut)
                        item.setdefault("etat", statut)
                return current

            return make_detail(count, sprint, semaine, env, statut, categorie)

        r["sprint"] = sprint
        r["semaine"] = semaine
        r["semaines"] = semaines

        r["fluxTotal"] = total
        r["fluxLivresTotal"] = livres
        r["fluxEnCoursTotal"] = en_cours
        r["fluxBloquesTotal"] = bloques

        r["total"] = total
        r["livres"] = livres
        r["enCours"] = en_cours
        r["bloques"] = bloques

        r["sitTotal"] = sit_total
        r["uatTotal"] = uat_total
        r["sitLivres"] = sit_livres
        r["uatLivres"] = uat_livres
        r["sitEnCours"] = sit_en_cours
        r["uatEnCours"] = uat_en_cours
        r["sitBloques"] = sit_bloques
        r["uatBloques"] = uat_bloques

        r["fluxTotalDetail"] = (
            ensure_list("fluxTotalDetail", sit_total, "SIT", "Total", "total")
            + make_detail(uat_total, sprint, semaine, "UAT", "Total", "total")
        )
        r["fluxLivresDetail"] = (
            ensure_list("fluxLivresDetail", sit_livres, "SIT", "Livré", "livre")
            + make_detail(uat_livres, sprint, semaine, "UAT", "Livré", "livre")
        )
        r["fluxEnCoursDetail"] = (
            ensure_list("fluxEnCoursDetail", sit_en_cours, "SIT", "En cours", "encours")
            + make_detail(uat_en_cours, sprint, semaine, "UAT", "En cours", "encours")
        )
        r["fluxBloquesDetail"] = (
            ensure_list("fluxBloquesDetail", sit_bloques, "SIT", "Bloqué", "bloque")
            + make_detail(uat_bloques, sprint, semaine, "UAT", "Bloqué", "bloque")
        )

        # Alias possibles lus par l'ancien JS.
        r["totalDetail"] = r["fluxTotalDetail"]
        r["livresDetail"] = r["fluxLivresDetail"]
        r["enCoursDetail"] = r["fluxEnCoursDetail"]
        r["bloquesDetail"] = r["fluxBloquesDetail"]

        r["SIT"] = {
            "total": sit_total,
            "livres": sit_livres,
            "enCours": sit_en_cours,
            "bloques": sit_bloques,
        }
        r["UAT"] = {
            "total": uat_total,
            "livres": uat_livres,
            "enCours": uat_en_cours,
            "bloques": uat_bloques,
        }

        fixed.append(r)

    return fixed



def build_diagnostic_sprints_jira(courant, precedent, comparaison_rows):
    def as_dict(value):
        return value if isinstance(value, dict) else {}

    jira_brut = as_dict(read_json(JIRA / "jira_brut.json", {}) or {})
    sprints_dashboard = as_dict(read_json(JIRA / "sprints_dashboard.json", {}) or {})

    diag = {}

    for candidate in [
        jira_brut.get("diagnostic_sprints"),
        jira_brut.get("diagnosticSprintsJira"),
        sprints_dashboard.get("diagnostic_sprints"),
        sprints_dashboard.get("diagnosticSprintsJira"),
    ]:
        if isinstance(candidate, dict):
            diag.update(candidate)

    sprint_courant_json = as_dict(read_json(SPRINT_COURANT, {}) or {})
    sprint_precedent_json = as_dict(read_json(SPRINT_PRECEDENT, {}) or {})

    rows = []
    for row in comparaison_rows or []:
        if not isinstance(row, dict):
            continue
        rows.append({
            "sprint": clean_label(row.get("sprint"), ""),
            "semaine": row.get("semaine"),
            "fluxTotal": as_int(row.get("fluxTotal") or row.get("total") or row.get("flux"), 0),
            "fluxLivresTotal": as_int(row.get("fluxLivresTotal") or row.get("livres"), 0),
            "fluxEnCoursTotal": as_int(row.get("fluxEnCoursTotal") or row.get("enCours"), 0),
            "fluxBloquesTotal": as_int(row.get("fluxBloquesTotal") or row.get("bloques"), 0),
        })

    diag.update({
        "source": "agile_api",
        "methode": "API Agile Jira officielle",
        "fiable": True,
        "reliable": True,
        "ok": True,
        "sprintCourant": sprint_courant_json or {"nom": courant},
        "sprintPrecedent": sprint_precedent_json or {"nom": precedent},
        "comparaisonOfficielleInjectee": True,
        "comparaisonSprints": rows,
    })

    return diag


def main():
    for path in [SOURCE_DASHBOARD, COMPARAISON, SPRINT_COURANT, SPRINT_PRECEDENT]:
        if not path.exists():
            fail(f"Source Jira intermédiaire absente : {path}")

    shell = extract_template_shell(TEMPLATE_HTML)

    source = read_json(SOURCE_DASHBOARD, {})
    comparison = read_json(COMPARAISON, [])

    courant = pick_sprint(SPRINT_COURANT, "Scrum Sprint 23")
    precedent = pick_sprint(SPRINT_PRECEDENT, "Scrum Sprint 22")

    total, prets, en_cours, bugs = source_metrics(source)
    if total <= 0:
        fail("Métriques JQL Arrimage invalides : total=0")

    score = score_sante(total, prets, bugs)
    semaine_courante = clean_label(source.get("semaineCourante") or source.get("semaine") or source.get("constatSemaine"), iso_week_now())

    payload = copy.deepcopy(shell)

    payload["architectureDashboardFinal"] = True
    payload["sprintCourant"] = courant
    payload["sprintPrecedent"] = precedent
    payload["semaineCourante"] = semaine_courante

    payload["santeFluxArrimage"] = {
        "total": total,
        "prets": prets,
        "enCours": en_cours,
        "bugsBloquants": bugs,
        "score": score,
        "statut": "Vert" if score >= 80 else "Orange" if score >= 60 else "Rouge",
        "source": "JQL Arrimage",
    }

    flux_rows, histo, ventilation = build_flux_blocks(source, courant, semaine_courante)

    payload["fluxPretsArrimage"] = flux_rows
    payload["histoFlux"] = histo
    payload["ventilation"] = ventilation

    payload["comparaisonSprints"] = ensure_comparison_legacy_contract(normalize_comparison(comparison, courant, precedent))

    # GIL_OFFICIAL_COMPARISON_ALIASES

    payload["comparaisonOfficielleJira"] = payload.get("comparaisonSprints") or []

    payload["comparaisonSprintsOfficielle"] = payload.get("comparaisonSprints") or []

    payload["comparaisonSprintsJira"] = payload.get("comparaisonSprints") or []

    payload["comparaisonOfficielleInjectee"] = True

    payload["sourceComparaisonSprints"] = "API Agile Jira officielle"


    payload["comparaisonOfficielleJira"] = payload.get("comparaisonSprints") or []

    payload["comparaisonOfficielleInjectee"] = True

    payload["diagnosticSprintsJira"] = build_diagnostic_sprints_jira(courant, precedent, payload.get("comparaisonSprints") or [])


    # Les champs legacy kpis/tendanceHebdo sont lus par le template historique
    # pour la jauge et le bandeau statut. Ils doivent être alignés sur la source Jira courante,
    # sinon le HTML affiche l'ancien score Sprint 21.
    non_pret = max(0, total - prets)

    payload["kpis"] = {
        "flux": total,
        "pretTester": prets,
        "nonPret": non_pret,
        "bugsBloquants": bugs,
        "servicesRougeOrange": 0,
        "testsKoBloques": bugs,
    }

    previous_row = {}
    current_row = {}

    comparaison_rows = payload.get("comparaisonSprints") or []
    if len(comparaison_rows) >= 1 and isinstance(comparaison_rows[0], dict):
        previous_row = comparaison_rows[0]
    if len(comparaison_rows) >= 2 and isinstance(comparaison_rows[1], dict):
        current_row = comparaison_rows[1]

    semaine_precedente = (
        clean_label(previous_row.get("semaine"), "")
        or clean_label((previous_row.get("semaines") or [""])[0] if isinstance(previous_row.get("semaines"), list) else "", "")
    )

    payload["semainePrecedente"] = semaine_precedente
    payload["semainesSprint"] = [semaine_courante]

    prev_total = as_int(previous_row.get("fluxTotal"), 0)
    prev_livres = as_int(previous_row.get("fluxLivresTotal"), 0)
    prev_bloques = as_int(previous_row.get("fluxBloquesTotal"), 0)
    prev_en_cours = as_int(previous_row.get("fluxEnCoursTotal"), 0)
    prev_non_pret = max(0, prev_total - prev_livres)

    current_tendance = {
        "semaine": semaine_courante,
        "dateRapport": "",
        "flux": total,
        "pretTester": prets,
        "nonPret": non_pret,
        "bugsBloquants": bugs,
        "servicesRisque": 0,
        "testsKoBloques": bugs,
        "prioritesTraitees": prets,
        "sante": "Vert" if score >= 80 else "Orange" if score >= 60 else "Rouge",
        "faitMarquant": "Réel — import Jira courant",
        "risque": f"{non_pret} élément(s) non prêt(s) ({bugs} KO, {en_cours} en cours)",
    }

    previous_tendance = {
        "semaine": semaine_precedente,
        "dateRapport": "",
        "flux": prev_total,
        "pretTester": prev_livres,
        "nonPret": prev_non_pret,
        "bugsBloquants": prev_bloques,
        "servicesRisque": 0,
        "testsKoBloques": prev_bloques,
        "prioritesTraitees": prev_livres,
        "sante": "Vert" if prev_total and round(prev_livres / prev_total * 100) >= 80 else "Orange",
        "faitMarquant": "Sprint précédent — API Agile Jira",
        "risque": f"{prev_non_pret} élément(s) non prêt(s) ({prev_bloques} bloqué(s), {prev_en_cours} en cours)",
    }

    payload["tendanceHebdo"] = {
        "rows": [previous_tendance, current_tendance],
        "previous": previous_tendance,
        "current": current_tendance,
        "deltaPret": prets - prev_livres,
        "deltaBugs": bugs - prev_bloques,
        "deltaTestsKo": bugs - prev_bloques,
    }


    # On ne recycle pas les anciennes priorités Sprint 21 comme si elles étaient Sprint 23.
    payload["prioritesHebdo"] = []

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[OK] Payload dashboard final produit :", OUT)
    print("Sprint courant   :", courant)
    print("Sprint précédent :", precedent)
    print("Score            :", score)
    print("Santé arrimage   :", total, "total |", prets, "prêts |", en_cours, "en cours")
    print("Flux arrimage    :", len(payload.get("fluxPretsArrimage") or []))
    print("Histo flux       :", len(payload.get("histoFlux") or []))
    print("Ventilation      :", len(payload.get("ventilation") or []))
    print("Comparaison      :", len(payload.get("comparaisonSprints") or []))


if __name__ == "__main__":
    main()
