@echo off
setlocal
cd /d "%~dp0"
if not exist dashboard_gil_data.json (
  echo Source absente : commun\dashboard_gil_data.json
  echo Lancez un import Excel, Confluence ou JIRA.
  pause
  exit /b 1
)
python generer_dashboard_gil_classique.py
if errorlevel 1 py -3 generer_dashboard_gil_classique.py
if errorlevel 1 (
  echo Echec de generation du dashboard commun.
  pause
  exit /b 1
)
start "" "dashboard_gil_sprint21.html"
echo Dashboard commun actualise.
pause

