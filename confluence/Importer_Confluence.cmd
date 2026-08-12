@echo off
setlocal
cd /d "%~dp0"

echo Capture SSO Confluence et mise a jour du dashboard commun...
echo.

node --experimental-websocket capturer_confluence_sso.js
if errorlevel 1 goto :error

python importer_confluence.py --html-dir captures_confluence --diagnostic --output confluence_brut.json
if errorlevel 1 py -3 importer_confluence.py --html-dir captures_confluence --diagnostic --output confluence_brut.json
if errorlevel 1 goto :error

python preparer_source_dashboard.py --input confluence_brut.json --output dashboard_gil_data.json
if errorlevel 1 py -3 preparer_source_dashboard.py --input confluence_brut.json --output dashboard_gil_data.json
if errorlevel 1 goto :error

copy /y "dashboard_gil_data.json" "..\commun\dashboard_gil_data.json" >nul
call "..\commun\generer_dashboard_commun.cmd"
if errorlevel 1 goto :error

echo.
echo Source Confluence importee avec succes.
exit /b 0

:error
echo.
echo L'import Confluence a echoue. Consultez le message ci-dessus.
pause
exit /b 1
