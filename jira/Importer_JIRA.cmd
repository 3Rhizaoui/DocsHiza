@echo off
setlocal

cd /d "%~dp0"

title Import JIRA - Dashboard GIL

echo.
echo ============================================================
echo   IMPORT JIRA - DASHBOARD GIL
echo ============================================================
echo.

echo Dossier JIRA :
echo %CD%
echo.

REM ============================================================
REM 1 - CAPTURE JIRA
REM ============================================================

echo [1/4] Recuperation des donnees JIRA...
node "capturer_jira_sso.js"

if errorlevel 1 (
    echo.
    echo [ERREUR] La recuperation JIRA a echoue.
    echo Le dashboard ne sera pas regenere.
    pause
    exit /b 1
)

REM ============================================================
REM 2 - NORMALISATION JIRA
REM ============================================================

echo.
echo [2/4] Preparation des donnees JIRA...
python "preparer_source_jira.py"

if errorlevel 1 (
    py -3 "preparer_source_jira.py"
)

if errorlevel 1 (
    echo.
    echo [ERREUR] La preparation des donnees JIRA a echoue.
    pause
    exit /b 1
)

if not exist "dashboard_gil_data.json" (
    echo.
    echo [ERREUR] dashboard_gil_data.json n'a pas ete genere.
    pause
    exit /b 1
)

REM ============================================================
REM 3 - COPIE VERS LE DOSSIER COMMUN
REM ============================================================

echo.
echo [3/4] Copie des donnees vers le dashboard commun...

if not exist "..\commun" (
    echo.
    echo [ERREUR] Le dossier ..\commun est introuvable.
    echo Dossier courant : %CD%
    pause
    exit /b 1
)

copy /Y "dashboard_gil_data.json" "..\commun\dashboard_gil_data.json"

if errorlevel 1 (
    echo.
    echo [ERREUR] Impossible de copier dashboard_gil_data.json.
    pause
    exit /b 1
)

echo.
echo Donnees copiees dans :
echo %CD%\..\commun\dashboard_gil_data.json

REM ============================================================
REM 4 - GENERATION DU DASHBOARD
REM ============================================================

echo.
echo [4/4] Generation du dashboard HTML...

pushd "..\commun"

echo Dossier commun :
echo %CD%
echo.

if not exist "generer_dashboard_gil_classique.py" (
    echo [ERREUR] generer_dashboard_gil_classique.py introuvable dans :
    echo %CD%
    popd
    pause
    exit /b 1
)

python "generer_dashboard_gil_classique.py"

if errorlevel 1 (
    py -3 "generer_dashboard_gil_classique.py"
)

if errorlevel 1 (
    echo.
    echo [ERREUR] La generation du dashboard a echoue.
    popd
    pause
    exit /b 1
)

if not exist "dashboard_gil_sprint21.html" (
    echo.
    echo [ERREUR] dashboard_gil_sprint21.html est introuvable dans :
    echo %CD%
    popd
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   IMPORT JIRA TERMINE AVEC SUCCES
echo ============================================================
echo.
echo Dashboard :
echo %CD%\dashboard_gil_sprint21.html
echo.
echo Ouverture du dashboard...

start "" "%CD%\dashboard_gil_sprint21.html"

popd

echo.
echo Dashboard genere et ouvert.
echo.

pause

endlocal
exit /b 0