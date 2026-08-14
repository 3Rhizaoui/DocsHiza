@echo off
setlocal
cd /d "%~dp0"

title Import JIRA - Dashboard GIL

echo.
echo ============================================================
echo   IMPORT JIRA - DASHBOARD GIL
echo ============================================================
echo.

echo [1/3] Recuperation des donnees JIRA...
node capturer_jira_sso.js

if errorlevel 1 (
    echo.
    echo [ERREUR] La recuperation JIRA a echoue.
    echo Le dashboard ne sera pas regenere.
    pause
    exit /b 1
)

echo.
echo [2/3] Preparation des donnees JIRA...
python preparer_source_jira.py

if errorlevel 1 (
    echo.
    echo [ERREUR] La preparation des donnees JIRA a echoue.
    echo Le dashboard ne sera pas regenere.
    pause
    exit /b 1
)

echo.
echo [3/3] Generation du dashboard HTML...
python generer_dashboard_gil_classique.py

if errorlevel 1 (
    echo.
    echo [ERREUR] La generation du dashboard a echoue.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   IMPORT TERMINE AVEC SUCCES
echo ============================================================
echo.

if exist "dashboard_gil_sprint21.html" (
    echo Ouverture du dashboard...
    start "" "%~dp0dashboard_gil_sprint21.html"
) else (
    echo [ERREUR] dashboard_gil_sprint21.html est introuvable.
    pause
    exit /b 1
)

echo.
echo Dashboard ouvert dans le navigateur.
echo.

timeout /t 3 /nobreak >nul

endlocal
exit /b 0