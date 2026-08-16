from __future__ import annotations

import os
import subprocess
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PORT = 8765

ACTIONS = {
    "excel": PROJECT / "excel" / "Importer_Excel.cmd",
    "confluence": PROJECT / "confluence" / "Importer_Confluence.cmd",
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
title Dashboard GIL - action {action}
echo ============================================================
echo   Dashboard GIL - action {action}
echo ============================================================
echo.
cd /d "{target.parent}"
echo Dossier courant :
cd
echo.
echo Commande :
echo   call "{target.name}"
echo.
call "{target.name}"
echo.
echo ============================================================
echo   Action {action} terminee avec code %ERRORLEVEL%
echo ============================================================
pause
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

        if not target or not target.exists():
            self.send_error(404, f"Action introuvable : {action}")
            return

        launcher = make_launcher(action, target)

        if os.name == "nt":
            os.startfile(str(launcher))
        else:
            subprocess.Popen(["sh", str(launcher)], cwd=str(PROJECT))

        self.send_response(202)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"Action {action} lancée dans une nouvelle fenêtre CMD.\\n"
            f"Pour Jira/Confluence : connecte-toi SSO puis appuie sur ENTREE dans cette fenêtre.".encode("utf-8")
        )

if __name__ == "__main__":
    print(f"Dashboard local : http://127.0.0.1:{PORT}/dashboard_gil_sprint21.html")
    print("Actions disponibles :", ", ".join(ACTIONS))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
