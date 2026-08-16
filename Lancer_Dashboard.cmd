@echo off
setlocal
cd /d "%~dp0"
title Dashboard GIL - page historique

echo Demarrage du dashboard local GIL...
echo.
echo Cible principale :
echo   http://127.0.0.1:8765/dashboard_gil_sprint21.html
echo.
echo Cette page conserve l'organisation historique du dashboard.
echo Les boutons appellent le serveur local pour lancer les imports.
echo.

start "" "http://127.0.0.1:8765/dashboard_gil_sprint21.html"

python "commun\serveur_dashboard.py"
if errorlevel 1 py -3 "commun\serveur_dashboard.py"
if errorlevel 1 pause
