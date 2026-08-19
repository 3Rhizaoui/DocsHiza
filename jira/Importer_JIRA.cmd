@echo off
setlocal
cd /d "%~dp0"
title Import JIRA - Dashboard GIL

echo.
echo ============================================================
echo   IMPORT JIRA - DASHBOARD GIL
echo ============================================================
echo.
echo Dossier projet :
echo   %~dp0..
echo.

echo ============================================================
echo [1/5] EXTRACTION JIRA VIA SSO
echo ============================================================
echo Objectif :
echo   - ouvrir Jira via SSO
echo   - executer les requetes JQL configurees
echo   - produire jira_brut.json et jira_diagnostic.json
echo.

node "capturer_jira_sso.js"
if errorlevel 1 goto :extract_error

if not exist "jira_brut.json" goto :missing_brut
if not exist "jira_diagnostic.json" goto :missing_diag

echo.
echo [OK] Extraction JIRA terminee.
echo.

echo ============================================================
echo [2/5] ANALYSE DYNAMIQUE DES SPRINTS JIRA
echo ============================================================
echo Objectif :
echo   - detecter le sprint courant depuis Jira
echo   - detecter le sprint precedent depuis Jira
echo   - separer flux et anomalies par sprint
echo   - produire sprints_dashboard.json
echo.

python "construire_sprints_jira.py"
if errorlevel 1 goto erreur
python "%PROJECT_DIR%\jira\construire_architecture_sprints.py"
if errorlevel 1 goto erreur
python "%PROJECT_DIR%\jira\auditer_architecture_sprints.py"
if errorlevel 1 py -3 "construire_sprints_jira.py"
if errorlevel 1 goto :sprint_error

if not exist "sprints_dashboard.json" goto :missing_sprints

echo.
echo [OK] Analyse des sprints terminee.
echo.

echo ============================================================
echo [3/5] PREPARATION SOURCE JIRA NORMALISEE
echo ============================================================
echo Objectif :
echo   - transformer les tickets Jira en lignes dashboard
echo   - garder le calcul historique existant
echo.

python "preparer_source_jira.py"
if errorlevel 1 py -3 "preparer_source_jira.py"
if errorlevel 1 goto :prepare_error

if not exist "dashboard_gil_data.json" goto :missing_dashboard

echo.
echo [OK] Source JIRA normalisee produite.
echo.

echo ============================================================
echo [4/5] PUBLICATION HTML LEGACY
echo ============================================================
echo Objectif :
echo   - publier les donnees JIRA dans commun\dashboard_gil.html
echo   - injecter les noms de sprint dynamiques
echo   - injecter la comparaison sprint precedent / sprint courant
echo   - conserver les donnees apres Ctrl+F5
echo.

python "..\commun\publier_jira_dashboard.py"
if errorlevel 1 py -3 "..\commun\publier_jira_dashboard.py"
if errorlevel 1 goto :publish_error

echo.
echo [OK] Publication HTML terminee.
echo.

echo ============================================================
echo [5/5] CONTROLE FINAL IMPORT JIRA
echo ============================================================

python "controle_import_jira.py"

echo.
echo ============================================================
echo IMPORT JIRA TERMINE AVEC SUCCES
echo ============================================================
exit /b 0

:extract_error
echo.
echo ============================================================
echo [ERREUR BLOQUANTE] Extraction JIRA en echec.
echo ============================================================
echo La suite est arretee car jira_brut.json n'est pas fiable.
pause
exit /b 1

:sprint_error
echo.
echo ============================================================
echo [ERREUR BLOQUANTE] Analyse dynamique des sprints en echec.
echo ============================================================
echo La comparaison Sprint precedent / Sprint courant ne peut pas etre consideree fiable.
pause
exit /b 1

:prepare_error
echo.
echo ============================================================
echo [ERREUR BLOQUANTE] Preparation des donnees JIRA en echec.
echo ============================================================
echo La publication HTML n'est pas lancee car dashboard_gil_data.json n'est pas fiable.
pause
exit /b 1

:publish_error
echo.
echo ============================================================
echo [ERREUR BLOQUANTE] Publication HTML en echec.
echo ============================================================
echo Les donnees JIRA sont extraites mais non publiees dans la page HTML.
pause
exit /b 1

:missing_brut
echo.
echo [ERREUR BLOQUANTE] jira_brut.json n'a pas ete genere.
pause
exit /b 1

:missing_diag
echo.
echo [ERREUR BLOQUANTE] jira_diagnostic.json n'a pas ete genere.
pause
exit /b 1

:missing_sprints
echo.
echo [ERREUR BLOQUANTE] sprints_dashboard.json n'a pas ete genere.
pause
exit /b 1

:missing_dashboard
echo.
echo [ERREUR BLOQUANTE] dashboard_gil_data.json n'a pas ete genere.


echo.
echo ============================================================


echo.
echo ============================================================
echo [AUTO] PREPARATION HTML RUNTIME
echo ============================================================
if not defined PROJECT_DIR set "PROJECT_DIR=%~dp0.."
if exist "%PROJECT_DIR%\commun\preparer_dashboard_runtime.py" (
  python "%PROJECT_DIR%\commun\preparer_dashboard_runtime.py" --after-import
) else (
  echo [INFO] preparer_dashboard_runtime.py introuvable.
)

echo [AUTO] AUDIT RUNTIME DASHBOARD GIL
echo ============================================================
if not defined PROJECT_DIR set "PROJECT_DIR=%~dp0.."
if exist "%PROJECT_DIR%\audit_dashboard_gil.py" (
  python "%PROJECT_DIR%\audit_dashboard_gil.py" --mode runtime
) else (
  echo [INFO] audit_dashboard_gil.py introuvable, audit runtime ignore.
)

pause
exit /b 1
