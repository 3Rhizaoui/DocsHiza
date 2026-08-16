from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
SOURCES = PROJECT / "sources"
OUT = ROOT / "dashboard_gil_data.json"
REPORT = ROOT / "rapport_fusion_sources.json"
PRIORITY = {"excel": 1, "confluence": 2, "jira": 3}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_payload(data: dict, source_name: str) -> list[dict]:
    records = data.get("records") or []
    if records:
        out = []
        for r in records:
            item = dict(r)
            item.setdefault("source_system", source_name)
            item.setdefault("source", source_name)
            out.append(item)
        return out
    # Compatibilité avec les JSON normalisés Confluence/Jira qui exposent flux + anomalies.
    generated = str(data.get("generated_at") or data.get("generatedAt") or datetime.now().astimezone().isoformat())
    week = str(data.get("semaine") or data.get("semaineCourante") or "")
    if not week:
        try:
            dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now().astimezone()
        y, w, _ = dt.isocalendar()
        week = f"{y}-W{w:02d}"
    sprint = str(data.get("sprint") or data.get("sprintCourant") or f"Semaine {week}")
    out = []
    for f in data.get("flux") or []:
        ref = str(f.get("reference_flux") or f.get("reference") or f.get("id") or "")
        env = str(f.get("environnement") or "").upper()
        versions = f.get("versions") or []
        if isinstance(versions, str):
            versions = [versions]
        out.append({
            "id": ref,
            "reference": ref,
            "type": "AVRO" if str(f.get("type_flux") or "").casefold() == "event" else "Configuration",
            "domaine": f.get("domaine") or "Non renseigné",
            "sousDomaine": f.get("sous_domaine") or f.get("sousDomaine") or "Non renseigné",
            "environnement": env,
            "semaine": f.get("semaine") or week,
            "sprint": f.get("sprint") or sprint,
            "etatFlux": "Prêt" if f.get("pret_arrimage") else "En cours",
            "etatAnomalie": "",
            "statut": "Livré" if f.get("configuration_deployee") else str(f.get("statut_configuration") or ""),
            "version": " / ".join(map(str, versions)),
            "nombre": 1,
            "commentaire": f.get("description") or "",
            "source": source_name,
            "source_system": source_name,
            "date": generated[:10],
            "nature": source_name,
            "url_source": (f.get("source") or {}).get("url", "") if isinstance(f.get("source"), dict) else "",
        })
    for a in data.get("anomalies") or []:
        out.append({
            "id": a.get("flux") or a.get("reference") or "",
            "reference": a.get("reference") or "",
            "type": "Anomalie",
            "domaine": a.get("domaine") or "Non renseigné",
            "sousDomaine": a.get("sous_domaine") or a.get("sousDomaine") or "Non renseigné",
            "environnement": str(a.get("environnement") or "").upper(),
            "semaine": a.get("semaine") or week,
            "sprint": a.get("sprint") or sprint,
            "etatFlux": "",
            "etatAnomalie": "KO" if str(a.get("statut") or "").casefold() not in {"résolue", "resolue", "done", "clos"} else "Corrigée",
            "statut": a.get("statut") or "",
            "version": "",
            "nombre": 1,
            "commentaire": a.get("description") or a.get("resume") or "",
            "source": source_name,
            "source_system": source_name,
            "date": generated[:10],
            "nature": source_name,
            "severite": a.get("severite") or "",
        })
    return out


def logical_key(record: dict) -> tuple:
    is_anomaly = str(record.get("type") or "") == "Anomalie"
    identity = str(record.get("reference") or record.get("jira_key") or record.get("id") or "").strip().casefold()
    if not identity:
        identity = str(record.get("id") or "").strip().casefold()
    if is_anomaly:
        return ("anomaly", identity, str(record.get("environnement") or "").upper(), str(record.get("sprint") or record.get("semaine") or ""))
    return (
        "flow",
        identity,
        str(record.get("environnement") or "").upper(),
        str(record.get("sprint") or ""),
        str(record.get("semaine") or ""),
    )


def main():
    candidates = [
        ("excel", SOURCES / "excel.json", PROJECT / "excel" / "dashboard_gil_data.json"),
        ("confluence", SOURCES / "confluence.json", PROJECT / "confluence" / "dashboard_gil_data.json"),
        ("jira", SOURCES / "jira.json", PROJECT / "jira" / "dashboard_gil_data.json"),
    ]
    all_records = []
    source_counts = Counter()
    used_files = []
    for source, primary, fallback in candidates:
        path = primary if primary.exists() else fallback
        if not path.exists():
            continue
        data = read_json(path)
        records = normalize_payload(data, source)
        for r in records:
            r["source_system"] = source
        source_counts[source] += len(records)
        used_files.append(str(path.relative_to(PROJECT)))
        all_records.extend(records)
    selected = {}
    duplicates = []
    for rec in all_records:
        key = logical_key(rec)
        old = selected.get(key)
        if old is None:
            selected[key] = rec
            continue
        duplicates.append({"key": "|".join(map(str, key)), "kept": rec.get("source_system"), "replaced": old.get("source_system")})
        if PRIORITY.get(str(rec.get("source_system")), 0) >= PRIORITY.get(str(old.get("source_system")), 0):
            selected[key] = rec
    merged = list(selected.values())
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_type": "multisources",
        "sources_utilisees": used_files,
        "records": merged,
    }
    write_json(OUT, payload)
    write_json(REPORT, {
        "generatedAt": payload["generatedAt"],
        "sources": dict(source_counts),
        "fichiers": used_files,
        "lignes_entree": len(all_records),
        "lignes_sortie": len(merged),
        "doublons": duplicates,
    })
    print(f"Fusion OK : {len(merged)} lignes dans {OUT.relative_to(PROJECT)}")
    print(f"Rapport : {REPORT.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
