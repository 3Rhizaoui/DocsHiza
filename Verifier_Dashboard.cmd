@echo off
setlocal
cd /d "%~dp0"
python "commun\verifier_dashboard.py"
if errorlevel 1 py -3 "commun\verifier_dashboard.py"
if errorlevel 1 goto :error
pause
exit /b 0
:error
pause
exit /b 1
