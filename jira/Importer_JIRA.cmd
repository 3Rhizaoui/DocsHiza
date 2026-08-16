@echo off
setlocal
cd /d "%~dp0"
title Import JIRA - Dashboard GIL

echo ============================================================
echo   IMPORT JIRA - DASHBOARD GIL
echo ============================================================
echo.

echo [1/3] Recuperation des donnees JIRA...
node "capturer_jira_sso.js"
if errorlevel 1 goto :error

if not exist "jira_brut.json" goto :missing_brut

echo.
echo [2/3] Preparation des donnees JIRA...
python "preparer_source_jira.py"
if errorlevel 1 py -3 "preparer_source_jira.py"
if errorlevel 1 goto :error

if not exist "dashboard_gil_data.json" goto :missing_dashboard

echo.
echo [3/3] Publication JIRA dans le dashboard HTML legacy...
python "..\commun\publier_jira_dashboard.py"
if errorlevel 1 py -3 "..\commun\publier_jira_dashboard.py"
if errorlevel 1 goto :error

echo.
echo IMPORT JIRA TERMINE AVEC SUCCES
exit /b 0

:missing_brut
echo [ERREUR] jira_brut.json n'a pas ete genere.
pause
exit /b 1

:missing_dashboard
echo [ERREUR] dashboard_gil_data.json n'a pas ete genere.
pause
exit /b 1

:error
echo.
echo [ERREUR] Import JIRA en echec.
pause
exit /b 1
