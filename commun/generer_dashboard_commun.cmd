@echo off
setlocal

cd /d "%~dp0"

title Generation Dashboard GIL Commun

echo.
echo ============================================================
echo   GENERATION DASHBOARD GIL COMMUN
echo ============================================================
echo.

echo Dossier :
echo %CD%
echo.

if not exist "dashboard_gil_data.json" (
    echo.
    echo [ERREUR] dashboard_gil_data.json est introuvable.
    echo.
    echo Lancez d'abord un import :
    echo   - Excel
    echo   - Confluence
    echo   - JIRA
    echo.
    pause
    exit /b 1
)

if not exist "generer_dashboard_gil_classique.py" (
    echo.
    echo [ERREUR] generer_dashboard_gil_classique.py introuvable.
    pause
    exit /b 1
)

if not exist "dashboard_gil_sprint21.html" (
    echo.
    echo [ERREUR] dashboard_gil_sprint21.html introuvable.
    pause
    exit /b 1
)

echo [1/2] Generation du dashboard...
echo.

python "generer_dashboard_gil_classique.py"

if errorlevel 1 (
    echo.
    echo Tentative avec py -3...
    py -3 "generer_dashboard_gil_classique.py"
)

if errorlevel 1 (
    echo.
    echo ============================================================
    echo   ERREUR DE GENERATION
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Ouverture du dashboard...
echo.

start "" "%CD%\dashboard_gil_sprint21.html"

echo.
echo ============================================================
echo   DASHBOARD GENERE AVEC SUCCES
echo ============================================================
echo.
echo Fichier :
echo %CD%\dashboard_gil_sprint21.html
echo.

pause

endlocal
exit /b 0