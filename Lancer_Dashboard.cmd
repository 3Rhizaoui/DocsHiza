@echo off
setlocal
cd /d "%~dp0"
echo Demarrage du dashboard local GIL...
echo URL : http://127.0.0.1:8765/
echo.
start "" "http://127.0.0.1:8765/"
python "commun\serveur_dashboard.py"
if errorlevel 1 py -3 "commun\serveur_dashboard.py"
if errorlevel 1 pause
