from __future__ import annotations

import os
import shutil
import subprocess
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PORT = 8765

ACTIONS = {

    "jira": PROJECT / "jira" / "Importer_JIRA.cmd",
    "sync": PROJECT / "Synchroniser_Tout.cmd",
    "archive": PROJECT / "Archiver_Sprint.cmd",
    "generate": ROOT / "generer_dashboard_commun.cmd",
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
  pause
  exit /b 1
)

pushd "{target.parent}"
if errorlevel 1 (
  echo [ERREUR] Impossible d'entrer dans :
  echo   {target.parent}
  echo.
  pause
  exit /b 1
)

echo Dossier courant :
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
        super().__init__(*args, directory=str(PROJECT), **kwargs)

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

        if path in {"", "/", "/portal", "/portal/"}:
            self.path = "/portal/index.html"
            return super().do_GET()

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        # Compatibilité page legacy :
        # l'ancien HTML demande rapport_gil_v6_data.json,
        # alors que ton repo contient souvent rapport_gil_v6_w28_data.json.
        if path.endswith("/rapport_gil_v6_data.json") or path == "/rapport_gil_v6_data.json":
            candidates = [
                ROOT / "rapport_gil_v6_data.json",
                ROOT / "rapport_gil_v6_w28_data.json",
                ROOT / "dashboard_gil_data.json",
            ]
            for candidate in candidates:
                if candidate.exists():
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(candidate.read_bytes())
                    return

            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"rapport_gil_v6_data.json introuvable. Aucun JSON compatible trouve."
            )
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
            self.wfile.write(f"Action inconnue : {action}".encode("utf-8"))
            return

        target = target.resolve()

        if not target.exists():
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"Commande introuvable : {target}".encode("utf-8", errors="replace"))
            return

        launcher = make_launcher(action, target)

        try:
            if os.name == "nt":
                # Plus fiable que os.startfile dans certains contextes Edge/OneDrive :
                subprocess.Popen(
                    ["cmd.exe", "/k", str(launcher)],
                    cwd=str(PROJECT),
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
            else:
                subprocess.Popen(["sh", str(launcher)], cwd=str(PROJECT))

            self.send_response(202)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                (
                    f"Action {action} lancee dans une nouvelle fenetre CMD.\n"
                    f"Commande cible : {target}\n"
                    f"Launcher : {launcher}\n\n"
                    "Pour Jira/Confluence : connecte-toi SSO puis appuie sur ENTREE dans la fenetre CMD."
                ).encode("utf-8", errors="replace")
            )

        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"Erreur lancement {action}: {exc}".encode("utf-8", errors="replace"))

if __name__ == "__main__":
    print(f"Portail GIL local : http://127.0.0.1:{PORT}/portal/")
    print("Projet detecte  :", PROJECT)
    print("Actions detectees :")
    for name, target in ACTIONS.items():
        print(" -", name, "=>", target, "OK" if target.exists() else "ABSENT")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
