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


def make_detail(count, sprint, semaine, env="SIT"):
    return [
        {
            "sprint": sprint,
            "semaine": semaine,
            "environnement": env,
            "domaine": "Non renseigné",
            "sousDomaine": "Non renseigné",
            "flux": "Non détaillé",
            "statut": "Synthèse Jira",
        }
        for _ in range(max(0, int(count or 0)))
    ]


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

        sit_total = as_int(row_value(row, "sitTotal", "SIT", "sit"))
        uat_total = as_int(row_value(row, "uatTotal", "UAT", "uat"))

        r = copy.deepcopy(row)
        r["sprint"] = label
        r["semaine"] = semaine
        r["semaines"] = semaines

        r["fluxTotal"] = total
        r["fluxLivresTotal"] = livres
        r["fluxEnCoursTotal"] = en_cours
        r["fluxBloquesTotal"] = bloques

        r["fluxTotalDetail"] = make_detail(sit_total or total, label, semaine, "SIT") + make_detail(uat_total, label, semaine, "UAT")
        r["fluxLivresDetail"] = make_detail(livres, label, semaine, "SIT")
        r["fluxEnCoursDetail"] = make_detail(en_cours, label, semaine, "SIT")
        r["fluxBloquesDetail"] = make_detail(bloques, label, semaine, "SIT")

        normalized.append(r)

    return normalized


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

    payload["comparaisonSprints"] = normalize_comparison(comparison, courant, precedent)

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
