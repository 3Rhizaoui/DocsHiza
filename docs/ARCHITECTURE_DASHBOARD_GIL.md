# Architecture Dashboard GIL - Jira

## Principe

Le dashboard HTML est une template variabilisée. Il n'est pas responsable de reconstruire l'architecture Jira.

## Flux cible

Jira SSO
→ jira/jira_brut.json
→ jira/sprints_dashboard.json
→ jira/sprints/sprint_precedent.json
→ jira/sprints/sprint_courant.json
→ jira/presentation/comparaison_sprints.json
→ commun/dashboard_gil.html

## Règles

1. Les JSON sprint contiennent toutes les données disponibles :
   tickets, epics, anomalies, tâches, statut, description, reporter, assignee, liens Jira, parent, liens, champs métier.

2. Les JSON de présentation alimentent les graphes :
   comparaison_sprints.json, kpis_sprint.json, flux_dashboard.json, anomalies_dashboard.json.

3. Le dashboard affiche uniquement les données injectées.
   Il ne déduit pas le sprint courant, le sprint précédent ou la ventilation métier.

4. Les valeurs non ventilées sont explicites.
   Pour compatibilité legacy, le non ventilé peut être affiché côté SIT, mais le champ nonVentile reste conservé.

5. L'audit runtime bloque si les JSON d'architecture sont absents ou incohérents.
