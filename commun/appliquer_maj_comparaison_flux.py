from __future__ import annotations

import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent

PYTHON_FILE = ROOT / "generer_dashboard_gil_classique.py"
HTML_FILE = ROOT / "dashboard_gil.html"


def backup(path: Path):
    backup_path = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup_path)
    print(f"Sauvegarde : {backup_path.name}")


def update_python():
    if not PYTHON_FILE.exists():
        raise SystemExit(
            f"Fichier introuvable : {PYTHON_FILE}"
        )

    backup(PYTHON_FILE)

    content = PYTHON_FILE.read_text(
        encoding="utf-8"
    )

    start = content.find(
        "def sprint_comparison_row("
    )

    if start < 0:
        raise SystemExit(
            "Fonction sprint_comparison_row introuvable."
        )

    end_marker = '\npayload["comparaisonSprints"]'

    end = content.find(
        end_marker,
        start
    )

    if end < 0:
        raise SystemExit(
            'Bloc payload["comparaisonSprints"] introuvable.'
        )

    new_function = r'''def sprint_comparison_row(
    history_row,
    sprint,
    data_type,
    week,
    display_weeks=None
):
    if display_weeks is None:
        display_weeks = (
            current_sprint_weeks
            if sprint == current_sprint
            else previous_sprint_weeks
        )

    sprint_rows = [
        r
        for r in records
        if r["semaine"] == week
    ]

    # ---------------------------------------------------------
    # COMPARAISON DES FLUX / DEMANDES
    #
    # Les anomalies ne sont plus mélangées à ce graphique.
    # Elles restent traitées dans l'histogramme des anomalies.
    # ---------------------------------------------------------

    flow_rows = [
        r
        for r in sprint_rows
        if r.get("type") != "Anomalie"
    ]

    def flow_item(row, label):
        return {
            "reference":
                row.get("reference")
                or row.get("id")
                or "",

            "flux":
                row.get("id")
                or "",

            "jiraKey":
                row.get("jira_key")
                or row.get("epic_key")
                or "",

            "domaine":
                row.get("domaine")
                or "À qualifier",

            "sousDomaine":
                row.get("sousDomaine")
                or "À qualifier",

            "environnement":
                row.get("environnement")
                or "",

            "statut":
                label,

            "statutSource":
                row.get("statut")
                or "",

            "partenaire":
                row.get("responsable")
                or row.get("source")
                or bug_owner(row),

            "nombre":
                int(
                    float(
                        row.get("nombre")
                        or 0
                    )
                ),

            "version":
                row.get("version")
                or "",

            "resume":
                row.get("commentaire")
                or "",

            "description":
                row.get("description")
                or "",

            "url":
                row.get("url_source")
                or "",
        }

    def normalized_status(row):
        raw = " ".join(
            str(
                row.get(key)
                or ""
            )
            for key in (
                "etatFlux",
                "etatAnomalie",
                "statut"
            )
        )

        value = unicodedata.normalize(
            "NFKD",
            raw.casefold()
        )

        return "".join(
            char
            for char in value
            if not unicodedata.combining(char)
        )

    def is_blocked(row):
        status = normalized_status(row)

        blocked_words = (
            "bloqu",
            "rejet",
            "refus",
            "ko",
            "a traiter",
            "non pret",
            "abandon",
            "annul"
        )

        return (
            row.get("etatAnomalie") == "KO"
            or any(
                word in status
                for word in blocked_words
            )
        )

    def is_progress(row):
        # Un flux bloqué/rejeté ne doit pas être
        # compté une deuxième fois comme En cours.
        if is_blocked(row):
            return False

        status = normalized_status(row)

        return (
            row.get("etatFlux") == "En cours"
            or "en cours" in status
            or "progress" in status
        )

    def is_delivered(row):
        # Catégories exclusives :
        # Bloqué > En cours > Livré
        if is_blocked(row):
            return False

        if is_progress(row):
            return False

        status = normalized_status(row)

        return (
            row.get("etatFlux") == "Prêt"
            or "livr" in status
            or "pret" in status
            or "done" in status
        )

    # ---------------------------------------------------------
    # 1 - TOTAL DES FLUX / DEMANDES
    # ---------------------------------------------------------

    total_flows = [
        flow_item(
            row,
            "Total"
        )
        for row in flow_rows
    ]

    # ---------------------------------------------------------
    # 2 - FLUX LIVRÉS
    # ---------------------------------------------------------

    delivered = [
        flow_item(
            row,
            "Livré"
        )
        for row in flow_rows
        if is_delivered(row)
    ]

    # ---------------------------------------------------------
    # 3 - FLUX EN COURS
    # ---------------------------------------------------------

    progress = [
        flow_item(
            row,
            "En cours"
        )
        for row in flow_rows
        if is_progress(row)
    ]

    # ---------------------------------------------------------
    # 4 - FLUX BLOQUÉS / REJETÉS
    # ---------------------------------------------------------

    blocked = [
        flow_item(
            row,
            "Bloqué / Rejeté"
        )
        for row in flow_rows
        if is_blocked(row)
    ]

    return {
        **history_row,

        "sprint":
            sprint,

        "typeDonnee":
            data_type,

        "semaines":
            display_weeks,

        # Détails utilisés par le graphe
        # et le tableau comparatif.
        "fluxTotalDetail":
            total_flows,

        "fluxLivresDetail":
            delivered,

        "fluxEnCoursDetail":
            progress,

        "fluxBloquesDetail":
            blocked,

        # Totaux.
        "fluxTotal":
            sum(
                x["nombre"]
                for x in total_flows
            ),

        "fluxLivresTotal":
            sum(
                x["nombre"]
                for x in delivered
            ),

        "fluxEnCoursTotal":
            sum(
                x["nombre"]
                for x in progress
            ),

        "fluxBloquesTotal":
            sum(
                x["nombre"]
                for x in blocked
            ),
    }
'''

    new_content = (
        content[:start]
        + new_function
        + content[end:]
    )

    PYTHON_FILE.write_text(
        new_content,
        encoding="utf-8"
    )

    print(
        "OK : generer_dashboard_gil_classique.py mis à jour."
    )


def update_html():
    if not HTML_FILE.exists():
        raise SystemExit(
            f"Fichier introuvable : {HTML_FILE}"
        )

    backup(HTML_FILE)

    content = HTML_FILE.read_text(
        encoding="utf-8"
    )

    # =========================================================
    # 1 - TABLEAU COMPARAISON SPRINT
    # =========================================================

    weekly_pattern = re.compile(
        r"document\.getElementById\('weeklyTrend'\)"
        r"\.innerHTML\s*=\s*.*?;\s*\n",
        re.DOTALL
    )

    new_weekly = """document.getElementById('weeklyTrend').innerHTML =
        '<tr>'+
          '<th>Sprint</th>'+
          '<th>Semaines</th>'+
          '<th>Flux / demandes total</th>'+
          '<th>Flux livrés</th>'+
          '<th>Flux en cours</th>'+
          '<th>Flux bloqués / rejetés</th>'+
          '<th>Statut</th>'+
        '</tr>' +

        sprintComparison.map(h =>
          clickableRow(
            [
              link(
                h.sprint,
                'sprintSnapshot',
                h.sprint
              ),

              esc(
                (h.semaines || [])
                .join(' / ')
              ),

              environmentMetricDetails(
                h.fluxTotalDetail || [],
                false
              ),

              environmentMetricDetails(
                h.fluxLivresDetail || [],
                false
              ),

              environmentMetricDetails(
                h.fluxEnCoursDetail || [],
                false
              ),

              environmentMetricDetails(
                h.fluxBloquesDetail || [],
                false
              ),

              '<span class="' +
                cls(
                  healthLevel(
                    healthScore(h)
                  )
                ) +
              '">' +
                esc(
                  healthLevel(
                    healthScore(h)
                  )
                ) +
              '</span>'
            ],
            'sprintSnapshot',
            h.sprint
          )
        ).join('');
"""

    content, count = weekly_pattern.subn(
        new_weekly,
        content,
        count=1
    )

    if count != 1:
        raise SystemExit(
            "Impossible de modifier le tableau weeklyTrend."
        )

    # =========================================================
    # 2 - GRAPHE COMPARAISON SPRINT
    # =========================================================

    metrics_pattern = re.compile(
        r"const metrics\s*=\s*\["
        r"\['fluxLivresDetail'.*?"
        r"\];",
        re.DOTALL
    )

    new_metrics = """const metrics=[
        [
          'fluxTotalDetail',
          '#64748b',
          'Flux / demandes total'
        ],
        [
          'fluxLivresDetail',
          '#15803d',
          'Flux livrés'
        ],
        [
          'fluxEnCoursDetail',
          '#f59e0b',
          'Flux en cours'
        ],
        [
          'fluxBloquesDetail',
          '#b91c1c',
          'Flux bloqués / rejetés'
        ]
      ];"""

    content, count = metrics_pattern.subn(
        new_metrics,
        content,
        count=1
    )

    if count != 1:
        raise SystemExit(
            "Impossible de modifier les séries du graphe Sprint."
        )

    # =========================================================
    # 3 - TEXTE EXPLICATIF DU GRAPHE
    # =========================================================

    content = content.replace(
        "Comparaison des Sprints, barres empilées SIT et UAT",
        "Comparaison des flux par Sprint, barres empilées SIT et UAT"
    )

    old_note = (
        "Survol : domaine, sous-domaine, environnement, "
        "flux, statut et partenaire."
    )

    new_note = (
        "Survol : domaine, sous-domaine, environnement, "
        "flux, statut et partenaire. "
        "Les anomalies sont suivies séparément dans "
        "leur histogramme dédié."
    )

    content = content.replace(
        old_note,
        new_note
    )

    HTML_FILE.write_text(
        content,
        encoding="utf-8"
    )

    print(
        "OK : dashboard_gil.html mis à jour."
    )


def main():
    print()
    print("=" * 65)
    print(" MAJ COMPARAISON SPRINT - FLUX / DEMANDES")
    print("=" * 65)
    print()

    print(
        f"Dossier : {ROOT}"
    )
    print()

    update_python()
    update_html()

    print()
    print("=" * 65)
    print(" MISE A JOUR TERMINEE")
    print("=" * 65)
    print()
    print(
        "Le graphe et le tableau utilisent maintenant :"
    )
    print(
        "  1. Flux / demandes total"
    )
    print(
        "  2. Flux livrés"
    )
    print(
        "  3. Flux en cours"
    )
    print(
        "  4. Flux bloqués / rejetés"
    )
    print()
    print(
        "Les anomalies restent dans leur histogramme dédié."
    )
    print()
    print(
        "Relancez maintenant generer_dashboard_commun.cmd"
    )
    print(
        "ou Importer_JIRA.cmd."
    )
    print()


if __name__ == "__main__":
    main()