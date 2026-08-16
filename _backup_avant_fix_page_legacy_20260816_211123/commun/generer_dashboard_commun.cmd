@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo   GENERATION DASHBOARD GIL COMMUN
echo ============================================================
echo.
if not exist "dashboard_gil_data.json" (
    echo [ERREUR] dashboard_gil_data.json est introuvable.
    echo Lancez un import ou Synchroniser_Tout.cmd.
    pause
    exit /b 1
)
python "generer_dashboard_gil_classique.py"
if errorlevel 1 py -3 "generer_dashboard_gil_classique.py"
if errorlevel 1 goto :error
if exist "dashboard_gil.html" start "" "%CD%\dashboard_gil.html"
exit /b 0
:error
echo.
echo [ERREUR] Generation dashboard impossible.
pause
exit /b 1
