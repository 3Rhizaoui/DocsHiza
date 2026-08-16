from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
ARCHIVES = PROJECT / "archives_sprints"
INDEX = ARCHIVES / "index_sprints.json"
DATA = ROOT / "dashboard_gil_data.json"
PAYLOAD = ROOT / "rapport_gil_v6_w28_data.json"
HTML = ROOT / "dashboard_gil.html"
LEGACY_HTML = ROOT / "dashboard_gil_sprint21.html"
VERSION_CALCUL = "dynamic-v1"


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "Sprint_non_defini")).strip("_")
    return value or "Sprint_non_defini"


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT, text=True).strip()
    except Exception:
        return ""


def next_revision(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    existing = [p for p in folder.iterdir() if p.is_dir() and re.match(r"rev\d{3}$", p.name)]
    numbers = [int(p.name[3:]) for p in existing]
    return folder / f"rev{(max(numbers) + 1) if numbers else 1:03d}"


def main():
    if not DATA.exists():
        raise SystemExit("Aucune donnée à archiver : commun/dashboard_gil_data.json est absent.")
    if not PAYLOAD.exists():
        # Génère le payload si nécessaire.
        import generer_dashboard_gil_classique  # noqa: F401
    payload = read_json(PAYLOAD, {}) or {}
    sprint = str(payload.get("sprintCourant") or "Sprint non défini")
    sprint_dir = ARCHIVES / safe_name(sprint)
    rev_dir = next_revision(sprint_dir)
    rev_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(DATA, rev_dir / "dashboard_gil_data.json")
    if PAYLOAD.exists():
        shutil.copy2(PAYLOAD, rev_dir / "metriques_sprint.json")
    source_html = HTML if HTML.exists() else LEGACY_HTML
    if source_html.exists():
        shutil.copy2(source_html, rev_dir / "dashboard.html")
    metadata = {
        "sprint": sprint,
        "semaines": payload.get("semainesSprint") or [],
        "date_validation": datetime.now().astimezone().isoformat(timespec="seconds"),
        "statut": "VALIDE",
        "version_calcul": payload.get("versionCalcul") or VERSION_CALCUL,
        "sources_utilisees": (read_json(DATA, {}) or {}).get("sources_utilisees") or [],
        "commentaire_validation": "Archive manuelle depuis Archiver_Sprint.cmd",
        "commit_git": git_commit(),
        "archive_dir": str(rev_dir.relative_to(PROJECT)).replace("\\", "/"),
        "data_path": str((rev_dir / "dashboard_gil_data.json").relative_to(PROJECT)).replace("\\", "/"),
    }
    write_json(rev_dir / "metadata.json", metadata)
    index = read_json(INDEX, {"archives": []}) or {"archives": []}
    archives = index.get("archives") or []
    archives.append(metadata)
    index["archives"] = archives
    index["last_validated"] = metadata
    write_json(INDEX, index)
    print(f"Sprint archivé : {sprint}")
    print(f"Révision : {rev_dir.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
