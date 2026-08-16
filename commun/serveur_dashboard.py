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

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # Permet aux boutons de fonctionner même si dashboard_gil_sprint21.html
        # est ouvert en file:// pendant que ce serveur tourne.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        # Cible principale = ancienne page historique.
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

        name = path.rsplit("/", 1)[-1]
        cmd = ACTIONS.get(name)

        if not cmd:
            self.send_error(403, "Action non autorisee")
            return

        if not cmd.exists():
            self.send_error(404, f"Commande introuvable : {cmd}")
            return

        try:
            if os.name == "nt":
                # Important :
                # - CREATE_NEW_CONSOLE ouvre une vraie fenêtre visible.
                # - /k garde la fenêtre ouverte.
                # - call lance correctement les .cmd.
                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                subprocess.Popen(
                    ["cmd.exe", "/k", f'call "{cmd}"'],
                    cwd=str(cmd.parent),
                    creationflags=flags,
                )
            else:
                subprocess.Popen(["sh", str(cmd)], cwd=str(cmd.parent))

            body = (
                f"Action {name} lancee dans une nouvelle fenetre CMD.\n"
                f"Commande : {cmd}\n"
                "Pour Jira/Confluence : connecte-toi SSO puis appuie sur ENTREE dans la fenetre CMD."
            )
            self.send_response(202)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8", errors="replace"))

        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"Erreur lancement {name}: {exc}".encode("utf-8", errors="replace"))

if __name__ == "__main__":
    print(f"Dashboard local : http://127.0.0.1:{PORT}/")
    print(f"Page cible      : http://127.0.0.1:{PORT}/dashboard_gil_sprint21.html")
    print("Actions         :", ", ".join(ACTIONS))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
