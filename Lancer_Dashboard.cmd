@echo off
setlocal
cd /d "%~dp0"
if exist "commun\preparer_dashboard_runtime.py" (
  python "commun\preparer_dashboard_runtime.py" --bootstrap
)

title Dashboard GIL - page legacy

echo Demarrage du dashboard local GIL...
echo URL : http://127.0.0.1:8765/dashboard_gil.html
echo.

start "" "http://127.0.0.1:8765/dashboard_gil.html"

python "commun\serveur_dashboard.py"
if errorlevel 1 py -3 "commun\serveur_dashboard.py"
if errorlevel 1 pause
