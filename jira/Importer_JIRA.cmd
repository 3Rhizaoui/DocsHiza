@echo off
setlocal
cd /d "%~dp0"
node --experimental-websocket capturer_jira_sso.js
if errorlevel 1 goto :error
python preparer_source_jira.py
if errorlevel 1 py -3 preparer_source_jira.py
if errorlevel 1 goto :error
copy /y "dashboard_gil_data.json" "..\commun\dashboard_gil_data.json" >nul
call "..\commun\generer_dashboard_commun.cmd"
exit /b %errorlevel%

:error
echo.
echo L'import JIRA a echoue. Consultez le message ci-dessus.
pause
exit /b 1
