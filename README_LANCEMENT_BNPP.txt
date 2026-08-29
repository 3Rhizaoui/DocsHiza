LANCEMENT DASHBOARD GIL DEPUIS ZIP

1. Dezipper le projet.
2. Double-cliquer sur 00_DEMARRER_DASHBOARD_GIL.cmd.
3. Le navigateur ouvre http://127.0.0.1:8765/portal/.
4. Cliquer sur Importer JIRA.
5. Faire l'authentification SSO Jira, puis revenir au terminal et appuyer sur Entree.
6. L'import produit automatiquement :
   - jira/jira_brut.json
   - jira/jira_diagnostic.json
   - jira/sprints_dashboard.json
   - jira/dashboard_gil_data.json
   - commun/portal/index.html
7. A la fin, audit_dashboard_gil.py --mode runtime est lance automatiquement.
8. Le navigateur recharge automatiquement le portail GIL apres publication.

Important :
- Ne pas ouvrir directement commun/portal/index.html en file:// pour lancer les actions.
- Les actions locales ont besoin du serveur 127.0.0.1:8765.
