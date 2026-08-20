from pathlib import Path
import datetime as dt
import json
import re

ROOT = Path(__file__).resolve().parents[1]
JIRA = ROOT / "jira"

PREV = JIRA / "sprints" / "sprint_precedent.json"
CUR = JIRA / "sprints" / "sprint_courant.json"
OUT = JIRA / "presentation" / "comparaison_sprints.json"
OUT_ALIAS = JIRA / "comparaison_sprints.json"


def load(path: Path):
    if not path.exists():
        raise SystemExit(f"[ERREUR] Fichier absent : {path}")
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(text(x) for x in value)
    if isinstance(value, dict):
        return " ".join(text(x) for x in value.values())
    return str(value)


def to_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def first_int(*values, default=0):
    for value in values:
        try:
            if value not in (None, ""):
                return int(value)
        except Exception:
            pass
    return default


def excel_serial(day: dt.date) -> int:
    return (day - dt.date(1899, 12, 30)).days


def iso_week(day: dt.date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def sprint_name(doc, fallback):
    sprint = doc.get("sprint") or {}
    return (
        sprint.get("nom")
        or sprint.get("name")
        or doc.get("nom")
        or doc.get("name")
        or fallback
    )


def official_total(doc):
    stats = doc.get("statistiques") or {}
    return first_int(
        stats.get("total"),
        stats.get("flux"),
        doc.get("total"),
        doc.get("flux"),
        default=0,
    )


def extract_tickets(doc):
    raw = None
    for key in ["tickets", "issues", "flux", "items"]:
        if isinstance(doc.get(key), list):
            raw = doc.get(key)
            break

    if not raw:
        return []

    result = []
    seen = set()

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue

        key = (
            item.get("key")
            or item.get("jiraKey")
            or item.get("id")
            or item.get("reference")
            or f"NO_KEY_{index}_{item.get('summary') or item.get('resume') or ''}"
        )

        key = str(key)
        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def blob(ticket):
    return text(ticket).lower()


def ticket_key(ticket):
    return str(ticket.get("key") or ticket.get("jiraKey") or ticket.get("reference") or "")


def ticket_summary(ticket):
    return str(ticket.get("summary") or ticket.get("resume") or ticket_key(ticket) or "Ticket Jira")


def ticket_status(ticket):
    return str(ticket.get("status") or ticket.get("statut") or ticket.get("statutJira") or "")


def ticket_url(ticket):
    return str(ticket.get("url") or "")


def ticket_assignee(ticket):
    return str(ticket.get("assignee") or ticket.get("responsable") or ticket.get("reporter") or "")


def detect_env(ticket):
    b = blob(ticket)

    if "uat" in b and "sit" not in b:
        return "UAT"

    if "sit" in b:
        return "SIT"

    # Le template historique agrège SIT/UAT.
    # Si l'environnement est absent, on classe en SIT mais on garde un indicateur nonVentile.
    return "SIT"


def detect_domain(ticket):
    b = blob(ticket)

    if "acquisition" in b:
        return "Acquisition"
    if "issuing" in b:
        return "Issuing"
    if "ged" in b:
        return "Issuing"
    if "authorize" in b or "autho" in b:
        return "Issuing"

    return "Non renseigné"


def detect_subdomain(ticket):
    b = blob(ticket)

    if "onboarding" in b:
        return "Onboarding"
    if "authorize" in b or "authorization" in b:
        return "Authorize"
    if "paiement" in b or "payment" in b:
        return "Authorize / Paiement"
    if "contestation" in b:
        return "Contestation"
    if "ged" in b:
        return "GED"
    if "crédit commerçant" in b or "credit commercant" in b:
        return "Crédit commerçant"

    return "Non renseigné"


def is_blocked(ticket):
    b = blob(ticket)
    return any(x in b for x in ["bloqué", "bloque", "blocked", "ko", "rejeté", "rejete", "rejected"])


def is_delivered(ticket):
    b = blob(ticket)
    return any(x in b for x in [
        "done", "terminé", "termine", "livré", "livre",
        "validé", "valide", "résolu", "resolu", "closed", "clos"
    ])


def detail(ticket, sprint, week, statut):
    key = ticket_key(ticket)
    summary = ticket_summary(ticket)

    return {
        "reference": key or summary,
        "flux": key or summary,
        "jiraKey": key,
        "domaine": detect_domain(ticket),
        "sousDomaine": detect_subdomain(ticket),
        "environnement": detect_env(ticket),
        "statut": statut,
        "statutSource": ticket_status(ticket),
        "partenaire": ticket_assignee(ticket),
        "nombre": 1,
        "version": text(ticket.get("fixVersions") or ticket.get("version")),
        "resume": summary,
        "description": str(ticket.get("description") or ""),
        "url": ticket_url(ticket),
        "sprint": sprint,
        "semaine": week,
        "source": "API Agile Jira officielle",
    }


def synthetic_total(sprint, week, count):
    return {
        "reference": "Total Jira Agile",
        "flux": "Tickets du sprint officiel",
        "jiraKey": "",
        "domaine": "Non renseigné",
        "sousDomaine": "Non renseigné",
        "environnement": "SIT",
        "statut": "Total",
        "statutSource": "Total officiel API Agile",
        "partenaire": "",
        "nombre": count,
        "version": "",
        "resume": "Tickets présents dans le sprint officiel Jira",
        "description": "",
        "url": "",
        "sprint": sprint,
        "semaine": week,
        "source": "API Agile Jira officielle",
    }


def health(total, delivered, blocked):
    if total <= 0:
        score = 100
    else:
        score = round((delivered / total) * 100 - min(35, blocked * 3))

    score = max(0, min(100, score))

    if score >= 80:
        return "Vert"
    if score >= 60:
        return "Orange"
    return "Rouge"


def build_row(doc, role, week):
    name = sprint_name(doc, "Sprint précédent" if role == "precedent" else "Sprint courant")
    total = official_total(doc)
    tickets = extract_tickets(doc)

    ignored = 0
    if total and len(tickets) > total:
        ignored = len(tickets) - total
        tickets = tickets[:total]

    total_details = []
    delivered_details = []
    in_progress_details = []
    blocked_details = []

    non_ventile = 0

    for ticket in tickets:
        d_total = detail(ticket, name, week, "Total")
        total_details.append(d_total)

        if detect_domain(ticket) == "Non renseigné" or detect_subdomain(ticket) == "Non renseigné":
            non_ventile += 1

        if is_blocked(ticket):
            blocked_details.append(detail(ticket, name, week, "Bloqué"))
        elif is_delivered(ticket):
            delivered_details.append(detail(ticket, name, week, "Livré"))
        else:
            in_progress_details.append(detail(ticket, name, week, "En cours"))

    if total > len(total_details):
        missing = total - len(total_details)
        total_details.append(synthetic_total(name, week, missing))
        non_ventile += missing

    flux_livres = sum(to_int(x.get("nombre")) for x in delivered_details)
    flux_en_cours = sum(to_int(x.get("nombre")) for x in in_progress_details)
    flux_bloques = sum(to_int(x.get("nombre")) for x in blocked_details)

    return {
        "semaine": week,
        "dateRapport": excel_serial(dt.date.today()),
        "flux": total,
        "pretTester": flux_livres,
        "nonPret": max(0, total - flux_livres),
        "bugsBloquants": flux_bloques,
        "servicesRisque": 0,
        "testsKoBloques": flux_bloques,
        "prioritesTraitees": flux_livres,
        "sante": health(total, flux_livres, flux_bloques),
        "faitMarquant": "Comparaison issue de l’API Agile Jira officielle",
        "risque": f"{max(0, total - flux_livres)} ticket(s) non terminés ou à qualifier",
        "sprint": name,
        "typeDonnee": "Réel Jira Agile",
        "semaines": [week],

        "fluxTotalDetail": total_details,
        "fluxLivresDetail": delivered_details,
        "fluxEnCoursDetail": in_progress_details,
        "fluxBloquesDetail": blocked_details,

        "fluxTotal": total,
        "fluxLivresTotal": flux_livres,
        "fluxEnCoursTotal": flux_en_cours,
        "fluxBloquesTotal": flux_bloques,

        "nonVentile": non_ventile,
        "ticketsPrisEnCompte": len(tickets),
        "ticketsIgnoresPourRespectTotalOfficiel": ignored,
        "source": "API Agile Jira officielle",
    }


def main():
    previous = load(PREV)
    current = load(CUR)

    today = dt.date.today()
    rows = [
        build_row(previous, "precedent", iso_week(today - dt.timedelta(days=7))),
        build_row(current, "courant", iso_week(today)),
    ]

    for doc, row in [(previous, rows[0]), (current, rows[1])]:
        expected = official_total(doc)
        if row["fluxTotal"] != expected:
            raise SystemExit(
                f"[ERREUR] Total comparaison incohérent pour {row['sprint']} : "
                f"{row['fluxTotal']} au lieu de {expected}"
            )

    write(OUT, rows)
    write(OUT_ALIAS, rows)

    print("[OK] Comparaison dashboard compatible HTML produite :")
    print(" -", OUT)

    for row in rows:
        print(
            "-",
            row["sprint"],
            "| total:", row["fluxTotal"],
            "| livrés:", row["fluxLivresTotal"],
            "| en cours:", row["fluxEnCoursTotal"],
            "| bloqués:", row["fluxBloquesTotal"],
            "| nonVentile:", row["nonVentile"],
        )


if __name__ == "__main__":
    main()
