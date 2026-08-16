@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo   SYNCHRONISATION DES 3 SOURCES - DASHBOARD GIL
echo ============================================================
echo.
if not exist "sources" mkdir "sources"

echo [1/5] Import Excel...
call "excel\Importer_Excel.cmd"
echo.
echo [2/5] Import Confluence...
call "confluence\Importer_Confluence.cmd"
echo.
echo [3/5] Import JIRA...
call "jira\Importer_JIRA.cmd"
echo.
echo [4/5] Fusion des sources disponibles...
python "commun\fusionner_sources.py"
if errorlevel 1 py -3 "commun\fusionner_sources.py"
if errorlevel 1 goto :error

echo.
echo [5/5] Generation du dashboard...
call "commun\generer_dashboard_commun.cmd"
exit /b %errorlevel%

:error
echo.
echo [ERREUR] Synchronisation impossible.
pause
exit /b 1
