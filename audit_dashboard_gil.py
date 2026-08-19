from pathlib import Path
import argparse
import base64
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path.cwd()
REPORTS = ROOT / "audit_reports"
REPORTS.mkdir(exist_ok=True)

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["dev", "runtime"], default="dev")
args = parser.parse_args()

checks = []

def add(level, code, message, evidence=""):
    checks.append({
        "level": level,
        "code": code,
        "message": message,
        "evidence": evidence,
    })

def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        add("FAIL", "READ_ERROR", f"Lecture impossible : {path}", str(e))
        return ""

def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        add("FAIL", "JSON_INVALID", f"JSON invalide : {path}", str(e))
        return None

def run_cmd(cmd, code, label):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, shell=False)
        if r.returncode == 0:
            add("PASS", code, label, "OK")
        else:
            add("FAIL", code, label, (r.stderr or r.stdout or "").strip()[:2000])
    except Exception as e:
        add("FAIL", code, label, str(e))

def decode_payload_from_html(html):
    m = re.search(r'atob\("([^"]+)"\)', html)
    if m:
        try:
            return "base64", json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
        except Exception as e:
            return "base64 invalide", {"_decode_error": str(e)}

    m = re.search(r"const\s+fallbackData\s*=\s*([\s\S]*?);\s*(?:let|var|const)\s+currentData", html)
    if m:
        try:
            return "json direct", json.loads(m.group(1))
        except Exception as e:
            return "json direct invalide", {"_decode_error": str(e)}

    return "introuvable", {}

def get_name(obj):
    if not isinstance(obj, dict):
        return None
    return obj.get("nom") or obj.get("name") or obj.get("sprint") or obj.get("label")

def get_int(obj, key):
    if not isinstance(obj, dict):
        return None
    value = obj.get(key)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except Exception:
        return None

def sha(path):
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]

def scan_values(obj, tokens, path="payload", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            scan_values(v, tokens, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_values(v, tokens, f"{path}[{i}]", out)
    else:
        text = str(obj)
        for token in tokens:
            if token in text:
                out.append((path, token, text[:160]))
    return out

runtime = args.mode == "runtime"

# ============================================================
# 1. Fichiers critiques
# ============================================================

critical = [
    "jira/capturer_jira_sso.js",
    "jira/Importer_JIRA.cmd",
    "jira/construire_sprints_jira.py",
    "jira/preparer_source_jira.py",
    "jira/controle_import_jira.py",
    "commun/publier_jira_dashboard.py",
    "commun/dashboard_gil.html",
]

for rel in critical:
    p = ROOT / rel
    if p.exists():
        add("PASS", "FILE_EXISTS", f"Fichier présent : {rel}", f"taille={p.stat().st_size}")
    else:
        add("FAIL", "FILE_MISSING", f"Fichier manquant : {rel}")

generic_html = ROOT / "commun/dashboard_gil.html"
legacy_html = ROOT / "commun/dashboard_gil_sprint21.html"

if generic_html.exists():
    add("PASS", "GENERIC_HTML", "Dashboard principal générique présent", str(generic_html))

if legacy_html.exists() and generic_html.exists():
    diff = abs(legacy_html.stat().st_size - generic_html.stat().st_size)
    if diff < 5000:
        add("PASS", "LEGACY_ALIAS", "Alias legacy proche du dashboard générique", f"diff={diff}")
    else:
        add("WARN", "LEGACY_ALIAS_SIZE", "Alias legacy différent du dashboard générique", f"generic={generic_html.stat().st_size}, legacy={legacy_html.stat().st_size}")

# ============================================================
# 2. Compilation / syntaxe
# ============================================================

for rel in [
    "commun/publier_jira_dashboard.py",
    "jira/construire_sprints_jira.py",
    "jira/preparer_source_jira.py",
    "jira/controle_import_jira.py",
]:
    p = ROOT / rel
    if p.exists():
        run_cmd([sys.executable, "-m", "py_compile", str(p)], "PY_COMPILE", f"Compilation Python : {rel}")

node = shutil.which("node")
if node and (ROOT / "jira/capturer_jira_sso.js").exists():
    run_cmd([node, "--check", str(ROOT / "jira/capturer_jira_sso.js")], "NODE_CHECK", "Syntaxe Node : jira/capturer_jira_sso.js")
else:
    add("WARN", "NODE_MISSING", "Node.js absent : contrôle JS ignoré")

# ============================================================
# 3. Références actives vers ancien HTML
# ============================================================

active_refs = []
skip_suffixes = {
    ".json", ".html", ".log", ".bak", ".cmdold", ".pyc", ".png", ".jpg",
    ".jpeg", ".gif", ".pdf", ".xlsx", ".zip"
}

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue

    parts = set(path.parts)
    if ".git" in parts or "__pycache__" in parts or "audit_reports" in parts:
        continue
    if any(part.startswith("_backup") for part in path.parts):
        continue
    if path.suffix.lower() in skip_suffixes:
        continue
    if path.name.startswith("audit_dashboard_gil"):
        continue

    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    text = read_text(path)
    if "dashboard_gil_sprint21.html" in text:
        # Autorisé uniquement dans le publisher :
        # dashboard_gil_sprint21.html reste un alias legacy temporaire.
        # Interdit dans les lanceurs, contrôles, README et scripts actifs.
        if rel == "commun/publier_jira_dashboard.py":
            continue
        active_refs.append(rel)

if active_refs:
    add("FAIL", "ACTIVE_LEGACY_REF", "Références actives restantes vers dashboard_gil_sprint21.html", "\n".join(active_refs))
else:
    add("PASS", "NO_ACTIVE_LEGACY_REF", "Aucune référence active gênante vers dashboard_gil_sprint21.html")

# ============================================================
# 4. Règles publication HTML
# ============================================================

publisher_path = ROOT / "commun/publier_jira_dashboard.py"
publisher = read_text(publisher_path) if publisher_path.exists() else ""

publisher_rules = {
    "load_sprints_dashboard": "Lecture de sprints_dashboard.json",
    "apply_sprint_comparison_from_jira": "Application des sprints Jira au payload",
    "diagnosticSprintsJira": "Diagnostic sprint conservé dans le payload",
    "stableFallbackLoader": "Loader stable après F5/Ctrl+F5",
    "remove_dynamic_sprint_label_script": "Suppression de l'ancien JS fragile",
    "dashboard_gil.html": "Publication du fichier générique",
}

for token, label in publisher_rules.items():
    if token in publisher:
        add("PASS", "PUBLISHER_RULE", label, token)
    else:
        add("FAIL", "PUBLISHER_RULE_MISSING", label, token)

if 'print("HTML legacy :", HTML)\\n' in publisher:
    add("FAIL", "BROKEN_LITERAL_NEWLINE", "Retour ligne littéral cassé dans publier_jira_dashboard.py")
else:
    add("PASS", "NO_BROKEN_LITERAL_NEWLINE", "Pas de retour ligne littéral cassé dans le publisher")

# ============================================================
# 5. Règles capture Jira / sprints officiels
# ============================================================

capture_path = ROOT / "jira/capturer_jira_sso.js"
capture = read_text(capture_path) if capture_path.exists() else ""

capture_rules = {
    "collectOfficialSprintDiagnostics": "Détection officielle des sprints Jira",
    "diagnostic_sprints: sprintDiagnostic": "diagnostic_sprints écrit dans jira_brut.json",
    "rest/agile": "Utilisation API Agile Jira",
    "board": "Détection board Jira",
    "sprint": "Détection sprint Jira",
}

for token, label in capture_rules.items():
    if token in capture:
        add("PASS", "CAPTURE_RULE", label, token)
    else:
        add("FAIL", "CAPTURE_RULE_MISSING", label, token)

if "sans sprint" in capture or "ne prend pas en charge les sprints" in capture:
    add("PASS", "BOARD_400_HANDLED", "Boards sans sprint traités comme non bloquants")
else:
    add("WARN", "BOARD_400_UNKNOWN", "Vérifier que les boards sans sprint ne bloquent pas l'import")

# ============================================================
# 6. Formule statut sprint
# ============================================================

formula_text = ""
for rel in [
    "commun/dashboard_gil.html",
    "commun/generer_dashboard_gil_classique.py",
    "commun/publier_jira_dashboard.py",
]:
    p = ROOT / rel
    if p.exists():
        formula_text += "\n" + read_text(p)

formula_tokens = ["pretTester", "bugsBloquants", "Math.min(35", "* 3"]
hits = [t for t in formula_tokens if t in formula_text]

if len(hits) >= 3:
    add("PASS", "SPRINT_SCORE_FORMULA", "Formule historique de statut sprint préservée", ", ".join(hits))
else:
    add("WARN", "SPRINT_SCORE_FORMULA_UNKNOWN", "Formule de statut sprint à vérifier", ", ".join(hits))

for token in ["scoreBrut", "penalite", "scoreFinal"]:
    if token in formula_text:
        add("PASS", "SCORE_DETAIL", f"Détail score présent : {token}")
    else:
        add("WARN", "SCORE_DETAIL_MISSING", f"Détail score à vérifier : {token}")

# ============================================================
# 7. Fichiers runtime Jira
# ============================================================

jira_brut_path = ROOT / "jira/jira_brut.json"
sprints_path = ROOT / "jira/sprints_dashboard.json"
dash_data_path = ROOT / "jira/dashboard_gil_data.json"

for p in [jira_brut_path, sprints_path, dash_data_path]:
    if p.exists():
        add("PASS", "RUNTIME_FILE_EXISTS", f"Fichier runtime présent : {p.relative_to(ROOT)}", f"sha={sha(p)}")
    elif runtime:
        add("FAIL", "RUNTIME_FILE_MISSING", f"Fichier runtime manquant : {p.relative_to(ROOT)}")
    else:
        add("WARN", "RUNTIME_FILE_ABSENT_DEV", f"Fichier runtime absent en mode dev : {p.relative_to(ROOT)}")

jira_brut = load_json(jira_brut_path)
sprints = load_json(sprints_path)
dash_data = load_json(dash_data_path)

if isinstance(jira_brut, dict):
    if "diagnostic_sprints" in jira_brut:
        add("PASS", "JIRA_BRUT_DIAG", "jira_brut.json contient diagnostic_sprints")
    else:
        add("FAIL" if runtime else "WARN", "JIRA_BRUT_NO_DIAG", "jira_brut.json ne contient pas diagnostic_sprints")

if isinstance(sprints, dict):
    reliable = sprints.get("reliable")
    methode = sprints.get("methode") or sprints.get("method")
    courant = sprints.get("courant") or {}
    precedent = sprints.get("precedent") or {}
    cur_name = get_name(courant)
    prev_name = get_name(precedent)

    if reliable is True:
        add("PASS", "SPRINTS_RELIABLE", "Détection officielle des sprints fiable", str(methode))
    else:
        add("FAIL" if runtime else "WARN", "SPRINTS_NOT_RELIABLE", "Détection sprint non fiable ou absente", str(reliable))

    if cur_name and prev_name:
        add("PASS", "TWO_LAST_SPRINTS", "Sprint courant et sprint précédent détectés", f"{prev_name} -> {cur_name}")
    else:
        add("FAIL" if runtime else "WARN", "TWO_LAST_SPRINTS_MISSING", "Sprint courant/précédent incomplets")

    for label, obj in [("courant", courant), ("precedent", precedent)]:
        flux = get_int(obj, "flux")
        anomalies = get_int(obj, "anomalies")
        total = get_int(obj, "total")
        if flux is not None and anomalies is not None and total is not None:
            if flux + anomalies == total:
                add("PASS", "SPRINT_TOTAL_OK", f"Ventilation {label} cohérente : flux + anomalies = total", f"{flux}+{anomalies}={total}")
            else:
                add("FAIL", "SPRINT_TOTAL_KO", f"Ventilation {label} incohérente", f"flux={flux}, anomalies={anomalies}, total={total}")
        else:
            add("WARN", "SPRINT_TOTAL_UNKNOWN", f"Ventilation {label} non vérifiable", str(obj)[:1000])

    comp = sprints.get("comparaisonSprints")
    if isinstance(comp, list) and len(comp) >= 2:
        text = json.dumps(comp, ensure_ascii=False)
        if cur_name and prev_name and cur_name in text and prev_name in text:
            add("PASS", "SPRINT_COMPARISON_OFFICIAL", "Comparaison officielle contient les deux derniers sprints", f"{prev_name} / {cur_name}")
        else:
            add("WARN", "SPRINT_COMPARISON_NAMES", "Comparaison officielle présente mais noms à vérifier", text[:1000])
    else:
        add("FAIL" if runtime else "WARN", "SPRINT_COMPARISON_MISSING", "comparaisonSprints absente ou incomplète dans sprints_dashboard.json")

if isinstance(dash_data, dict):
    data_text = json.dumps(dash_data, ensure_ascii=False).lower()
    for token in ["sprint", "flux", "epic", "anomal"]:
        if token in data_text:
            add("PASS", "DASH_DATA_DOMAIN", f"dashboard_gil_data.json contient le domaine {token}")
        else:
            add("WARN", "DASH_DATA_DOMAIN_MISSING", f"dashboard_gil_data.json ne montre pas clairement le domaine {token}")

# ============================================================
# 8. HTML générique publié
# ============================================================

if generic_html.exists():
    html = read_text(generic_html)
    mode, payload = decode_payload_from_html(html)

    add("PASS", "HTML_HASH", "Hash dashboard_gil.html", sha(generic_html))

    if "dynamicSprintLabelsScript" in html:
        add("FAIL", "DYNAMIC_SCRIPT_PRESENT", "Ancien dynamicSprintLabelsScript encore présent")
    else:
        add("PASS", "NO_DYNAMIC_SCRIPT", "dynamicSprintLabelsScript absent")

    if "fetch('rapport_gil_v6_data.json'" in html or 'fetch("rapport_gil_v6_data.json' in html:
        add("FAIL", "EXTERNAL_FETCH_ACTIVE", "Fetch externe actif vers rapport_gil_v6_data.json")
    else:
        add("PASS", "NO_EXTERNAL_FETCH", "Pas de fetch externe actif vers rapport_gil_v6_data.json")

    if "stableFallbackLoader" in html:
        add("PASS", "HTML_STABLE_LOADER", "stableFallbackLoader présent dans le HTML")
    else:
        add("FAIL" if runtime else "WARN", "HTML_STABLE_LOADER_MISSING", "stableFallbackLoader absent du HTML publié")

    if payload:
        add("PASS", "HTML_PAYLOAD_DECODED", "Payload fallbackData décodé", mode)

        sprint_courant = payload.get("sprintCourant")
        sprint_precedent = payload.get("sprintPrecedent")
        diag = payload.get("diagnosticSprintsJira") or {}

        if runtime:
            if sprint_courant and sprint_precedent and sprint_courant != "Sprint 21":
                add("PASS", "HTML_DYNAMIC_SPRINTS", "HTML utilise des noms de sprint dynamiques", f"{sprint_precedent} -> {sprint_courant}")
            else:
                add("FAIL", "HTML_DYNAMIC_SPRINTS_MISSING", "HTML encore legacy ou générique côté payload", f"sprintCourant={sprint_courant}, sprintPrecedent={sprint_precedent}")

            if diag.get("reliable") is True:
                add("PASS", "HTML_DIAG_RELIABLE", "Diagnostic sprint Jira fiable dans le payload HTML")
            else:
                add("FAIL", "HTML_DIAG_NOT_RELIABLE", "Diagnostic sprint Jira absent ou non fiable dans le payload HTML", str(diag)[:1000])
        else:
            if sprint_courant == "Sprint 21":
                add("WARN", "DEV_PAYLOAD_LEGACY", "Payload dev encore Sprint 21 : normal si import Jira non exécuté ici")
            else:
                add("PASS", "DEV_PAYLOAD_DYNAMIC", "Payload dev contient déjà un sprint dynamique", str(sprint_courant))

        if isinstance(payload.get("comparaisonSprintsJiraOfficielle"), list):
            add("PASS", "HTML_OFFICIAL_COMPARISON", "comparaisonSprintsJiraOfficielle présente dans le payload HTML")
        elif isinstance(payload.get("comparaisonSprints"), list):
            add("WARN", "HTML_LEGACY_COMPARISON_ONLY", "Comparaison présente mais comparaison officielle non injectée dans le HTML")
        else:
            add("FAIL" if runtime else "WARN", "HTML_COMPARISON_MISSING", "Comparaison sprint absente du payload HTML")

        tokens = [
            "Sprint 21",
            "Sprint 20",
            "Sprint N-1",
            "Sprint actuel",
            "Sprint courant",
            "Sprint précédent",
            "Sprint precedent",
            "À qualifier",
            "Non renseigné",
            "Non renseignée",
        ]
        hits = scan_values(payload, tokens)
        if hits:
            evidence = "\n".join([f"{token} | {path} | {value}" for path, token, value in hits[:80]])
            add("WARN", "NON_VENTILATED_VALUES", f"Valeurs génériques/non ventilées à vérifier : {len(hits)} occurrence(s)", evidence)
        else:
            add("PASS", "NO_NON_VENTILATED_VALUES", "Aucune valeur générique/non ventilée détectée dans le payload")
    else:
        add("FAIL" if runtime else "WARN", "HTML_PAYLOAD_MISSING", "Payload fallbackData introuvable dans dashboard_gil.html", mode)

# ============================================================
# 9. Rapport
# ============================================================

passes = [c for c in checks if c["level"] == "PASS"]
warns = [c for c in checks if c["level"] == "WARN"]
fails = [c for c in checks if c["level"] == "FAIL"]

if fails:
    verdict = "KO"
elif warns:
    verdict = "OK_AVEC_ALERTES"
else:
    verdict = "OK"

stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
json_path = REPORTS / f"audit_dashboard_gil_{args.mode}_{stamp}.json"
md_path = REPORTS / f"audit_dashboard_gil_{args.mode}_{stamp}.md"

payload = {
    "mode": args.mode,
    "verdict": verdict,
    "root": str(ROOT),
    "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    "summary": {
        "PASS": len(passes),
        "WARN": len(warns),
        "FAIL": len(fails),
    },
    "checks": checks,
}

json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    f"# Audit Dashboard GIL - {args.mode}",
    "",
    f"- Verdict : **{verdict}**",
    f"- Racine : `{ROOT}`",
    f"- PASS : {len(passes)}",
    f"- WARN : {len(warns)}",
    f"- FAIL : {len(fails)}",
    "",
]

for level in ["FAIL", "WARN", "PASS"]:
    subset = [c for c in checks if c["level"] == level]
    if not subset:
        continue
    lines.append(f"## {level}")
    lines.append("")
    for c in subset:
        lines.append(f"### {c['code']}")
        lines.append("")
        lines.append(c["message"])
        if c.get("evidence"):
            lines.append("")
            lines.append("```text")
            lines.append(str(c["evidence"]))
            lines.append("```")
        lines.append("")

md_path.write_text("\n".join(lines), encoding="utf-8")

print("============================================================")
print("AUDIT DASHBOARD GIL")
print("============================================================")
print("Mode    :", args.mode)
print("Verdict :", verdict)
print("PASS    :", len(passes))
print("WARN    :", len(warns))
print("FAIL    :", len(fails))
print("Rapport :", md_path)
print("JSON    :", json_path)

if fails:
    print()
    print("ECHECS BLOQUANTS")
    for c in fails:
        print("-", c["code"], ":", c["message"])
elif warns:
    print()
    print("ALERTES A VERIFIER")
    for c in warns[:20]:
        print("-", c["code"], ":", c["message"])
else:
    print()
    print("Aucun échec, aucune alerte.")
