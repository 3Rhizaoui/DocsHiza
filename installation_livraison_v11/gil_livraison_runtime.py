"""Local delivery server. No Jira/Octane connectors or credentials.

Copied by the exporter as serveur_portal.py. Only pipeline_livraison.py,
created by the exporter, may be executed. Business data are read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}


class DeliveryServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def list_directory(self, path):
        self.send_error(403, "Directory listing disabled")
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _allowed_host(self):
        expected = {f"127.0.0.1:{self.server.server_port}",
                    f"localhost:{self.server.server_port}"}
        return self.headers.get("Host", "") in expected

    def _json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self._allowed_host():
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        if path == "/__delivery__/info":
            try:
                manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
                self._json(200, {"application": "GIL Portal", "deliveryId": manifest["deliveryId"],
                                 "version": "V11", "dataMode": "embedded"})
            except (OSError, ValueError, KeyError):
                self._json(500, {"error": "Manifest absent ou invalide"})
            return
        if path.startswith("/action/status/"):
            job_id = path.rsplit("/", 1)[-1]
            with _LOCK:
                job = _JOBS.get(job_id)
                if job:
                    code = job["process"].poll()
                    result = {"id": job_id,
                              "state": "running" if code is None else "done" if code == 0 else "failed",
                              "exitCode": code}
                else:
                    result = None
            self._json(200 if result else 404, result or {"error": "Action inconnue"})
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if Path(path).suffix.lower() in {".py", ".cmd", ".ps1", ".bat"}:
            self.send_error(403)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        if not self._allowed_host():
            self.send_error(403)
            return
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}",
                                     f"http://localhost:{self.server.server_port}"}:
            self.send_error(403)
            return
        # Ignore rather than retain client logs / credentials.
        self.close_connection = True
        path = urlsplit(self.path).path
        if path == "/log/client":
            self.send_response(204)
            self.end_headers()
            return
        if path not in {"/action/jira", "/action/octane"}:
            self._json(404, {"error": "Action inconnue"})
            return
        pipeline = ROOT / "pipeline_livraison.py"
        if not pipeline.is_file():
            self._json(500, {"error": "Pipeline locale absente"})
            return
        try:
            with _LOCK:
                active = next(((k, j) for k, j in _JOBS.items()
                               if j["process"].poll() is None), None)
                if active:
                    job_id = active[0]
                else:
                    # Bound in-memory history; no business files are written.
                    if len(_JOBS) >= 20:
                        _JOBS.clear()
                    job_id = uuid.uuid4().hex
                    process = subprocess.Popen(
                        [sys.executable, "-u", str(pipeline), path.rsplit("/", 1)[-1]],
                        cwd=str(ROOT),
                        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                        stdin=subprocess.DEVNULL,
                    )
                    _JOBS[job_id] = {"process": process, "created": time.time()}
            self._json(202, {"id": job_id, "state": "running"})
        except OSError as exc:
            self._json(500, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8875)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    try:
        server = DeliveryServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"ERREUR : port {args.port} indisponible. Fermer l'ancienne livraison.\n{exc}", flush=True)
        return 1
    url = f"http://127.0.0.1:{server.server_port}/"
    print("=" * 65, flush=True)
    print("GIL PORTAL", flush=True)
    print("Dossier :", ROOT, flush=True)
    print("URL     :", url, flush=True)
    print("Arret   : Ctrl+C", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
