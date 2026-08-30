from __future__ import annotations

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import subprocess
import json
import sys


PORT = 8765

PORTAL = Path(__file__).resolve().parent
PROJECT = PORTAL.parent


LOG_ROOT = PORTAL / "logs"

for _folder in [
    "server",
    "pipeline",
    "jira",
    "publication",
    "pages",
    "audit",
    "errors",
]:
    (
        LOG_ROOT
        / _folder
    ).mkdir(
        parents=True,
        exist_ok=True,
    )


def write_log(
    component,
    level,
    event,
    **details,
):

    now = datetime.now()

    folder = (
        LOG_ROOT
        / component
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = (
        folder
        / (
            f"{component}_"
            f"{now:%Y-%m-%d}.log"
        )
    )

    payload = {
        "timestamp":
            now.isoformat(
                timespec="seconds"
            ),

        "level":
            level,

        "event":
            event,

        **details,
    }

    with log_file.open(
        "a",
        encoding="utf-8",
    ) as fh:

        fh.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )
            + "\n"
        )



JIRA_IMPORT = (
    PROJECT
    / "jira"
    / "Importer_JIRA.cmd"
)


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            directory=str(PORTAL),
            **kwargs,
        )

    def end_headers(self):
        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate",
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )
        super().end_headers()

    def log_message(
        self,
        format,
        *args,
    ):

        message = (
            format
            % args
        )

        write_log(
            "server",
            "INFO",
            "HTTP_REQUEST",
            client=self.client_address[0],
            method=self.command,
            path=self.path,
            message=message,
        )

        super().log_message(
            format,
            *args,
        )


    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):

        path = urlparse(self.path).path

        if path in {"", "/"}:
            self.path = "/index.html"
            return super().do_GET()

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        return super().do_GET()

    def do_POST(self):

        path = urlparse(self.path).path

        if path == "/log/client":

            try:

                length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

                raw = self.rfile.read(
                    length
                )

                payload = json.loads(
                    raw.decode(
                        "utf-8"
                    )
                    or "{}"
                )

                level = str(
                    payload.get(
                        "level",
                        "INFO",
                    )
                ).upper()

                write_log(
                    "pages",
                    level,
                    payload.get(
                        "event",
                        "CLIENT_EVENT",
                    ),
                    page=payload.get(
                        "page"
                    ),
                    url=payload.get(
                        "url"
                    ),
                    details=payload.get(
                        "details",
                        {},
                    ),
                )

                if level in {
                    "ERROR",
                    "CRITICAL",
                }:

                    write_log(
                        "errors",
                        level,
                        payload.get(
                            "event",
                            "CLIENT_ERROR",
                        ),
                        page=payload.get(
                            "page"
                        ),
                        details=payload.get(
                            "details",
                            {},
                        ),
                    )

                self.send_response(
                    204
                )
                self.end_headers()

            except Exception as exc:

                write_log(
                    "errors",
                    "ERROR",
                    "CLIENT_LOG_ERROR",
                    error=str(exc),
                )

                self.send_response(
                    500
                )
                self.end_headers()

            return


        if path != "/action/jira":
            self.send_error(404)
            return

        if not JIRA_IMPORT.exists():

            self.send_response(500)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8",
            )
            self.end_headers()

            self.wfile.write(
                (
                    "Importer_JIRA.cmd introuvable :\n"
                    + str(JIRA_IMPORT)
                ).encode("utf-8")
            )
            return

        try:

            write_log(
                "pipeline",
                "INFO",
                "JIRA_PIPELINE_REQUESTED",
                endpoint="/action/jira",
                command=str(JIRA_IMPORT),
            )

            write_log(
                "jira",
                "INFO",
                "JIRA_IMPORT_START",
                command=str(JIRA_IMPORT),
            )

            subprocess.Popen(
                [
                    "cmd.exe",
                    "/c",
                    "start",
                    "Dashboard GIL - action jira",
                    "cmd.exe",
                    "/k",
                    "call",
                    str(JIRA_IMPORT),
                ],
                cwd=str(JIRA_IMPORT.parent),
            )

            self.send_response(202)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8",
            )
            self.end_headers()

            self.wfile.write(
                (
                    "Pipeline JIRA lancé.\n"
                    "Connecte-toi au SSO Jira puis "
                    "continue dans la fenêtre CMD."
                ).encode("utf-8")
            )

        except Exception as exc:

            write_log(
                "errors",
                "ERROR",
                "JIRA_LAUNCH_ERROR",
                error=str(exc),
            )

            write_log(
                "jira",
                "ERROR",
                "JIRA_IMPORT_LAUNCH_ERROR",
                error=str(exc),
            )

            self.send_response(500)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8",
            )
            self.end_headers()

            self.wfile.write(
                (
                    "Erreur lancement JIRA : "
                    + str(exc)
                ).encode("utf-8")
            )


if __name__ == "__main__":

    write_log(
        "server",
        "INFO",
        "PORTAL_SERVER_START",
        port=PORT,
        portal=str(PORTAL),
        project=str(PROJECT),
    )

    print()
    print("=" * 60)
    print("GIL PORTAL")
    print("=" * 60)
    print()
    print(
        f"URL : http://127.0.0.1:{PORT}/"
    )
    print(
        "Portal :",
        PORTAL,
    )
    print(
        "Import JIRA :",
        JIRA_IMPORT,
        "OK" if JIRA_IMPORT.exists() else "ABSENT",
    )
    print()

    ThreadingHTTPServer(
        ("127.0.0.1", PORT),
        Handler,
    ).serve_forever()
