from __future__ import annotations

import os
import subprocess
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PORT = 8765

def find_cmd(*parts: str) -> Path | None:
    direct = PROJECT.joinpath(*parts)
    if direct.exists():
        return direct.resolve()

    name = parts[-1].lower()
    for p in PROJECT.rglob(parts[-1]):
        if p.name.lower() == name and ".git" not in p.parts:
            return p.resolve()

    return None

ACTIONS = {
    "excel": find_cmd("excel", "Importer_Excel.cmd"),
    "confluence": find_cmd("confluence", "Importer_Confluence.cmd"),
    "jira": find_cmd("jira", "Importer_JIRA.cmd"),
    "sync": find_cmd("Synchroniser_Tout.cmd"),
    "archive": find_cmd("Archiver_Sprint.cmd"),
    "generate": find_cmd("commun", "generer_dashboard_commun.cmd"),
}

RUN_DIR = PROJECT / ".dashboard_runs"
RUN_DIR.mkdir(exist_ok=True)

def make_launcher(action: str, target: Path) -> Path:
    launcher = RUN_DIR / f"run_{action}.cmd"

    launcher.write_text(f"""@echo off
chcp 65001 >nul
title Dashboard GIL - action {action}

echo ============================================================
echo   Dashboard GIL - action {action}
echo ============================================================
echo.

echo Projet :
echo   {PROJECT}
echo.

echo Commande cible :
echo   {target}
echo.

if not exist "{target}" (
  echo [ERREUR] Fichier commande introuvable :
  echo   {target}
  echo.
  echo Dossiers disponibles dans le projet :
  dir "{PROJECT}" /ad
  echo.
  pause
  exit /b 1
)

echo Dossier de la commande :
echo   {target.parent}
echo.

pushd "{target.parent}"
if errorlevel 1 (
  echo [ERREUR] Impossible d'entrer dans le dossier :
  echo   {target.parent}
  echo.
  pause
  exit /b 1
)

echo Dossier courant apres pushd :
cd
echo.

echo Lancement :
echo   call "{target.name}"
echo.

call "{target.name}"

set RC=%ERRORLEVEL%

echo.
echo ============================================================
echo   Action {action} terminee avec code %RC%
echo ============================================================
echo.

popd
pause
exit /b %RC%
""", encoding="utf-8")

    return launcher

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in {"", "/"}:
            self.path = "/dashboard_gil_sprint21.html"

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if not path.startswith("/action/"):
            self.send_error(404)
            return

        action = path.rsplit("/", 1)[-1]
        target = ACTIONS.get(action)

        if not target:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"Action introuvable ou commande absente : {action}\n\n"
                f"Projet detecte : {PROJECT}\n"
                f"Actions detectees : {ACTIONS}\n".encode("utf-8", errors="replace")
            )
            return

        try:
            launcher = make_launcher(action, target)

            if os.name == "nt":
                os.startfile(str(launcher))
            else:
                subprocess.Popen(["sh", str(launcher)], cwd=str(PROJECT))

            body = (
                f"Action {action} lancée dans une nouvelle fenêtre CMD.\n"
                f"Commande cible : {target}\n"
                f"Launcher : {launcher}\n\n"
                "Pour Jira/Confluence : connecte-toi SSO puis appuie sur ENTREE dans cette fenêtre."
            )

            self.send_response(202)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8", errors="replace"))

        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"Erreur lancement {action}: {exc}".encode("utf-8", errors="replace"))

if __name__ == "__main__":
    print(f"Dashboard local : http://127.0.0.1:{PORT}/dashboard_gil_sprint21.html")
    print("Projet detecte  :", PROJECT)
    print("Actions detectees :")
    for name, target in ACTIONS.items():
        print(" -", name, "=>", target)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
