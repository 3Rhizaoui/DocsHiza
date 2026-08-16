@echo off
setlocal
cd /d "%~dp0"
python generer_dashboard_gil.py --data-only
if errorlevel 1 py -3 generer_dashboard_gil.py --data-only
if errorlevel 1 goto :error
if not exist "..\sources" mkdir "..\sources"
copy /y dashboard_gil_data.json "..\sources\excel.json" >nul
python "..\commun\fusionner_sources.py"
if errorlevel 1 py -3 "..\commun\fusionner_sources.py"
if errorlevel 1 goto :error
call "..\commun\generer_dashboard_commun.cmd"
exit /b %errorlevel%
:error
echo Echec de l'import Excel.
pause
exit /b 1
