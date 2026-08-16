from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
REQUIRED = [
    PROJECT / "Lancer_Dashboard.cmd",
    PROJECT / "Synchroniser_Tout.cmd",
    PROJECT / "Archiver_Sprint.cmd",
    PROJECT / "Verifier_Dashboard.cmd",
    ROOT / "fusionner_sources.py",
    ROOT / "archiver_sprint.py",
    ROOT / "serveur_dashboard.py",
    ROOT / "generer_dashboard_gil_classique.py",
]
PY_FILES = [
    ROOT / "fusionner_sources.py",
    ROOT / "archiver_sprint.py",
    ROOT / "serveur_dashboard.py",
    ROOT / "generer_dashboard_gil_classique.py",
]
LABELS = ["Importer Excel", "Importer Confluence", "Importer JIRA", "Synchroniser les 3", "Valider / Archiver Sprint"]


def ok(msg): print("[OK]", msg)
def ko(msg): print("[KO]", msg)


def main():
    errors = 0
    for path in REQUIRED:
        if path.exists(): ok(str(path.relative_to(PROJECT)))
        else: errors += 1; ko(f"manquant : {path.relative_to(PROJECT)}")
    for path in PY_FILES:
        try:
            py_compile.compile(str(path), doraise=True)
            ok(f"syntaxe Python : {path.relative_to(PROJECT)}")
        except Exception as exc:
            errors += 1; ko(f"syntaxe Python : {path.relative_to(PROJECT)} : {exc}")
    for path in [ROOT / "dashboard_gil_data.json", ROOT / "rapport_gil_v6_w28_data.json"]:
        if path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8-sig"))
                ok(f"JSON valide : {path.relative_to(PROJECT)}")
            except Exception as exc:
                errors += 1; ko(f"JSON invalide : {path.relative_to(PROJECT)} : {exc}")
    html_path = ROOT / "dashboard_gil.html"
    if not html_path.exists():
        html_path = ROOT / "dashboard_gil_sprint21.html"
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        missing = [label for label in LABELS if label not in html]
        if missing:
            errors += 1; ko("boutons manquants : " + ", ".join(missing))
        else:
            ok("boutons dashboard présents")
    data_path = ROOT / "rapport_gil_v6_w28_data.json"
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8-sig"))
        for row in data.get("comparaisonSprints") or []:
            total = int(row.get("fluxTotal") or 0)
            parts = int(row.get("fluxLivresTotal") or 0) + int(row.get("fluxEnCoursTotal") or 0) + int(row.get("fluxBloquesTotal") or 0)
            if total != parts:
                errors += 1; ko(f"cohérence {row.get('sprint')}: total={total}, détails={parts}")
            else:
                ok(f"cohérence métriques : {row.get('sprint')}")
    if errors:
        raise SystemExit(f"{errors} erreur(s) détectée(s)")
    print("Vérification terminée avec succès.")


if __name__ == "__main__":
    main()
