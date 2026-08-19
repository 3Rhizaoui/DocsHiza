@echo off
setlocal
cd /d "%~dp0"
if exist "commun\preparer_dashboard_runtime.py" (
  python "commun\preparer_dashboard_runtime.py" --bootstrap
)


echo ============================================================
echo  DASHBOARD GIL - DEMARRAGE LOCAL
echo ============================================================
echo.
echo Dossier projet :
echo   %CD%
echo.
echo Le navigateur va ouvrir :
echo   http://127.0.0.1:8765/dashboard_gil.html
echo.
echo Ensuite :
echo   1. Cliquer sur Importer JIRA
echo   2. Faire le SSO Jira
echo   3. Revenir au terminal JIRA et valider avec Entree
echo   4. La page se recharge automatiquement apres publication
echo.

if exist "Lancer_Dashboard.cmd" (
  call "Lancer_Dashboard.cmd"
) else (
  echo [ERREUR] Lancer_Dashboard.cmd introuvable.
  pause
)
