@echo off
setlocal
cd /d "%~dp0"
echo Archivage manuel du sprint valide...
python "commun\archiver_sprint.py"
if errorlevel 1 py -3 "commun\archiver_sprint.py"
if errorlevel 1 goto :error
echo.
echo Archive creee avec succes.
pause
exit /b 0
:error
echo.
echo [ERREUR] Archivage impossible.
pause
exit /b 1
