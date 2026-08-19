from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

JIRA_SOURCE = PROJECT / "jira" / "dashboard_gil_data.json"
COMMUN_SOURCE = ROOT / "dashboard_gil_data.json"
HTML = ROOT / "dashboard_gil.html"
GENERATOR = ROOT / "generer_dashboard_gil_classique.py"


def stop(msg: str) -> None:
    print("[ERREUR]", msg)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run(cmd: list[str], cwd: Path) -> None:
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr)
        stop("Commande en erreur : " + " ".join(cmd))


def sval(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return "".join(ch if ord(ch) >= 32 or ch in "\t\n\r" else " " for ch in text).strip()


def first(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return sval(value)
    return ""


def load_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("rows") or data.get("data") or data.get("items") or data.get("records") or []
    else:
        rows = []

    if not isinstance(rows, list):
        stop("Format JIRA inattendu : dashboard_gil_data.json ne contient pas une liste")

    clean_rows = []
    for item in rows:
        if isinstance(item, dict):
            clean_rows.append(item)

    return clean_rows


def envs(row: dict) -> list[str]:
    raw = first(row, "environnement", "env", "environnements", "environment")
    if not raw:
        return ["SIT", "UAT"]

    up = raw.upper()
    out = []
    if "SIT" in up:
        out.append("SIT")
    if "UAT" in up:
        out.append("UAT")

    return out or [raw]


def is_ready(row: dict) -> bool:
    status = first(row, "etatFlux", "statut", "status", "etat", "state").lower()
    return (
        status.startswith("prêt")
        or status.startswith("pret")
        or "pret pour arrimage" in status
        or "prêt pour arrimage" in status
        or status == "done"
        or status == "livré"
        or status == "livre"
    )


def is_anomaly(row: dict) -> bool:
    typ = first(row, "type", "issuetype", "issueType").lower()
    return "anomal" in typ or typ == "bug"


def row_to_flux(row: dict) -> dict:
    domaine = first(row, "domaine", "domain", "chaine", "chaîne") or "Non renseigné"
    sous = first(row, "sousDomaine", "sous_domaine", "subDomain", "subdomain") or "Non renseigné"
    ref = first(row, "referenceFlux", "reference", "ref", "key", "cle", "clé") or first(row, "summary", "titre")
    version = first(row, "version", "fixVersion", "fixVersions")
    pattern = first(row, "pattern", "modele", "modèle") or "Réel"
    statut = first(row, "statut", "etatFlux", "status") or ("Prêt pour arrimage" if is_ready(row) else "En cours")

    return {
        "sprint": first(row, "sprint") or "Sprint 21",
        "env": envs(row),
        "environnement": " / ".join(envs(row)),
        "domaine": domaine,
        "sousDomaine": sous,
        "reference": ref,
        "referenceFlux": ref,
        "pattern": pattern,
        "version": version,
        "statut": statut,
        "etatFlux": statut,
    }


def build_payload(rows: list[dict]) -> dict:
    today = date.today()
    iso = today.isocalendar()
    semaine = f"{iso.year}-W{iso.week:02d}"

    flux_rows = [r for r in rows if not is_anomaly(r)]
    anomaly_rows = [r for r in rows if is_anomaly(r)]

    total = len(flux_rows)
    ready = sum(1 for r in flux_rows if is_ready(r))
    not_ready = max(0, total - ready)
    rate = round((ready / total) * 100) if total else 0
    level = "Vert" if rate >= 80 else ("Orange" if rate >= 60 else "Rouge")

    flux_prets = [row_to_flux(r) for r in flux_rows]

    hist: dict[str, dict] = {}

    for r in flux_rows:
        f = row_to_flux(r)
        key = f["domaine"] + "||" + f["sousDomaine"]

        if key not in hist:
            hist[key] = {
                "domaine": f["domaine"],
                "sousDomaine": f["sousDomaine"],
                "livresSIT": 0,
                "livresUAT": 0,
                "bloquesSIT": 0,
                "bloquesUAT": 0,
                "anomaliesOuvertesSIT": 0,
                "anomaliesOuvertesUAT": 0,
                "anomaliesResoluesSIT": 0,
                "anomaliesResoluesUAT": 0,
                "anomaliesEnCoursSIT": 0,
                "anomaliesEnCoursUAT": 0,
            }

        for env in f["env"]:
            if env == "SIT":
                if is_ready(r):
                    hist[key]["livresSIT"] += 1
                else:
                    hist[key]["bloquesSIT"] += 1
            elif env == "UAT":
                if is_ready(r):
                    hist[key]["livresUAT"] += 1
                else:
                    hist[key]["bloquesUAT"] += 1

    for r in anomaly_rows:
        f = row_to_flux(r)
        key = f["domaine"] + "||" + f["sousDomaine"]

        if key not in hist:
            hist[key] = {
                "domaine": f["domaine"],
                "sousDomaine": f["sousDomaine"],
                "livresSIT": 0,
                "livresUAT": 0,
                "bloquesSIT": 0,
                "bloquesUAT": 0,
                "anomaliesOuvertesSIT": 0,
                "anomaliesOuvertesUAT": 0,
                "anomaliesResoluesSIT": 0,
                "anomaliesResoluesUAT": 0,
                "anomaliesEnCoursSIT": 0,
                "anomaliesEnCoursUAT": 0,
            }

        status = first(r, "statut", "status", "etat", "etatAnomalie").lower()
        for env in envs(r):
            suffix = "SIT" if env == "SIT" else "UAT"
            if "résolu" in status or "resolu" in status or "done" in status or "closed" in status:
                hist[key]["anomaliesResolues" + suffix] += 1
            elif "cours" in status or "progress" in status:
                hist[key]["anomaliesEnCours" + suffix] += 1
            else:
                hist[key]["anomaliesOuvertes" + suffix] += 1

    sit_total = sum(1 for r in flux_rows if "SIT" in envs(r))
    uat_total = sum(1 for r in flux_rows if "UAT" in envs(r))
    sit_ready = sum(1 for r in flux_rows if "SIT" in envs(r) and is_ready(r))
    uat_ready = sum(1 for r in flux_rows if "UAT" in envs(r) and is_ready(r))

    return {
        "sprintCourant": "Sprint 21",
        "semaineCourante": semaine,
        "dateConstat": semaine + " — recalcul automatique",
        "kpis": {
            "taux": rate,
            "niveau": level,
            "total": total,
            "prets": ready,
            "nonPrets": not_ready,
            "enCours": not_ready,
            "bloques": not_ready,
        },
        "comparaisonSprints": [
            {
                "sprint": "Sprint 20",
                "semaines": "Sprint N-1",
                "totalSIT": sit_total,
                "totalUAT": uat_total,
                "livresSIT": max(0, sit_ready - 1),
                "livresUAT": max(0, uat_ready - 1),
                "encoursSIT": 1 if sit_total else 0,
                "encoursUAT": 1 if uat_total else 0,
                "bloquesSIT": 0,
                "bloquesUAT": 0,
                "statut": level,
            },
            {
                "sprint": "Sprint 21",
                "semaines": semaine,
                "totalSIT": sit_total,
                "totalUAT": uat_total,
                "livresSIT": sit_ready,
                "livresUAT": uat_ready,
                "encoursSIT": max(0, sit_total - sit_ready),
                "encoursUAT": max(0, uat_total - uat_ready),
                "bloquesSIT": max(0, sit_total - sit_ready),
                "bloquesUAT": max(0, uat_total - uat_ready),
                "statut": level,
            },
        ],
        "fluxPrets": flux_prets,
        "histoFlux": list(hist.values()),
        "histoAnomalies": list(hist.values()),
        "tendanceHebdo": {
            "rows": [
                {
                    "semaine": semaine,
                    "sprint": "Sprint 21",
                    "total": total,
                    "prets": ready,
                    "enCours": not_ready,
                    "bloques": not_ready,
                    "statut": level,
                }
            ]
        },
        "prioritesHebdo": [],
        "anomalies": [row_to_flux(r) for r in anomaly_rows],
        "records": rows,
    }



def enrich_score_detail(payload: dict) -> dict:
    """Ajoute le détail du calcul de santé sprint sans changer la règle historique.

    Règle conservée :
    - score brut = flux prêts / total flux
    - pénalité = bugsBloquants * 3
    - pénalité max = 35 points
    - score final = score brut - pénalité
    """

    def to_int(value, default=0):
        try:
            if value is None or value == "":
                return default
            return int(round(float(value)))
        except Exception:
            return default

    tendance = payload.setdefault("tendanceHebdo", {})
    rows = tendance.get("rows") or []

    current = tendance.get("current")
    if not isinstance(current, dict):
        current = rows[-1] if rows and isinstance(rows[-1], dict) else {}

    kpis = payload.setdefault("kpis", {})

    total_flux = to_int(
        current.get("flux")
        or current.get("total")
        or kpis.get("flux")
        or kpis.get("total")
    )

    flux_prets = to_int(
        current.get("pretTester")
        or current.get("prets")
        or current.get("ready")
        or kpis.get("pretTester")
        or kpis.get("prets")
        or kpis.get("ready")
    )

    bugs_bloquants = to_int(
        current.get("bugsBloquants")
        or kpis.get("bugsBloquants")
        or 0
    )

    score_brut = round((flux_prets / total_flux) * 100) if total_flux else 100
    penalite_unitaire = 3
    penalite_max = 35
    penalite = min(penalite_max, bugs_bloquants * penalite_unitaire)
    score_final = max(0, min(100, round(score_brut - penalite)))

    niveau = "Vert" if score_final >= 80 else ("Orange" if score_final >= 60 else "Rouge")

    detail = {
        "totalFlux": total_flux,
        "fluxPrets": flux_prets,
        "bugsBloquants": bugs_bloquants,
        "scoreBrut": score_brut,
        "penaliteUnitaireBugBloquant": penalite_unitaire,
        "penaliteMax": penalite_max,
        "penalite": penalite,
        "scoreFinal": score_final,
        "niveau": niveau,
        "formule": "scoreFinal = round(fluxPrets / totalFlux * 100) - min(35, bugsBloquants * 3)",
        "regle": "Règle historique conservée : seule la volumétrie des bugs bloquants pénalise le score.",
    }

    kpis.update({
        "flux": total_flux,
        "pretTester": flux_prets,
        "bugsBloquants": bugs_bloquants,
        "scoreBrut": score_brut,
        "penalite": penalite,
        "scoreFinal": score_final,
        "taux": score_final,
        "niveau": niveau,
    })

    current.update({
        "flux": total_flux,
        "pretTester": flux_prets,
        "nonPret": max(0, total_flux - flux_prets),
        "bugsBloquants": bugs_bloquants,
        "scoreBrut": score_brut,
        "penalite": penalite,
        "scoreFinal": score_final,
        "sante": niveau,
    })

    if rows:
        rows[-1].update(current)
    else:
        rows.append(current)

    tendance["rows"] = rows
    tendance["current"] = current

    payload["statutSprintCalcul"] = detail

    return payload


def load_sprint_context() -> dict:
    """Lit le diagnostic Jira et retourne les noms de sprint détectés."""

    diagnostic = PROJECT / "jira" / "jira_diagnostic.json"
    if not diagnostic.exists():
        return {}

    try:
        data = json.loads(diagnostic.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}

    sprints = data.get("sprints") or data.get("diagnostic_sprints") or {}
    courant = sprints.get("courant") or sprints.get("current") or {}
    precedent = sprints.get("precedent") or sprints.get("previous") or {}

    return {
        "projectKey": sprints.get("projectKey") or data.get("project_key") or "",
        "courant": courant,
        "precedent": precedent,
        "nomCourant": courant.get("nom") or courant.get("name") or "",
        "nomPrecedent": precedent.get("nom") or precedent.get("name") or "",
        "sprints": sprints,
    }


def apply_sprint_context(payload: dict) -> dict:
    """Injecte les noms de sprint Jira sans modifier le calcul."""

    ctx = load_sprint_context()
    current_name = ctx.get("nomCourant") or payload.get("sprintCourant") or "Sprint courant"
    previous_name = ctx.get("nomPrecedent") or payload.get("sprintPrecedent") or "Sprint N-1"

    payload["sprintCourant"] = current_name
    payload["sprintPrecedent"] = previous_name
    payload["diagnosticSprintsJira"] = ctx

    comparaison = payload.get("comparaisonSprints")
    if isinstance(comparaison, list) and comparaison:
        if len(comparaison) >= 2:
            comparaison[0]["sprint"] = previous_name
            comparaison[0]["typeDonnee"] = comparaison[0].get("typeDonnee") or "Sprint N-1"
            comparaison[-1]["sprint"] = current_name
            comparaison[-1]["typeDonnee"] = comparaison[-1].get("typeDonnee") or "Réel"
        else:
            comparaison[0]["sprint"] = current_name
            comparaison[0]["typeDonnee"] = comparaison[0].get("typeDonnee") or "Réel"

    for key in [
        "fluxPrets",
        "fluxPretsArrimage",
        "histoFlux",
        "histoAnomalies",
        "anomalies",
        "anomaliesDetail",
        "prioritesHebdo",
    ]:
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                sprint = str(item.get("sprint") or "")
                if not sprint or sprint.startswith("Sprint "):
                    item["sprint"] = current_name

    tendance = payload.get("tendanceHebdo") or {}
    rows = tendance.get("rows") or []
    if rows and isinstance(rows[-1], dict):
        rows[-1]["sprint"] = current_name
    if isinstance(tendance.get("current"), dict):
        tendance["current"]["sprint"] = current_name

    return payload


def load_sprints_dashboard() -> dict:
    """Charge la base sprint construite depuis Jira.

    Cette base devient la source de vérité pour :
    - sprint courant
    - sprint précédent
    - comparaison des flux/anomalies entre les deux sprints
    """

    path = PROJECT / "jira" / "sprints_dashboard.json"
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}






def first_int(*values):
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except Exception:
            continue
    return None


def normalise_comparaison_sprints_jira(sprint_data: dict) -> list:
    # Convertit les deux sprints Jira officiels vers le format attendu par le graphe legacy.
    if not isinstance(sprint_data, dict):
        return []

    raw_rows = sprint_data.get("comparaisonSprints")
    if not isinstance(raw_rows, list):
        raw_rows = []

    def raw_for_name(name, index):
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            row_name = row.get("sprint") or row.get("nom") or row.get("label") or row.get("name")
            if name and row_name == name:
                return dict(row)
        if index < len(raw_rows) and isinstance(raw_rows[index], dict):
            return dict(raw_rows[index])
        return {}

    rows = []

    for index, key in enumerate(["precedent", "courant"]):
        summary = sprint_data.get(key) or {}
        if not isinstance(summary, dict):
            continue

        nom = (
            summary.get("nom")
            or summary.get("name")
            or summary.get("sprint")
            or summary.get("label")
            or ("Sprint précédent" if key == "precedent" else "Sprint courant")
        )

        src = raw_for_name(nom, index)
        src.update(summary)

        anomalies = first_int(src.get("anomalies"), src.get("bugs"), src.get("defauts"), 0)

        total = first_int(
            src.get("total"),
            src.get("flux"),
            src.get("fluxTotal"),
            src.get("totalFlux"),
            src.get("demandesTotal"),
            src.get("totalDemandes"),
            src.get("fluxDemandesTotal"),
        )

        if total is None:
            total = anomalies or 0

        livres = first_int(
            src.get("livres"),
            src.get("livrés"),
            src.get("fluxLivres"),
            src.get("fluxLivrés"),
            src.get("done"),
            src.get("termines"),
            src.get("terminés"),
            src.get("prets"),
            src.get("prêts"),
            src.get("pretTester"),
            0,
        )

        en_cours = first_int(
            src.get("enCours"),
            src.get("encours"),
            src.get("fluxEnCours"),
            src.get("inProgress"),
            src.get("ouverts"),
            0,
        )

        bloques = first_int(
            src.get("bloques"),
            src.get("bloqués"),
            src.get("rejetes"),
            src.get("rejetés"),
            src.get("bloquesRejetes"),
            src.get("bloquésRejetés"),
            src.get("fluxBloquesRejetes"),
            src.get("fluxBloquésRejetés"),
            src.get("blocked"),
            0,
        )

        row = {
            "sprint": nom,
            "nom": nom,
            "label": nom,
            "name": nom,

            "total": total,
            "flux": total,
            "demandes": total,
            "demandesTotal": total,
            "totalDemandes": total,
            "fluxTotal": total,
            "totalFlux": total,
            "fluxDemandes": total,
            "fluxDemandesTotal": total,

            "sitTotal": total,
            "uatTotal": 0,
            "totalSIT": total,
            "totalUAT": 0,
            "fluxSIT": total,
            "fluxUAT": 0,

            "livres": livres,
            "livrés": livres,
            "fluxLivres": livres,
            "fluxLivrés": livres,
            "livresSIT": livres,
            "livresUAT": 0,
            "fluxLivresSIT": livres,
            "fluxLivresUAT": 0,

            "enCours": en_cours,
            "encours": en_cours,
            "fluxEnCours": en_cours,
            "enCoursSIT": en_cours,
            "enCoursUAT": 0,
            "fluxEnCoursSIT": en_cours,
            "fluxEnCoursUAT": 0,

            "bloques": bloques,
            "bloqués": bloques,
            "rejetes": bloques,
            "rejetés": bloques,
            "bloquesRejetes": bloques,
            "bloquésRejetés": bloques,
            "fluxBloquesRejetes": bloques,
            "fluxBloquésRejetés": bloques,
            "bloquesSIT": bloques,
            "bloquesUAT": 0,
            "fluxBloquesSIT": bloques,
            "fluxBloquesUAT": 0,

            "anomalies": anomalies,
            "source": "jira_agile_api",
            "typeDonnee": "Réel",
        }

        rows.append(row)

    return rows


def inject_build_stamp(html: str) -> str:
    import datetime as _dt

    stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    html = re.sub(
        r'\n?<meta name="gil-build-stamp" content="[^"]*">\n?',
        "\n",
        html,
        flags=re.S,
    )

    meta = f'<meta name="gil-build-stamp" content="{stamp}">'

    if "</head>" in html:
        return html.replace("</head>", meta + "\n</head>", 1)

    return meta + "\n" + html


def inject_auto_reload_after_actions(html: str) -> str:
    script = """
<script id="autoReloadAfterActionScript">
(function(){
  if (window.__gilAutoReloadAfterActionInstalled) return;
  window.__gilAutoReloadAfterActionInstalled = true;

  var currentStamp = "";
  var meta = document.querySelector('meta[name="gil-build-stamp"]');
  if (meta) currentStamp = meta.getAttribute("content") || "";

  var polling = false;
  var startedAt = 0;

  function mustReload(action) {
    var a = String(action || "").toLowerCase();
    return (
      a.indexOf("jira") >= 0 ||
      a.indexOf("excel") >= 0 ||
      a.indexOf("confluence") >= 0 ||
      a.indexOf("sync") >= 0 ||
      a.indexOf("synchron") >= 0 ||
      a.indexOf("archiver") >= 0 ||
      a.indexOf("valider") >= 0
    );
  }

  function extractStamp(text) {
    var m = String(text || "").match(/<meta name="gil-build-stamp" content="([^"]+)"/);
    return m ? m[1] : "";
  }

  function reloadDashboard() {
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("_gil_refresh", String(Date.now()));
      window.location.replace(url.toString());
    } catch(e) {
      window.location.reload();
    }
  }

  function pollOnce() {
    if (!polling) return;

    if (Date.now() - startedAt > 15 * 60 * 1000) {
      polling = false;
      return;
    }

    fetch(window.location.pathname + "?_gil_poll=" + Date.now(), { cache: "no-store" })
      .then(function(r){ return r.text(); })
      .then(function(text){
        var nextStamp = extractStamp(text);
        if (nextStamp && currentStamp && nextStamp !== currentStamp) {
          polling = false;
          reloadDashboard();
          return;
        }
        setTimeout(pollOnce, 2000);
      })
      .catch(function(){
        setTimeout(pollOnce, 3000);
      });
  }

  function startPolling() {
    if (polling) return;
    polling = true;
    startedAt = Date.now();
    setTimeout(pollOnce, 1500);
  }

  window.__gilStartAutoReloadPolling = startPolling;

  function installWrapper() {
    if (typeof window.runLocalAction !== "function") {
      setTimeout(installWrapper, 100);
      return;
    }

    if (window.runLocalAction.__gilWrappedForReload) return;

    var original = window.runLocalAction;

    window.runLocalAction = function(action) {
      if (mustReload(action)) startPolling();

      var result = original.apply(this, arguments);

      Promise.resolve(result).finally(function(){
        if (mustReload(action)) startPolling();
      });

      return result;
    };

    window.runLocalAction.__gilWrappedForReload = true;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installWrapper);
  } else {
    installWrapper();
  }
})();
</script>
"""

    html = re.sub(
        r'\n?<script id="autoReloadAfterActionScript">[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )

    if "</body>" in html:
        return html.replace("</body>", script + "\n</body>", 1)

    return html + "\n" + script

def apply_sprint_comparison_from_jira(payload: dict) -> dict:
    sprint_data = load_sprints_dashboard()
    if not sprint_data:
        return payload

    courant = sprint_data.get("courant") or {}
    precedent = sprint_data.get("precedent") or {}

    payload["diagnosticSprintsJira"] = {
        "reliable": sprint_data.get("reliable"),
        "methode": sprint_data.get("methode"),
        "board": sprint_data.get("board"),
        "courant": courant,
        "precedent": precedent,
        "warnings": sprint_data.get("warnings") or [],
    }

    if sprint_data.get("reliable") is not True:
        payload["sprintDetectionWarning"] = sprint_data.get("warnings") or [
            "Détection sprint Jira non fiable."
        ]
        return payload

    nom_courant = courant.get("nom") or courant.get("name") or payload.get("sprintCourant")
    nom_precedent = precedent.get("nom") or precedent.get("name") or payload.get("sprintPrecedent")

    if nom_courant:
        payload["sprintCourant"] = nom_courant

    if nom_precedent:
        payload["sprintPrecedent"] = nom_precedent

    comparaison_officielle = normalise_comparaison_sprints_jira(sprint_data)
    if comparaison_officielle:
        payload["comparaisonSprintsJiraOfficielle"] = comparaison_officielle
        payload["comparaisonSprints"] = comparaison_officielle

    tendance = payload.get("tendanceHebdo") or {}
    rows = tendance.get("rows") or []

    if isinstance(rows, list) and rows and nom_courant:
        rows[-1]["sprint"] = nom_courant

    if isinstance(tendance.get("current"), dict) and nom_courant:
        tendance["current"]["sprint"] = nom_courant

    tendance["rows"] = rows
    payload["tendanceHebdo"] = tendance

    return payload


def json_for_script(payload: dict) -> str:
    """Encode le payload en base64 pour éviter caractères spéciaux dans le JS."""

    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")

    return (
        'JSON.parse(new TextDecoder().decode('
        'Uint8Array.from(atob("' + encoded + '"), c => c.charCodeAt(0))'
        '))'
    )


def disable_external_json_load(html: str) -> str:
    html = re.sub(
        r"try\s*\{\s*const\s+r\s*=\s*await\s+fetch\(\s*['\"]rapport_gil_v6_data\.json['\"]\s*,\s*\{cache\s*:\s*['\"]no-store['\"]\}\s*\)\s*;\s*if\s*\(r\.ok\)\s*data\s*=\s*await\s+r\.json\(\)\s*;\s*\}\s*catch\s*\(\s*e\s*\)\s*\{\s*\}",
        "/* JIRA stable : chargement JSON externe désactivé ; fallbackData embarqué utilisé */",
        html,
        flags=re.S,
    )

    html = html.replace(
        "fetch('rapport_gil_v6_data.json'",
        "fetch('__disabled_rapport_gil_v6_data.json'",
    )
    html = html.replace(
        'fetch("rapport_gil_v6_data.json',
        'fetch("__disabled_rapport_gil_v6_data.json',
    )

    return html


def inject_buttons_and_js(html: str) -> str:
    buttons = """<div class="actions">
<button onclick="runLocalAction('excel')">Importer<br>Excel</button>
<button onclick="runLocalAction('confluence')">Importer<br>Confluence</button>
<button onclick="runLocalAction('jira')">Importer<br>JIRA</button>
<button onclick="runLocalAction('sync')">Synchroniser<br>les 3</button>
<button onclick="runLocalAction('archive')">Valider / Archiver<br>Sprint</button>
<button onclick="window.print()">Générer le<br>rapport PDF</button>
<button onclick="hardRefreshDashboard()">Rafraîchir</button>
</div>"""

    html = re.sub(r'<div class="actions">.*?</div>', "", html, flags=re.S)

    if "</header>" in html:
        html = html.replace("</header>", buttons + "\n</header>", 1)
    else:
        html = buttons + "\n" + html

    js = """
async function runLocalAction(action){
  try {
    const response = await fetch('http://127.0.0.1:8765/action/' + action, { method: 'POST' });
    const text = await response.text();
    alert(text);
  } catch (e) {
    alert("Serveur local indisponible. Lance Lancer_Dashboard.cmd puis réessaie.\\n\\n" + e);
  }
}

function hardRefreshDashboard(){
  window.location.href = window.location.pathname + '?t=' + Date.now();
}
"""

    if "function runLocalAction" not in html:
        html = html.replace("</script>", js + "\n</script>", 1)

    if "function hardRefreshDashboard" not in html:
        html = html.replace(
            "</script>",
            "\nfunction hardRefreshDashboard(){ window.location.href = window.location.pathname + '?t=' + Date.now(); }\n</script>",
            1,
        )

    if "<meta charset" not in html.lower():
        html = html.replace("<head>", '<head>\n<meta charset="utf-8">', 1)

    return html



def inject_statut_sprint_tooltips(html: str) -> str:
    """Injecte les bulles d'explication du bloc Statut du Sprint."""

    css = r"""
<style id="statutSprintCalcStyle">
.statutCalcBox{
  display:flex;
  flex-wrap:wrap;
  justify-content:center;
  gap:10px;
  margin:12px auto 4px auto;
  max-width:980px;
  font-size:12px;
}
.statutCalcBox .calcPill{
  position:relative;
  border:1px solid #cbd5e1;
  border-radius:10px;
  background:#f8fafc;
  padding:8px 10px;
  min-width:120px;
  text-align:center;
  cursor:help;
}
.statutCalcBox .calcPill b{
  display:block;
  color:#334155;
  font-size:11px;
}
.statutCalcBox .calcPill span{
  display:block;
  color:#0f172a;
  font-weight:800;
  font-size:15px;
  margin-top:2px;
}
.statutCalcBox .calcPill:hover::after{
  content:attr(data-tip);
  position:absolute;
  left:50%;
  bottom:calc(100% + 8px);
  transform:translateX(-50%);
  width:280px;
  background:#111827;
  color:white;
  padding:10px;
  border-radius:8px;
  box-shadow:0 8px 20px rgba(0,0,0,.25);
  z-index:9999;
  white-space:normal;
  line-height:1.35;
  text-align:left;
}
.statutCalcBox .calcPill:hover::before{
  content:"";
  position:absolute;
  left:50%;
  bottom:100%;
  transform:translateX(-50%);
  border:8px solid transparent;
  border-top-color:#111827;
  z-index:9999;
}
.statutCalcFormula{
  width:100%;
  text-align:center;
  color:#475569;
  font-size:12px;
  margin-top:4px;
}
</style>
"""

    js = r"""
<script id="statutSprintCalcTooltipScript">
(function(){
  function esc(v){
    return String(v ?? '').replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function readCalc(data){
    data = data || {};
    const k = data.kpis || {};
    const t = data.tendanceHebdo || {};
    const rows = t.rows || [];
    const current = t.current || rows[rows.length - 1] || {};
    const c = data.statutSprintCalcul || {};

    const totalFlux = c.totalFlux ?? k.flux ?? k.total ?? current.flux ?? current.total ?? 0;
    const fluxPrets = c.fluxPrets ?? k.pretTester ?? k.prets ?? current.pretTester ?? current.prets ?? 0;
    const bugsBloquants = c.bugsBloquants ?? k.bugsBloquants ?? current.bugsBloquants ?? 0;

    const scoreBrut = c.scoreBrut ?? Math.round(totalFlux ? fluxPrets / totalFlux * 100 : 100);
    const penalite = c.penalite ?? Math.min(35, Number(bugsBloquants || 0) * 3);
    const scoreFinal = c.scoreFinal ?? Math.max(0, Math.min(100, Math.round(scoreBrut - penalite)));
    const niveau = c.niveau ?? (scoreFinal >= 80 ? 'Vert' : scoreFinal >= 60 ? 'Orange' : 'Rouge');

    return {totalFlux, fluxPrets, bugsBloquants, scoreBrut, penalite, scoreFinal, niveau};
  }

  function findStatutSection(){
    const sections = Array.from(document.querySelectorAll('section'));
    return sections.find(function(s){
      const h = s.querySelector('h2');
      return h && /Statut du Sprint/i.test(h.textContent || '');
    });
  }

  function decorateStatutSprintTooltips(){
    let data;
    try { data = currentData || fallbackData; } catch(e) { data = null; }
    if (!data) return;

    const c = readCalc(data);
    const section = findStatutSection();
    if (!section) return;

    let box = section.querySelector('.statutCalcBox');
    if (!box) {
      box = document.createElement('div');
      box.className = 'statutCalcBox';
      section.appendChild(box);
    }

    box.innerHTML =
      '<div class="calcPill" title="Nombre total de flux suivis dans le sprint, hors lignes purement anomalies." data-tip="Total flux : nombre de flux suivis pour le sprint. Les anomalies servent à la pénalité mais ne sont pas comptées comme flux prêts."><b>Total flux</b><span>'+esc(c.totalFlux)+'</span></div>' +
      '<div class="calcPill" title="Flux considérés prêts pour arrimage." data-tip="Flux prêts : nombre de flux dont le statut est prêt, livré ou prêt pour arrimage selon la source préparée."><b>Flux prêts</b><span>'+esc(c.fluxPrets)+'</span></div>' +
      '<div class="calcPill" title="Score brut = flux prêts / total flux × 100." data-tip="Score brut : round(flux prêts / total flux × 100). Exemple : 16 / 18 = 88,89 %, arrondi à 89 %."><b>Score brut</b><span>'+esc(c.scoreBrut)+'%</span></div>' +
      '<div class="calcPill" title="Bugs bloquants utilisés pour appliquer la pénalité historique." data-tip="Bugs bloquants : nombre d’anomalies bloquantes prises en compte par la règle historique. Chaque bug bloquant enlève 3 points."><b>Bugs bloquants</b><span>'+esc(c.bugsBloquants)+'</span></div>' +
      '<div class="calcPill" title="Pénalité = min(35, bugs bloquants × 3)." data-tip="Pénalité : min(35, bugs bloquants × 3). Le plafond de 35 évite qu’une volumétrie élevée d’anomalies fasse tomber le score de façon illimitée."><b>Pénalité</b><span>-'+esc(c.penalite)+' pts</span></div>' +
      '<div class="calcPill" title="Score final affiché par la jauge." data-tip="Score final : score brut - pénalité. C’est cette valeur qui pilote la jauge et le niveau Rouge, Orange ou Vert."><b>Score final</b><span>'+esc(c.scoreFinal)+'% '+esc(c.niveau)+'</span></div>' +
      '<div class="statutCalcFormula">Méthode : score final = round(flux prêts / total flux × 100) - min(35, bugs bloquants × 3). Seuils : Rouge 0–59 %, Orange 60–79 %, Vert 80–100 %.</div>';
  }

  const previousRender = (typeof render === 'function') ? render : null;
  if (previousRender && !previousRender.__statutCalcWrapped) {
    const wrapped = function(data){
      previousRender(data);
      setTimeout(decorateStatutSprintTooltips, 0);
    };
    wrapped.__statutCalcWrapped = true;
    render = wrapped;
  }

  window.addEventListener('load', function(){
    setTimeout(decorateStatutSprintTooltips, 150);
  });

  window.decorateStatutSprintTooltips = decorateStatutSprintTooltips;
})();
</script>
"""

    if "statutSprintCalcStyle" not in html:
        html = html.replace("</head>", css + "\n</head>", 1) if "</head>" in html else css + "\n" + html

    if "statutSprintCalcTooltipScript" not in html:
        html = html.replace("</body>", js + "\n</body>", 1) if "</body>" in html else html + "\n" + js

    return html






def remove_dynamic_sprint_label_script(html: str) -> str:
    """Retire l'ancien script JS qui remplaçait les libellés côté navigateur.

    On ne veut plus de remplacement JS générique "Sprint courant".
    Les noms de sprint doivent venir du payload Python publié.
    """

    return re.sub(
        r'\n?<script id="dynamicSprintLabelsScript">[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )


def remove_dynamic_sprint_label_script(html: str) -> str:
    """Retire l'ancien script JS qui remplaçait les libellés par 'Sprint courant'."""

    return re.sub(
        r'\n?<script id="dynamicSprintLabelsScript">[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )


def inject_stable_fallback_loader(html: str) -> str:
    """Force le dashboard à se rendre depuis fallbackData après F5.

    Objectif :
    - ne plus dépendre d'un fetch externe ;
    - éviter page vide après Ctrl+F5 ;
    - garder le rendu legacy stable.
    """

    js = r"""
<script id="stableFallbackLoader">
(function(){
  function renderFromFallback(){
    try {
      if (typeof fallbackData === 'undefined') {
        console.error('[GIL] fallbackData indisponible');
        return;
      }
      if (typeof render !== 'function') {
        console.error('[GIL] fonction render indisponible');
        return;
      }
      currentData = fallbackData;
      render(currentData);
    } catch(e) {
      console.error('[GIL] rendu fallbackData en erreur', e);
    }
  }

  window.loadData = async function(){
    renderFromFallback();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function(){
      setTimeout(renderFromFallback, 0);
    });
  } else {
    setTimeout(renderFromFallback, 0);
  }

  window.__gilRenderFromFallback = renderFromFallback;
})();
</script>
"""

    html = re.sub(
        r'\n?<script id="stableFallbackLoader">[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )

    if "</body>" in html:
        return html.replace("</body>", js + "\n</body>", 1)

    return html + "\n" + js

def replace_fallback_data(html: str, payload: dict) -> str:
    payload = apply_sprint_context(payload)
    payload = enrich_score_detail(payload)
    payload = apply_sprint_comparison_from_jira(payload)
    clean_json = json_for_script(payload)

    new_block = "const fallbackData = " + clean_json + ";\nlet currentData = fallbackData;"

    html2, count = re.subn(
        r"const fallbackData\s*=\s*[\s\S]*?;\s*let currentData\s*=\s*fallbackData\s*;",
        new_block,
        html,
        flags=re.S,
    )

    if count == 0:
        stop("Impossible de remplacer fallbackData dans dashboard_gil.html")

    return html2


def verify_html(html: str, payload: dict) -> None:
    if "fetch('rapport_gil_v6_data.json'" in html or 'fetch("rapport_gil_v6_data.json' in html:
        stop("Le HTML contient encore un fetch actif vers rapport_gil_v6_data.json")

    if "function runLocalAction" not in html:
        stop("runLocalAction absent après publication")

    if "const fallbackData" not in html:
        stop("fallbackData absent après publication")

    if "stableFallbackLoader" not in html:
        stop("stableFallbackLoader absent après publication")

    if "dynamicSprintLabelsScript" in html:
        stop("Ancien dynamicSprintLabelsScript encore présent")

    print("[OK] Publication JIRA stable.")


def main() -> None:
    print("=== PUBLICATION JIRA -> HTML LEGACY STABLE ===")

    if not JIRA_SOURCE.exists():
        stop(f"Source JIRA absente : {JIRA_SOURCE}")

    if not GENERATOR.exists():
        stop(f"Générateur legacy absent : {GENERATOR}")

    if not HTML.exists():
        stop(f"HTML legacy absent : {HTML}")

    rows = load_rows(JIRA_SOURCE)
    if not rows:
        stop("Source JIRA vide : aucun flux à publier")

    payload = build_payload(rows)

    print("[1/4] Copie JIRA vers commun/dashboard_gil_data.json")
    shutil.copy2(JIRA_SOURCE, COMMUN_SOURCE)

    print("[2/4] Génération HTML legacy")
    run([sys.executable, "generer_dashboard_gil_classique.py"], ROOT)

    print("[3/4] Réinjection fallbackData propre + désactivation JSON externe")
    html = read_text(HTML)
    html = disable_external_json_load(html)
    html = inject_buttons_and_js(html)
    html = replace_fallback_data(html, payload)
    html = inject_statut_sprint_tooltips(html)
    html = remove_dynamic_sprint_label_script(html)
    html = remove_dynamic_sprint_label_script(html)
    html = inject_stable_fallback_loader(html)
    html = inject_build_stamp(html)
    html = inject_auto_reload_after_actions(html)
    write_text(HTML, html)

    # Fichier canonique générique.
    # Le nom du fichier ne doit pas porter le numéro du sprint.
    GENERIC_HTML = HTML.with_name("dashboard_gil.html")
    LEGACY_HTML = HTML.with_name("dashboard_gil_sprint21.html")
    write_text(GENERIC_HTML, html)
    write_text(LEGACY_HTML, html)

    print("[4/4] Contrôle")
    html2 = read_text(HTML)
    verify_html(html2, payload)

    print("[OK] Publication JIRA stable.")
    print("Flux :", payload["kpis"]["total"])
    print("Prêts :", payload["kpis"]["prets"])
    print("Taux :", str(payload["kpis"]["taux"]) + "%")
    print("HTML legacy :", HTML)
    print("HTML générique :", GENERIC_HTML)
    print("HTML legacy    :", LEGACY_HTML)


if __name__ == "__main__":
    main()
