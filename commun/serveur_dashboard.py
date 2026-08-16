from __future__ import annotations

import subprocess
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PORT = 8765
ACTIONS = {
    "excel": [PROJECT / "excel" / "Importer_Excel.cmd"],
    "confluence": [PROJECT / "confluence" / "Importer_Confluence.cmd"],
    "jira": [PROJECT / "jira" / "Importer_JIRA.cmd"],
    "sync": [PROJECT / "Synchroniser_Tout.cmd"],
    "archive": [PROJECT / "Archiver_Sprint.cmd"],
    "generate": [ROOT / "generer_dashboard_commun.cmd"],
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", ""}:
            target = ROOT / "dashboard_gil.html"
            if not target.exists():
                target = ROOT / "dashboard_gil_sprint21.html"
            self.path = "/" + target.name
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/action/"):
            self.send_error(404)
            return
        name = path.rsplit("/", 1)[-1]
        cmd = ACTIONS.get(name)
        if not cmd:
            self.send_error(403, "Action non autorisée")
            return
        cmd_path = cmd[0]
        if not cmd_path.exists():
            self.send_error(404, f"Commande introuvable : {cmd_path}")
            return
        try:
            proc = subprocess.run(str(cmd_path), cwd=str(cmd_path.parent), shell=True, text=True, capture_output=True, timeout=1800)
            body = (proc.stdout or "") + (proc.stderr or "")
            status = 200 if proc.returncode == 0 else 500
        except Exception as exc:
            body = f"Erreur action {name}: {exc}"
            status = 500
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8", errors="replace"))


if __name__ == "__main__":
    address = ("127.0.0.1", PORT)
    print(f"Dashboard local : http://127.0.0.1:{PORT}/")
    ThreadingHTTPServer(address, Handler).serve_forever()
