@echo off
setlocal
cd /d "%~dp0"
title Import JIRA - Dashboard GIL

echo ============================================================
echo   IMPORT JIRA - DASHBOARD GIL
echo ============================================================
echo.

echo [1/4] Recuperation des donnees JIRA...
node "capturer_jira_sso.js"
if errorlevel 1 goto :error

echo.
echo [2/4] Preparation des donnees JIRA...
python "preparer_source_jira.py"
if errorlevel 1 py -3 "preparer_source_jira.py"
if errorlevel 1 goto :error
if not exist "dashboard_gil_data.json" goto :missing

echo.
echo [3/4] Copie de la source JIRA normalisee...
if not exist "..\sources" mkdir "..\sources"
copy /Y "dashboard_gil_data.json" "..\sources\jira.json" >nul
if errorlevel 1 goto :error

echo.
echo [4/4] Fusion et generation du dashboard...
python "..\commun\fusionner_sources.py"
if errorlevel 1 py -3 "..\commun\fusionner_sources.py"
if errorlevel 1 goto :error
call "..\commun\generer_dashboard_commun.cmd"
if errorlevel 1 goto :error

echo.
echo IMPORT JIRA TERMINE AVEC SUCCES
exit /b 0

:missing
echo [ERREUR] dashboard_gil_data.json n'a pas ete genere.
pause
exit /b 1

:error
echo.
echo [ERREUR] Import JIRA en echec.
pause
exit /b 1
