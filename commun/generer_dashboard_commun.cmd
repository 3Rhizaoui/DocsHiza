@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   GENERATION DASHBOARD GIL COMMUN - PAGE LEGACY
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

REM Compatibilite avec le HTML legacy qui charge rapport_gil_v6_data.json
if exist "rapport_gil_v6_w28_data.json" copy /Y "rapport_gil_v6_w28_data.json" "rapport_gil_v6_data.json" >nul
if exist "dashboard_gil_data.json" copy /Y "dashboard_gil_data.json" "dashboard_gil_data_live.json" >nul

echo.
echo Dashboard legacy regenere :
echo   %CD%\dashboard_gil_sprint21.html
echo.
exit /b 0

:error
echo.
echo [ERREUR] Generation dashboard impossible.
pause
exit /b 1
