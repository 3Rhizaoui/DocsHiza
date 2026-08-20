@echo off



setlocal EnableExtensions EnableDelayedExpansion







set "SCRIPT_DIR=%~dp0"



set "PROJECT_DIR=%SCRIPT_DIR%.."







cd /d "%PROJECT_DIR%"







echo ============================================================



echo   IMPORT JIRA - DASHBOARD GIL



echo ============================================================



echo.



echo Dossier projet :



echo   %PROJECT_DIR%



echo.







echo ============================================================



echo [1/7] EXTRACTION JIRA VIA SSO



echo ============================================================



echo Objectif :



echo   - ouvrir Jira via SSO



echo   - executer les requetes JQL configurees



echo   - produire jira_brut.json et jira_diagnostic.json



echo.







node "%PROJECT_DIR%\jira\capturer_jira_sso.js"



if errorlevel 1 goto erreur_extraction







echo.



echo ============================================================



echo [2/7] DETECTION OFFICIELLE DES SPRINTS JIRA



echo ============================================================



echo Objectif :



echo   - construire sprints_dashboard.json



echo   - identifier sprint courant et sprint precedent



echo.







python "%PROJECT_DIR%\jira\construire_sprints_jira.py"



if errorlevel 1 goto erreur







echo.



echo ============================================================



echo [3/7] ARCHITECTURE JSON PAR SPRINT



echo ============================================================



echo Objectif :



echo   - produire jira\sprints\sprint_courant.json



echo   - produire jira\sprints\sprint_precedent.json



echo   - produire jira\presentation\comparaison_sprints.json



echo.







python "%PROJECT_DIR%\jira\construire_architecture_sprints.py"



if errorlevel 1 goto erreur







python "%PROJECT_DIR%\jira\auditer_architecture_sprints.py"



if errorlevel 1 goto erreur







echo.



echo ============================================================



echo [4/7] PREPARATION SOURCE DASHBOARD



echo ============================================================



echo Objectif :



echo   - transformer les tickets Jira en lignes dashboard



echo   - produire jira\dashboard_gil_data.json



echo.







python "%PROJECT_DIR%\jira\preparer_source_jira.py"



if errorlevel 1 goto erreur







echo.



echo ============================================================



echo [5/7] PUBLICATION HTML



echo ============================================================



echo Objectif :



echo   - publier commun\dashboard_gil.html



echo   - conserver le calcul historique du statut sprint



echo.







echo [INFO] Publication HTML legacy desactivee : le HTML final sera genere uniquement apres le payload final.



rem python "%PROJECT_DIR%\commun\publier_jira_dashboard.py"



rem if errorlevel 1 goto erreur







echo.



echo ============================================================



echo [6/7] PAYLOAD DASHBOARD FINAL



echo ============================================================



echo Objectif :



echo   - conserver la sante GIL basee sur JQL Arrimage



echo   - conserver les blocs legacy enrichis



echo   - injecter la comparaison officielle API Agile



echo   - produire commun\dashboard_gil_data.json final







python "%PROJECT_DIR%\jira\construire_comparaison_dashboard.py"



if errorlevel 1 goto erreur







python "%PROJECT_DIR%\jira\construire_payload_dashboard_final.py"



if errorlevel 1 goto erreur







python "%PROJECT_DIR%\commun\injecter_payload_final_html.py"

if errorlevel 1 goto erreur

python "%PROJECT_DIR%\commun\force_runtime_markers.py"

echo [INFO] Nettoyage historique navigateur local avant audit
del /f /q "%PROJECT_DIR%\jira\.jira_sso_profile_manuel\Default\History" >nul 2>nul
del /f /q "%PROJECT_DIR%\jira\.jira_sso_profile_manuel\Default\History-journal" >nul 2>nul


if errorlevel 1 goto erreur



if errorlevel 1 goto erreur







if errorlevel 1 goto erreur







echo.



echo ============================================================



echo [6/7] PREPARATION RUNTIME HTML



echo ============================================================



echo Objectif :



echo   - copier les JSON utiles dans commun\



echo   - permettre au HTML generique de les charger directement



echo.







echo.



echo ============================================================



echo [7/7] CONTROLE FINAL



echo ============================================================







python "%PROJECT_DIR%\jira\controle_import_jira.py"



if errorlevel 1 goto erreur







if exist "%PROJECT_DIR%\audit_dashboard_gil.py" (



  python "%PROJECT_DIR%\audit_dashboard_gil.py" --mode runtime



  if errorlevel 1 goto erreur



)







echo.



echo ============================================================



echo IMPORT JIRA TERMINE AVEC SUCCES



echo ============================================================



echo.







echo Fichiers runtime attendus :



dir "%PROJECT_DIR%\commun\sprint_courant.json" "%PROJECT_DIR%\commun\sprint_precedent.json" "%PROJECT_DIR%\commun\comparaison_sprints.json"







for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeMilliseconds()"') do set GIL_TS=%%i







echo.



echo Ouverture dashboard actualise :



echo   http://127.0.0.1:8765/dashboard_gil.html?_gil_refresh=%GIL_TS%



start "" "http://127.0.0.1:8765/dashboard_gil.html?_gil_refresh=%GIL_TS%"







echo.



echo Action jira terminee avec code 0



pause



exit /b 0







:erreur_extraction



echo.



echo ============================================================



echo [ERREUR BLOQUANTE] Extraction JIRA en echec.



echo ============================================================



echo La suite est arretee car jira_brut.json n'est pas fiable.



pause



exit /b 1







:erreur



echo.



echo ============================================================



echo [ERREUR BLOQUANTE] Import JIRA interrompu.



echo ============================================================



echo Controle les messages ci-dessus.



pause



exit /b 1



