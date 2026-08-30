@echo off
setlocal

cd /d "%~dp0"

echo ============================================================
echo   GIL PORTAL
echo ============================================================
echo.
echo Demarrage du Portal GIL...
echo.
echo URL :
echo   http://127.0.0.1:8765/
echo.

start "" "http://127.0.0.1:8765/"

python serveur_portal.py

endlocal
