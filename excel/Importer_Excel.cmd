@echo off
setlocal
cd /d "%~dp0"
python generer_dashboard_gil.py --data-only
if errorlevel 1 py -3 generer_dashboard_gil.py --data-only
if errorlevel 1 goto :error
copy /y dashboard_gil_data.json "..\commun\dashboard_gil_data.json" >nul
call "..\commun\generer_dashboard_commun.cmd"
exit /b %errorlevel%
:error
echo Echec de l'import Excel.
pause
exit /b 1

