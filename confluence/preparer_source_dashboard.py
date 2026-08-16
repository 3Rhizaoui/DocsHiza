#!/usr/bin/env python3
"""Convertit le JSON Confluence brut en source stable pour le dashboard GIL.

Le convertisseur accepte aussi le texte copié depuis une console, dans lequel
les URL peuvent avoir perdu leurs guillemets. Il ne crée jamais un
environnement « Synthèse » : une ligne sans environnement reste
« Non précisé ».
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "confluence_brut.json"
DEFAULT_OUTPUT = ROOT / "dashboard_gil_data.json"


def clean(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def ascii_key(value):
    text = unicodedata.normalize("NFKD", clean(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.upper()


def repair_mojibake(value):
    if isinstance(value, dict):
        return {k: repair_mojibake(v) for k, v in value.items()}
    if isinstance(value, list):
        return [repair_mojibake(v) for v in value]
    if isinstance(value, str) and any(x in value for x in ("Ã", "Â", "â€")):
        try:
            return value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
    return value


def load_json(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    try:
        return repair_mojibake(json.loads(text))
    except json.JSONDecodeError:
        # Répare le format d'affichage copié : "url": https://...,
        fixed = re.sub(
            r'("url"\s*:\s*)(https?://[^,\r\n]+)(\s*,)',
            lambda m: m.group(1) + json.dumps(m.group(2).strip()) + m.group(3),
            text,
        )
        # Répare également les URL brutes placées dans un tableau, notamment
        # les liens JIRA de la forme: [ https://... ].
        fixed = re.sub(
            r'(?m)^(\s*)(https?://[^,\s\]]+)(\s*,?\s*)$',
            lambda m: m.group(1) + json.dumps(m.group(2).strip())
            + ("," if "," in m.group(3) else ""),
            fixed,
        )
        return repair_mojibake(json.loads(fixed))


def values(block):
    if not isinstance(block, dict):
        return clean(block), []
    return clean(block.get("valeur")), [clean(x) for x in block.get("statuts", [])]


def primary_status(block, default="Non renseigné"):
    text, statuses = values(block)
    probe = ascii_key(" ".join(statuses) + " " + text)
    priority = (
        ("TEST KO", "KO"), ("REFUS", "Refusé"), ("EN COURS", "En cours"),
        ("EN ATTENTE", "En attente"), ("A FAIRE", "À faire"),
        ("TEST OK", "Test OK"), ("DEPLOYE", "Déployé"),
        ("LIVRE", "Livré"), ("VALIDE", "Validé"),
        ("NON APPLICABLE", "Non applicable"),
    )
    return next((label for token, label in priority if token in probe), default)


def is_separator(row):
    ref = ascii_key(row.get("reference_flux"))
    sub = ascii_key(row.get("sous_domaine"))
    description = ascii_key(row.get("description"))
    return bool(ref and ref == sub and (not description or description == ref))


def anomaly_refs(row):
    refs = list((row.get("anomalies") or {}).get("references") or [])
    probe = " ".join(clean((row.get(name) or {}).get("valeur")) for name in (
        "test_gil", "test_connectivite", "test_integration", "anomalies"
    ))
    refs += re.findall(r"\b(?:AERL|OCT|JIRA|INC|DEFECT)[-_ ][A-Z0-9_-]+\b|\b\d{5,8}\b", probe, re.I)
    return list(dict.fromkeys(clean(x) for x in refs if clean(x)))


def convert(raw):
    normalized = []
    seen = set()
    anomalies = []
    for row in raw.get("flux", []):
        if is_separator(row):
            continue
        ref = clean(row.get("reference_flux"))
        if not ref:
            continue
        domain = clean(row.get("domaine")) or "Non déterminé"
        sub = clean(row.get("sous_domaine")) or "Non déterminé"
        envs = [ascii_key(x) for x in row.get("environnements_detectes", [])]
        envs = [x for x in envs if x in {"SIT", "UAT", "QUA"}] or ["Non précisé"]
        avro_status = primary_status(row.get("avro"))
        config_status = primary_status(row.get("configuration"))
        test_status = primary_status(row.get("test_gil"))
        avro_value, _ = values(row.get("avro"))
        flow_type = "API" if "NON APPLICABLE" in ascii_key(avro_value) else "Event"
        versions = list(dict.fromkeys(
            list((row.get("avro") or {}).get("versions") or []) +
            list((row.get("configuration") or {}).get("versions") or [])
        ))
        refs = anomaly_refs(row)
        combined = ascii_key(" ".join(
            clean((row.get(k) or {}).get("valeur")) for k in
            ("test_gil", "test_connectivite", "test_integration", "anomalies")
        ))
        resolved = any(x in combined for x in ("TERMINE", "RESOLU", "CLOS", "VALIDE"))
        blocking = "TEST KO" in combined
        for env in envs:
            identity = (domain, sub, ref, env)
            if identity in seen:
                continue
            seen.add(identity)
            item = {
                "domaine": domain, "sous_domaine": sub, "reference_flux": ref,
                "description": clean(row.get("description")),
                "demandeur": clean(row.get("demandeur")),
                "partenaire": "ESTREEM" if domain == "Issuing" else "BCEF",
                "environnement": env, "type_flux": flow_type,
                "versions": versions, "statut_avro": avro_status,
                "statut_configuration": config_status, "statut_test": test_status,
                "avro_livre": avro_status in {"Livré", "Non applicable"},
                "configuration_deployee": config_status == "Déployé",
                "pret_arrimage": config_status == "Déployé" and test_status == "Test OK",
                "anomalies": refs, "source": row.get("source", {}),
            }
            normalized.append(item)
            for anomaly_ref in refs:
                anomalies.append({
                    "reference": anomaly_ref, "flux": ref, "domaine": domain,
                    "sous_domaine": sub, "environnement": env,
                    "statut": "Résolue" if resolved else "En cours",
                    "bloquante": blocking, "responsable": item["partenaire"],
                    "severite": "Bloquante" if blocking else "Non renseignée",
                })

    groups = defaultdict(lambda: {"total": 0, "avro_livres": 0, "configurations_deployees": 0,
                                  "prets_arrimage": 0, "anomalies": 0, "bugs_bloquants": 0})
    for item in normalized:
        group = groups[(item["domaine"], item["sous_domaine"], item["environnement"])]
        group["total"] += 1
        group["avro_livres"] += int(item["avro_livre"])
        group["configurations_deployees"] += int(item["configuration_deployee"])
        group["prets_arrimage"] += int(item["pret_arrimage"])
    for anomaly in anomalies:
        group = groups[(anomaly["domaine"], anomaly["sous_domaine"], anomaly["environnement"])]
        group["anomalies"] += 1
        group["bugs_bloquants"] += int(anomaly["bloquante"] and anomaly["statut"] != "Résolue")
    grouped = [{"domaine": k[0], "sous_domaine": k[1], "environnement": k[2], **v}
               for k, v in sorted(groups.items())]
    total = len(normalized)
    deployed = sum(x["configuration_deployee"] for x in normalized)
    blocking = sum(x["bloquante"] and x["statut"] != "Résolue" for x in anomalies)
    # La santé ne pénalise que les bugs bloquants, conformément à la règle GIL.
    health = round(max(0, deployed - blocking) * 100 / total) if total else 0
    generated_at = raw.get("generated_at") or datetime.now().astimezone().isoformat()
    try:
        generated_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        generated_dt = datetime.now().astimezone()
    iso_year, iso_week, _ = generated_dt.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    sprint_label = str(raw.get("sprint") or raw.get("sprintCourant") or f"Semaine {week_label}")

    # Compatibilité avec le générateur HTML historique. Le JSON normalisé reste
    # la source principale, tandis que `records` permet au dashboard existant
    # d'être recalculé sans ressaisie ni fichier Excel.
    records = []
    anomaly_by_flow_env = defaultdict(list)
    for anomaly in anomalies:
        anomaly_by_flow_env[(anomaly["flux"], anomaly["environnement"])].append(anomaly)
    for item in normalized:
        related = anomaly_by_flow_env[(item["reference_flux"], item["environnement"])]
        has_open_blocker = any(a["bloquante"] and a["statut"] != "Résolue" for a in related)
        source = item.get("source") or {}
        records.append({
            "id": item["reference_flux"],
            "reference": item["reference_flux"],
            "type": "AVRO" if item["type_flux"] == "Event" else "Configuration",
            "domaine": item["domaine"],
            "sousDomaine": item["sous_domaine"],
            "environnement": item["environnement"],
            "semaine": week_label,
            "sprint": sprint_label,
            "etatFlux": "Prêt" if item["pret_arrimage"] else "En cours",
            "etatAnomalie": "KO" if has_open_blocker else "",
            "statut": "Livré" if item["configuration_deployee"] else item["statut_configuration"],
            "version": " / ".join(item["versions"]),
            "nombre": 1,
            "commentaire": item["description"],
            "source": item["partenaire"],
            "date": generated_dt.date().isoformat(),
            "nature": "Confluence",
            "url_source": source.get("url", "") if isinstance(source, dict) else "",
        })
    for anomaly in anomalies:
        records.append({
            "id": anomaly["flux"], "reference": anomaly["reference"],
            "type": "Anomalie", "domaine": anomaly["domaine"],
            "sousDomaine": anomaly["sous_domaine"],
            "environnement": anomaly["environnement"], "semaine": week_label,
            "sprint": sprint_label, "etatFlux": "",
            "etatAnomalie": "Corrigée" if anomaly["statut"] == "Résolue" else "KO",
            "statut": anomaly["statut"], "version": "", "nombre": 1,
            "commentaire": f"{anomaly['responsable']} — {anomaly['severite']}",
            "source": anomaly["responsable"], "date": generated_dt.date().isoformat(),
            "severite": anomaly["severite"], "responsable": anomaly["responsable"],
            "nature": "Confluence",
        })

    return {
        "schema_version": "2.0-dashboard",
        "generated_at": generated_at,
        "source_type": raw.get("source_type", "confluence"),
        "pages": raw.get("pages", []),
        "indicateurs": {
            "flux_total": total,
            "avro_livres": sum(x["avro_livre"] for x in normalized),
            "configurations_deployees": deployed,
            "flux_prets_arrimage": sum(x["pret_arrimage"] for x in normalized),
            "anomalies_total": len(anomalies),
            "bugs_bloquants_ouverts": blocking,
            "sante_pourcent": health,
        },
        "groupes": grouped,
        "flux": normalized,
        "anomalies": anomalies,
        "records": records,
        "erreurs_source": raw.get("erreurs", []),
    }


def main():
    parser = argparse.ArgumentParser(description="Prépare la source JSON du dashboard GIL")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = convert(load_json(args.input))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Source dashboard produite : {args.output}")
    print(f"Flux : {len(result['flux'])} | Anomalies : {len(result['anomalies'])} | Santé : {result['indicateurs']['sante_pourcent']}%")


if __name__ == "__main__":
    main()
