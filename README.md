# Dashboard GIL multisources

Le dashboard HTML est unique dans `commun`. Chaque connecteur produit le meme fichier normalise `dashboard_gil_data.json`, puis lance le generateur commun.

## Utilisation

- Excel : lancer `excel\Importer_Excel.cmd`.
- Confluence SSO : renseigner `confluence\confluence_urls.txt`, puis lancer `confluence\Importer_Confluence.cmd`.
- JIRA SSO : renseigner l'URL principale et les requêtes JQL dans `jira\jira_config.json`, adapter si nécessaire `jira\regles_domaines.json`, puis lancer `jira\Importer_JIRA.cmd`. Le fichier `jira_urls.txt` reste uniquement une compatibilité avec l'ancienne version.

Le resultat est `commun\dashboard_gil.html`.

## Logique JIRA Domaine / Sous-domaine

1. Un Epic est classe avec les champs JIRA configures dans `regles_domaines.json`, s'ils existent.
2. Sinon, les regles de mots-cles analysent son resume, sa description, ses composants et ses labels.
3. Toute Story, tache, sous-tache ou anomalie herite du domaine et du sous-domaine de son Epic parent.
4. Une valeur explicitement portee par le ticket enfant reste prioritaire.
5. Les tickets non classes apparaissent dans `A qualifier` afin qu'aucune donnee ne soit perdue silencieusement.

Les identifiants des champs personnalises different selon l'instance JIRA. Les cles `epic_link`, `sprint`, `domaine`, `sous_domaine`, `severite` et `environnement` sont configurables. Un identifiant vide active la detection par nom de champ quand elle est disponible.

## Vue directeur JIRA

Le JSON conserve les Epics, les taches liees et les bugs avec leur statut, responsable, priorite ou severite, sprint, URL JIRA et parent Epic. Les bugs ouverts deviennent des anomalies `KO`; les bugs termines deviennent des anomalies `Corrigee`.
# DocsHiza
