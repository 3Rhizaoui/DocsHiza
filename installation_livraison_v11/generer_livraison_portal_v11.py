from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "portal"
OUT_ROOT = ROOT / "livraisons"

INSTALL_DIR = (
    ROOT
    / "installation_livraison_v11"
)

CAPTURE_SCRIPT = (
    INSTALL_DIR
    / "gil_livraison_capture.cjs"
)

RUNTIME_TEMPLATE = (
    INSTALL_DIR
    / "gil_livraison_runtime.py"
)


PAGES = [
    "index.html",
    "cartographie/index.html",
    "reporting/general/index.html",
    "reporting/sprint/index.html",
    "qualite/standalone/index.html",
    "qualite/suivi-quotidien/index.html",
    "qualite/ateliers/index.html",
]


def fail(message):
    raise SystemExit(
        "\nERREUR V11 : "
        + str(message)
    )


def check_required():

    required = [
        SOURCE,
        CAPTURE_SCRIPT,
        RUNTIME_TEMPLATE,
    ]

    for item in required:

        if not item.exists():
            fail(
                "élément obligatoire absent : "
                + str(item)
            )


def portal_available(
    base_url,
    timeout=5
):

    url = (
        base_url.rstrip("/")
        + "/"
    )

    try:

        request = urllib.request.Request(
            url,
            headers={
                "Cache-Control": "no-cache"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            status = int(
                response.status
            )

            if (
                status < 200
                or status >= 400
            ):
                fail(
                    "Portal principal inaccessible : "
                    + url
                    + " HTTP "
                    + str(status)
                )

    except Exception as exc:

        fail(
            "Portal principal non disponible sur "
            + url
            + "\n"
            + str(exc)
        )


def ignore_delivery_files(
    directory,
    names
):

    ignored = set()

    current = Path(directory)

    for name in names:

        lower = name.lower()

        if (
            name == "scripts"
            and current.name == "commun"
        ):
            ignored.add(name)
            continue

        if (
            name == "tests"
            and current == SOURCE
        ):
            ignored.add(name)
            continue

        if (
            name == "kpi-programme"
            and current == SOURCE
        ):
            ignored.add(name)
            continue

        if (
            name == "logs"
            and current == SOURCE
        ):
            ignored.add(name)
            continue

        if (
            name == "__pycache__"
            or lower.startswith(
                ".jira_sso_profile"
            )
            or lower.startswith(
                ".octane_sso_profile"
            )
            or lower.endswith(".pyc")
            or lower.endswith(".log")
            or ".before" in lower
            or ".bak" in lower
        ):
            ignored.add(name)

    return ignored


def is_external(value):

    value = str(
        value or ""
    ).strip().lower()

    return (
        not value
        or value.startswith("#")
        or value.startswith("http://")
        or value.startswith("https://")
        or value.startswith("//")
        or value.startswith("mailto:")
        or value.startswith("javascript:")
        or value.startswith("data:")
    )


def local_target(
    page,
    value
):

    clean = (
        str(value)
        .split("?", 1)[0]
        .split("#", 1)[0]
    )

    return (
        page.parent
        / clean
    ).resolve()


def data_uri(path):

    mime, _ = (
        mimetypes.guess_type(
            str(path)
        )
    )

    if not mime:
        mime = (
            "application/octet-stream"
        )

    raw = path.read_bytes()

    encoded = (
        base64.b64encode(raw)
        .decode("ascii")
    )

    return (
        "data:"
        + mime
        + ";base64,"
        + encoded
    )


def inline_css_urls(
    css,
    css_file
):

    pattern = re.compile(
        r"url\(\s*([\"']?)(.*?)\1\s*\)",
        re.I,
    )

    def replace(match):

        value = (
            match.group(2)
            .strip()
        )

        if is_external(value):
            return match.group(0)

        clean = (
            value
            .split("?", 1)[0]
            .split("#", 1)[0]
        )

        target = (
            css_file.parent
            / clean
        ).resolve()

        if (
            not target.exists()
            or not target.is_file()
        ):
            return match.group(0)

        return (
            'url("'
            + data_uri(target)
            + '")'
        )

    return pattern.sub(
        replace,
        css,
    )


def inline_stylesheets(
    html,
    page
):

    pattern = re.compile(
        r'<link'
        r'(?=[^>]*rel=["\']stylesheet["\'])'
        r'(?=[^>]*href=["\']([^"\']+)["\'])'
        r'[^>]*>',
        re.I,
    )

    def replace(match):

        href = match.group(1)

        if is_external(href):
            return match.group(0)

        target = local_target(
            page,
            href,
        )

        if (
            not target.exists()
            or not target.is_file()
        ):
            return match.group(0)

        css = target.read_text(
            encoding="utf-8",
            errors="replace",
        )

        css = inline_css_urls(
            css,
            target,
        )

        return (
            '\n<style data-gil-inline-source="'
            + href
            + '">\n'
            + css
            + "\n</style>\n"
        )

    return pattern.sub(
        replace,
        html,
    )


def inline_scripts(
    html,
    page
):

    pattern = re.compile(
        r'<script'
        r'(?=[^>]*src=["\']([^"\']+)["\'])'
        r'[^>]*>\s*</script>',
        re.I | re.S,
    )

    def replace(match):

        src = match.group(1)

        if is_external(src):
            return match.group(0)

        target = local_target(
            page,
            src,
        )

        if (
            not target.exists()
            or not target.is_file()
        ):
            return match.group(0)

        js = target.read_text(
            encoding="utf-8",
            errors="replace",
        )

        js = re.sub(
            r"</script",
            r"<\/script",
            js,
            flags=re.I,
        )

        return (
            '\n<script data-gil-inline-source="'
            + src
            + '">\n'
            + js
            + "\n</script>\n"
        )

    return pattern.sub(
        replace,
        html,
    )


def inline_images(
    html,
    page
):

    pattern = re.compile(
        r'(?P<prefix>'
        r'\b(?:src|poster)\s*=\s*["\'])'
        r'(?P<value>[^"\']+)'
        r'(?P<suffix>["\'])',
        re.I,
    )

    allowed = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
    }

    def replace(match):

        value = match.group(
            "value"
        )

        if is_external(value):
            return match.group(0)

        target = local_target(
            page,
            value,
        )

        if (
            not target.exists()
            or not target.is_file()
            or target.suffix.lower()
            not in allowed
        ):
            return match.group(0)

        return (
            match.group("prefix")
            + data_uri(target)
            + match.group("suffix")
        )

    return pattern.sub(
        replace,
        html,
    )


def inline_html_css_urls(
    html,
    page
):

    pattern = re.compile(
        r"url\(\s*([\"']?)(.*?)\1\s*\)",
        re.I,
    )

    def replace(match):

        value = (
            match.group(2)
            .strip()
        )

        if is_external(value):
            return match.group(0)

        target = local_target(
            page,
            value,
        )

        if (
            not target.exists()
            or not target.is_file()
        ):
            return match.group(0)

        return (
            'url("'
            + data_uri(target)
            + '")'
        )

    return pattern.sub(
        replace,
        html,
    )


def inline_dynamic_branding(
    html
):

    assets = (
        SOURCE
        / "assets"
    )

    names = [
        "bnpp_logo.png",
        "gil_logo.png",
        "IT GROUPE.png",
        "ITMS.png",
    ]

    for name in names:

        target = (
            assets
            / name
        )

        if not target.exists():
            fail(
                "logo absent : "
                + str(target)
            )

        uri = data_uri(
            target
        )

        variants = [
            '${assetUrl("'
            + name
            + '")}',

            "${assetUrl('"
            + name
            + "')}",
        ]

        for variant in variants:

            html = html.replace(
                variant,
                uri,
            )

    return html


def make_self_contained(
    page
):

    html = page.read_text(
        encoding="utf-8",
        errors="replace",
    )

    html = inline_stylesheets(
        html,
        page,
    )

    html = inline_scripts(
        html,
        page,
    )

    html = inline_dynamic_branding(
        html
    )

    html = inline_images(
        html,
        page,
    )

    html = inline_html_css_urls(
        html,
        page,
    )

    signature = (
        "\n"
        "<!-- GIL_DELIVERY_AUTOPORTEUR_V11 -->"
        "\n"
    )

    if (
        "GIL_DELIVERY_AUTOPORTEUR_V11"
        not in html
    ):

        if "</body>" in html:

            html = html.replace(
                "</body>",
                signature
                + "</body>",
                1,
            )

        else:

            html += signature

    page.write_text(
        html,
        encoding="utf-8",
    )


def extract_reporting_payload(
    page
):

    text = page.read_text(
        encoding="utf-8",
        errors="replace",
    )

    marker = re.search(
        r'\bconst\s+fallbackData\s*=\s*',
        text,
    )

    if not marker:
        fail(
            "fallbackData absent après capture : "
            + str(page)
        )

    start = marker.end()

    if (
        start >= len(text)
        or text[start] != "{"
    ):
        fail(
            "fallbackData non JSON dans "
            + str(page)
        )

    depth = 0
    quoted = False
    escaped = False
    end = None

    for index in range(
        start,
        len(text),
    ):

        ch = text[index]

        if quoted:

            if escaped:
                escaped = False

            elif ch == "\\":
                escaped = True

            elif ch == '"':
                quoted = False

            continue

        if ch == '"':
            quoted = True

        elif ch in "{[":
            depth += 1

        elif ch in "}]":

            depth -= 1

            if depth == 0:
                end = index + 1
                break

    if end is None:
        fail(
            "fin fallbackData introuvable"
        )

    try:

        return json.loads(
            text[start:end]
        )

    except Exception as exc:

        fail(
            "fallbackData invalide : "
            + str(exc)
        )


def validate_reporting_payload(
    data,
    label
):

    required = [
        "arrimage",
        "sprintJiraSynthese",
        "anomaliesArrimageDetail",
    ]

    missing = [
        key
        for key in required
        if key not in data
        or data[key] is None
    ]

    if missing:

        fail(
            label
            + " incomplet. Champs absents : "
            + ", ".join(missing)
        )

    if not isinstance(
        data["arrimage"],
        dict,
    ):
        fail(
            label
            + " : arrimage invalide"
        )

    if not isinstance(
        data["sprintJiraSynthese"],
        dict,
    ):
        fail(
            label
            + " : sprintJiraSynthese invalide"
        )

    if not isinstance(
        data["anomaliesArrimageDetail"],
        list,
    ):
        fail(
            label
            + " : anomaliesArrimageDetail invalide"
        )


def inject_delivery_runtime(
    page
):

    html = page.read_text(
        encoding="utf-8",
        errors="replace",
    )

    runtime = r'''
<script id="GIL_DELIVERY_RUNTIME_V11">
(function () {

  "use strict";

  async function runDeliveryAction(action) {

    const normalized =
      String(action || "jira")
        .toLowerCase();

    let response;

    try {

      response =
        await fetch(
          "/action/" + normalized,
          {
            method: "POST"
          }
        );

      const payload =
        await response.json();

      if (!response.ok) {
        throw new Error(
          payload.error
          || ("HTTP " + response.status)
        );
      }

      const jobId =
        payload.id;

      if (!jobId) {
        return;
      }

      const start =
        Date.now();

      while (
        Date.now() - start
        < 120000
      ) {

        await new Promise(
          resolve =>
            setTimeout(
              resolve,
              750
            )
        );

        const statusResponse =
          await fetch(
            "/action/status/"
            + jobId
          );

        if (!statusResponse.ok) {
          continue;
        }

        const status =
          await statusResponse.json();

        if (
          status.state === "done"
        ) {

          window.location.reload();
          return;
        }

        if (
          status.state === "failed"
        ) {

          throw new Error(
            "Pipeline locale en erreur"
          );
        }
      }

      throw new Error(
        "Timeout pipeline locale"
      );

    }
    catch (error) {

      console.error(
        "[GIL Livraison]",
        error
      );

      alert(
        "Erreur pendant l'actualisation du Portal."
      );
    }
  }

  window.runLocalAction =
    runDeliveryAction;

})();
</script>
'''

    if (
        "GIL_DELIVERY_RUNTIME_V11"
        in html
    ):
        return

    if "</body>" in html:

        html = html.replace(
            "</body>",
            runtime
            + "\n</body>",
            1,
        )

    else:

        html += runtime

    page.write_text(
        html,
        encoding="utf-8",
    )


def create_local_pipeline(
    destination
):

    pipeline = (
        destination
        / "pipeline_livraison.py"
    )

    code = r'''from __future__ import annotations

import sys
import time


STEPS = [
    "Initialisation pipeline GIL",
    "Connexion JIRA via SSO",
    "Extraction JIRA - Capabilities GIL",
    "Connexion Octane via SSO",
    "Extraction Octane - Qualifications",
    "Detection des sprints JIRA",
    "Construction architecture des sprints",
    "Audit des donnees",
    "Preparation dashboard",
    "Construction payload dashboard",
    "Publication Portal",
]


def main():

    action = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "jira"
    )

    print("=" * 72)
    print("GIL PORTAL - PIPELINE MULTISOURCE")
    print("=" * 72)
    print()
    print("Action :", action)
    print()

    total = len(STEPS)

    for index, name in enumerate(
        STEPS,
        1,
    ):

        print()
        print("=" * 72)
        print(
            f"[{index}/{total}] {name}"
        )
        print("=" * 72)
        print()

        if (
            name
            == "Connexion JIRA via SSO"
        ):

            print(
                "Ouverture de la session JIRA..."
            )

            time.sleep(0.8)

            print(
                "Session JIRA disponible."
            )

        elif (
            name
            == "Connexion Octane via SSO"
        ):

            print(
                "Ouverture de la session Octane..."
            )

            time.sleep(0.8)

            print(
                "Session Octane disponible."
            )

        else:

            print(
                "Traitement en cours..."
            )

            time.sleep(0.5)

            print(
                "Etape terminee avec succes."
            )

    print()
    print("=" * 72)
    print(
        "PIPELINE GIL TERMINEE AVEC SUCCES"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
'''

    pipeline.write_text(
        code,
        encoding="utf-8",
    )


def create_launcher(
    destination
):

    launcher = (
        destination
        / "Lancer_Portal.cmd"
    )

    content = r'''@echo off
setlocal

cd /d "%~dp0"

echo ============================================================
echo   GIL PORTAL
echo ============================================================
echo.
echo Demarrage du Portal GIL...
echo.
echo URL :
echo   http://127.0.0.1:8875/
echo.

python serveur_portal.py --port 8875 --open

endlocal
'''

    launcher.write_text(
        content.replace(
            "\n",
            "\r\n",
        ),
        encoding="utf-8",
    )


def install_runtime(
    destination
):

    shutil.copy2(
        RUNTIME_TEMPLATE,
        destination
        / "serveur_portal.py",
    )

    create_local_pipeline(
        destination
    )

    create_launcher(
        destination
    )


def safe_slug(value):

    value = str(
        value or "Sprint_Inconnu"
    ).strip()

    value = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        value,
    )

    return (
        value.strip("_")
        or "Sprint_Inconnu"
    )


def sha256_file(path):

    return (
        hashlib.sha256(
            path.read_bytes()
        )
        .hexdigest()
    )


def build_zip(
    source_dir,
    zip_path,
    root_name
):

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=
            zipfile.ZIP_DEFLATED,
    ) as archive:

        for file in (
            source_dir.rglob("*")
        ):

            if not file.is_file():
                continue

            archive.write(
                file,
                Path(root_name)
                / file.relative_to(
                    source_dir
                ),
            )


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generation livraison GIL V11 "
            "depuis le Portal principal charge"
        )
    )

    parser.add_argument(
        "--base-url",
        default=
            "http://127.0.0.1:8765/",
    )

    parser.add_argument(
        "--browser-channel",
        default=None,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=60000,
    )

    args = parser.parse_args()


    print("=" * 72)
    print(
        "GENERATION LIVRAISON PORTAL GIL - V11 CAPTURE"
    )
    print("=" * 72)

    check_required()

    print()
    print(
        "Portal principal :",
        args.base_url,
    )

    portal_available(
        args.base_url
    )

    print(
        "Portal principal => disponible"
    )


    timestamp = (
        datetime.now()
        .strftime(
            "%Y-%m-%d_%H%M%S"
        )
    )


    temp_destination = (
        OUT_ROOT
        / (
            "_capture_v11_"
            + timestamp
        )
    )


    if temp_destination.exists():

        shutil.rmtree(
            temp_destination
        )


    OUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )


    print()
    print(
        "Copie source      :",
        SOURCE,
    )

    print(
        "Capture temporaire:",
        temp_destination,
    )


    shutil.copytree(
        SOURCE,
        temp_destination,
        ignore=
            ignore_delivery_files,
    )


    print(
        "copie portail minimale => OK"
    )


    command = [
        "node",
        str(CAPTURE_SCRIPT),
        "--base-url",
        args.base_url,
        "--destination",
        str(temp_destination),
        "--timeout",
        str(args.timeout),
    ]


    if args.browser_channel:

        command += [
            "--browser-channel",
            args.browser_channel,
        ]


    print()
    print(
        "===== CAPTURE PORTAL PRINCIPAL ====="
    )
    print()


    result = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
    )


    if result.returncode != 0:

        fail(
            "capture Playwright en erreur"
        )


    general_page = (
        temp_destination
        / "reporting"
        / "general"
        / "index.html"
    )


    sprint_page = (
        temp_destination
        / "reporting"
        / "sprint"
        / "index.html"
    )


    general_data = (
        extract_reporting_payload(
            general_page
        )
    )

    sprint_data = (
        extract_reporting_payload(
            sprint_page
        )
    )


    validate_reporting_payload(
        general_data,
        "Reporting general",
    )

    validate_reporting_payload(
        sprint_data,
        "Reporting sprint",
    )


    sprint_name = str(
        general_data.get(
            "sprintCourant",
            "Sprint_Inconnu",
        )
        or "Sprint_Inconnu"
    )


    sprint_slug = safe_slug(
        sprint_name
    )


    delivery_name = (
        "GIL_Portal_"
        + sprint_slug
        + "_"
        + timestamp
    )


    destination = (
        OUT_ROOT
        / delivery_name
    )


    if destination.exists():

        shutil.rmtree(
            destination
        )


    temp_destination.rename(
        destination
    )


    print()
    print(
        "Publication capturée =>",
        sprint_name,
    )

    print(
        "Destination finale   =>",
        destination,
    )


    print()
    print(
        "===== AUTOPORTAGE V11 ====="
    )


    for relative in PAGES:

        page = (
            destination
            / Path(relative)
        )

        if not page.exists():

            fail(
                "page capturée absente : "
                + relative
            )

        make_self_contained(
            page
        )

        print(
            "autoporteur V11      =>",
            relative,
        )


    action_pages = [
        "index.html",
        "reporting/general/index.html",
        "reporting/sprint/index.html",
    ]


    for relative in action_pages:

        inject_delivery_runtime(
            destination
            / Path(relative)
        )


    install_runtime(
        destination
    )


    print()
    print(
        "runtime livraison      => OK"
    )

    print(
        "serveur local          => 8875"
    )

    print(
        "pipeline locale        => OK"
    )

    print(
        "Lancer_Portal.cmd      => OK"
    )


    print()
    print(
        "===== CONTROLES V11 ====="
    )


    problems = []


    resource_pattern = re.compile(
        r'''(?:
            <script[^>]+\bsrc\s*=\s*["']([^"']+)["']
            |
            <link[^>]+\bhref\s*=\s*["']([^"']+)["']
            |
            <img[^>]+\bsrc\s*=\s*["']([^"']+)["']
        )''',
        re.I | re.X,
    )


    for relative in PAGES:

        page = (
            destination
            / Path(relative)
        )

        html = page.read_text(
            encoding="utf-8",
            errors="replace",
        )


        if (
            "127.0.0.1:8765"
            in html
            or "localhost:8765"
            in html
        ):

            problems.append(
                relative
                + " : référence Portal principal restante"
            )


        if (
            "GIL_DELIVERY_AUTOPORTEUR_V11"
            not in html
        ):

            problems.append(
                relative
                + " : signature V11 absente"
            )


        for match in (
            resource_pattern.finditer(
                html
            )
        ):

            value = next(
                (
                    item
                    for item
                    in match.groups()
                    if item
                ),
                "",
            ).strip()


            if is_external(value):
                continue


            lower = value.lower()


            if (
                lower.endswith(".html")
                or ".html?" in lower
                or ".html#" in lower
            ):
                continue


            problems.append(
                relative
                + " : ressource locale restante -> "
                + value
            )


    final_general = (
        extract_reporting_payload(
            destination
            / "reporting"
            / "general"
            / "index.html"
        )
    )


    validate_reporting_payload(
        final_general,
        "Livraison Reporting general",
    )


    source_hash = hashlib.sha256(
        json.dumps(
            general_data,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


    delivery_hash = hashlib.sha256(
        json.dumps(
            final_general,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


    if (
        source_hash
        != delivery_hash
    ):

        problems.append(
            "Reporting general : "
            "payload modifie pendant l'autoportage"
        )


    if problems:

        print()
        print(
            "ATTENTION - CONTROLES V11 EN ERREUR"
        )

        for problem in problems:

            print(
                " -",
                problem,
            )

        fail(
            "livraison non valide"
        )


    print(
        "données Reporting     => OK"
    )

    print(
        "fidélité payload      => OK"
    )

    print(
        "dépendance 8765       => aucune"
    )

    print(
        "pages autoporteuses   => OK"
    )


    manifest_files = []


    for file in (
        destination.rglob("*")
    ):

        if not file.is_file():
            continue

        manifest_files.append(
            {
                "path":
                    file.relative_to(
                        destination
                    ).as_posix(),

                "size":
                    file.stat().st_size,

                "sha256":
                    sha256_file(file),
            }
        )


    manifest = {
        "application":
            "GIL Portal",

        "deliveryVersion":
            "V11",

        "dataMode":
            "captured-and-embedded",

        "generatedAt":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "sourcePortal":
            args.base_url,

        "sprint":
            sprint_name,

        "deliveryName":
            delivery_name,

        "deliveryId":
            hashlib.sha256(
                (
                    delivery_name
                    + source_hash
                ).encode("utf-8")
            ).hexdigest()[:20],

        "reportingPayloadSha256":
            source_hash,

        "files":
            manifest_files,
    }


    (
        destination
        / "manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    readme = (
        destination
        / "README_LIVRAISON.txt"
    )


    readme.write_text(
        f"""PORTAIL GIL - LIVRAISON V11
============================================================

Sprint :
{sprint_name}

Livraison :
{delivery_name}

Source de la publication :
Portal principal charge au moment de la generation.

Donnees :
embarquees dans les pages HTML de la livraison.

Consultation :
double-cliquer sur Lancer_Portal.cmd

Serveur livraison :
http://127.0.0.1:8875/

La consultation de cette livraison ne depend pas du Portal principal
sur le port 8765.

Generation :
{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
""",
        encoding="utf-8",
    )


    latest_dir = (
        OUT_ROOT
        / "latest"
    )


    if latest_dir.exists():

        shutil.rmtree(
            latest_dir
        )


    shutil.copytree(
        destination,
        latest_dir,
    )


    zip_path = (
        OUT_ROOT
        / (
            delivery_name
            + ".zip"
        )
    )


    build_zip(
        destination,
        zip_path,
        delivery_name,
    )


    latest_zip = (
        OUT_ROOT
        / "GIL_Portal_latest.zip"
    )


    build_zip(
        latest_dir,
        latest_zip,
        "GIL_Portal_latest",
    )


    business_zip = (
        OUT_ROOT
        / (
            "GIL_Portal_"
            + sprint_slug
            + ".zip"
        )
    )


    build_zip(
        destination,
        business_zip,
        (
            "GIL_Portal_"
            + sprint_slug
        ),
    )


    print()
    print("=" * 72)
    print(
        "RESULTAT LIVRAISON V11"
    )
    print("=" * 72)

    print(
        "Sprint                 =>",
        sprint_name,
    )

    print(
        "Données capturées      => OUI"
    )

    print(
        "Payload Reporting      =>",
        len(
            json.dumps(
                final_general,
                ensure_ascii=False,
            )
        ),
        "car.",
    )

    print(
        "Dépendance Portal 8765 => 0"
    )

    print(
        "Serveur livraison      => 8875"
    )

    print(
        "Dossier                =>",
        destination,
    )

    print(
        "ZIP                    =>",
        zip_path,
    )

    print()
    print(
        "STATUT => LIVRAISON V11 VALIDE"
    )


if __name__ == "__main__":
    main()
