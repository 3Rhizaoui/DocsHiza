#!/usr/bin/env python3
"""Importe plusieurs pages Confluence GIL dans un JSON exploitable par le dashboard.

Le script ne dépend d'aucune bibliothèque externe. Il accepte Confluence Data Center
et Confluence Cloud dès lors que l'API REST classique /rest/api/content est disponible.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import ssl
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_URLS = ROOT / "confluence_urls.txt"
# Le fichier brut est conservé uniquement pour audit/diagnostic. Le lanceur
# fabrique ensuite dashboard_gil_data.json, qui est la source normalisée du site.
DEFAULT_OUTPUT = ROOT / "confluence_brut.json"
DEFAULT_HTML_DIR = ROOT / "captures_confluence"


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def key(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def page_id_from_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    candidates = [parsed.path, parsed.query, parsed.fragment]
    patterns = (
        r"/pages/(\d+)(?:/|$)",
        r"[?&]pageId=(\d+)",
        r"/viewpage\.action\?.*?pageId=(\d+)",
        r"/content/(\d+)(?:/|$)",
    )
    joined = "?".join(candidates)
    for pattern in patterns:
        match = re.search(pattern, joined, re.I)
        if match:
            return match.group(1)
    raise ValueError(f"ID de page introuvable dans l'URL : {url}")


def base_url_from_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL Confluence invalide : {url}")
    path = parsed.path
    context = ""
    for marker in ("/spaces/", "/pages/", "/display/", "/wiki/"):
        if marker in path:
            prefix = path.split(marker, 1)[0]
            context = prefix if prefix and prefix != "/wiki" else ("/wiki" if marker == "/wiki/" else "")
            break
    return f"{parsed.scheme}://{parsed.netloc}{context}".rstrip("/")


@dataclass
class Cell:
    text: str
    links: list[str]
    rowspan: int = 1
    colspan: int = 1


class ConfluenceTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[Cell]]] = []
        self._table_depth = 0
        self._table: list[list[Cell]] | None = None
        self._row: list[Cell] | None = None
        self._cell_parts: list[str] | None = None
        self._cell_links: list[str] = []
        self._rowspan = 1
        self._colspan = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"}:
            self._cell_parts = []
            self._cell_links = []
            self._rowspan = int(attrs_d.get("rowspan") or 1)
            self._colspan = int(attrs_d.get("colspan") or 1)
        elif self._cell_parts is not None and tag == "a" and attrs_d.get("href"):
            self._cell_links.append(str(attrs_d["href"]))
        elif self._cell_parts is not None and tag in {"br", "p", "div", "li"}:
            self._cell_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell_parts is not None:
            assert self._row is not None
            self._row.append(Cell(clean("".join(self._cell_parts)), self._cell_links, self._rowspan, self._colspan))
            self._cell_parts = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            if any(cell.text for cell in self._row):
                assert self._table is not None
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table_depth == 1 and self._table:
                self.tables.append(self._table)
                self._table = None
            self._table_depth = max(0, self._table_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)


def expand_table(rows: list[list[Cell]]) -> list[list[Cell]]:
    grid: list[list[Cell]] = []
    pending: dict[tuple[int, int], Cell] = {}
    for r_idx, row in enumerate(rows):
        out: list[Cell] = []
        c_idx = 0
        for cell in row:
            while (r_idx, c_idx) in pending:
                out.append(pending[(r_idx, c_idx)])
                c_idx += 1
            for dc in range(cell.colspan):
                clone = Cell(cell.text, list(cell.links))
                out.append(clone)
                for dr in range(1, cell.rowspan):
                    pending[(r_idx + dr, c_idx + dc)] = clone
            c_idx += cell.colspan
        while (r_idx, c_idx) in pending:
            out.append(pending[(r_idx, c_idx)])
            c_idx += 1
        grid.append(out)
    width = max((len(row) for row in grid), default=0)
    return [row + [Cell("", []) for _ in range(width - len(row))] for row in grid]


ALIASES = {
    "perimetre": ("perimetre",),
    "demandeur": ("demandeur",),
    "id_flux": ("id flux", "reference flux", "identifiant flux"),
    "description": ("description",),
    "livraison_estreem": ("livraison estreem", "livraison estream"),
    "avro": ("status date de livraison", "date de livraison avro gil", "avro"),
    "configuration": ("configuration du flux", "configuration flux", "configuration"),
    "test_gil": ("test gil standalone", "test interne gil sit qua", "test interne gil"),
    "ouverture_flux": ("ouverture de flux demande saam", "ouverture de flux"),
    "test_connectivite": ("test de connectivite", "test connectivite"),
    "test_integration": ("test d integration", "test integration"),
    "anomalies": ("anomalie octane jira", "octane jira", "anomalie"),
    "commentaire": ("commentaire", "commentaires"),
    "liens_utiles": ("liens utiles", "lien utile"),
}


def find_column(headers: list[str], names: tuple[str, ...]) -> int | None:
    normalized = [key(x) for x in headers]
    for name in names:
        wanted = key(name)
        for idx, header in enumerate(normalized):
            if wanted == header or wanted in header:
                return idx
    return None


def statuses(text: str) -> list[str]:
    upper = key(text).upper()
    rules = (
        ("REFUSE ARCHIVE", "REFUSÉ/ARCHIVÉ"), ("REFUSE", "REFUSÉ"),
        ("TEST NON PLANIFIE", "TEST NON PLANIFIÉ"), ("NON PLANIFIE", "NON PLANIFIÉ"),
        ("TEST EN COURS", "TEST EN COURS"), ("TEST KO", "TEST KO"),
        ("TEST OK", "TEST OK"), ("A FAIRE", "À FAIRE"), ("EN COURS", "EN COURS"),
        ("EN ATTENTE", "EN ATTENTE"), ("DEPLOYE", "DÉPLOYÉ"),
        ("LIVRE", "LIVRÉ"), ("VALIDE", "VALIDÉ"), ("STANDBY", "STANDBY"),
        ("TERMINE", "TERMINÉ"), ("NON APPLICABLE", "NON APPLICABLE"),
    )
    return list(dict.fromkeys(label for token, label in rules if token in upper))


def versions(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\bv?\d+(?:[._]\d+){1,3}\b", text, re.I)))


def references(text: str) -> list[str]:
    patterns = (
        r"\b(?:AERL|OCT|JIRA|INC|DEFECT)[-_ ]?[A-Z0-9]+(?:[-_][A-Z0-9]+)*\b",
        r"\b\d{5,8}\b",
    )
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, re.I))
    return list(dict.fromkeys(clean(x) for x in found))


def infer_domain(title: str, url: str) -> str:
    probe = key(f"{title} {url}")
    if "acquisition" in probe or "acquiring" in probe:
        return "Acquisition"
    if "emission" in probe or "issuing" in probe:
        return "Issuing"
    return clean(title) or "Non déterminé"


def parse_flux_tables(storage_html: str, page: dict, source_url: str) -> tuple[list[dict], list[dict]]:
    parser = ConfluenceTableParser()
    parser.feed(storage_html)
    domain = infer_domain(page.get("title", ""), source_url)
    flux: list[dict] = []
    diagnostics: list[dict] = []

    for table_no, raw_table in enumerate(parser.tables, 1):
        table = expand_table(raw_table)
        header_idx = next((i for i, row in enumerate(table) if any(key(c.text) == "id flux" for c in row)), None)
        if header_idx is None:
            continue
        headers = [cell.text for cell in table[header_idx]]
        columns = {name: find_column(headers, aliases) for name, aliases in ALIASES.items()}
        if columns["id_flux"] is None:
            continue
        diagnostics.append({"table": table_no, "headers": headers, "columns": columns})
        current_subdomain = "Non déterminé"

        for row in table[header_idx + 1:]:
            values = [cell.text for cell in row]
            nonempty = [value for value in values if value]
            flux_idx = int(columns["id_flux"])
            flux_id = clean(values[flux_idx]) if flux_idx < len(values) else ""
            if not flux_id:
                if len(set(nonempty)) == 1 and nonempty:
                    current_subdomain = nonempty[0]
                continue
            if key(flux_id) in {"id flux", "reference flux"}:
                continue
            # Les bandeaux bleus Domaine/Sous-domaine de Confluence sont
            # parfois exportés comme une ligne dont toutes les cellules ont
            # la même valeur (ex. « Authorize »). Ce ne sont pas des flux.
            if nonempty and len({key(value) for value in nonempty}) == 1:
                current_subdomain = nonempty[0]
                continue

            def cell(name: str) -> Cell:
                idx = columns.get(name)
                return row[idx] if idx is not None and idx < len(row) else Cell("", [])

            perimeter = cell("perimetre").text
            subdomain = perimeter or current_subdomain
            raw_fields = {name: cell(name).text for name in ALIASES}
            all_text = " | ".join(raw_fields.values())
            envs = list(dict.fromkeys(re.findall(r"\b(?:SIT|UAT|QUA)\b", all_text, re.I)))
            record = {
                "domaine": domain,
                "sous_domaine": subdomain,
                "reference_flux": flux_id,
                "demandeur": cell("demandeur").text,
                "description": cell("description").text,
                "environnements_detectes": [env.upper() for env in envs],
                "livraison_estreem": cell("livraison_estreem").text,
                "avro": {"valeur": cell("avro").text, "statuts": statuses(cell("avro").text), "versions": versions(cell("avro").text)},
                "configuration": {"valeur": cell("configuration").text, "statuts": statuses(cell("configuration").text), "versions": versions(cell("configuration").text)},
                "test_gil": {"valeur": cell("test_gil").text, "statuts": statuses(cell("test_gil").text)},
                "prerequis_ouverture_flux": {"valeur": cell("ouverture_flux").text, "statuts": statuses(cell("ouverture_flux").text)},
                "test_connectivite": {"valeur": cell("test_connectivite").text, "statuts": statuses(cell("test_connectivite").text)},
                "test_integration": {"valeur": cell("test_integration").text, "statuts": statuses(cell("test_integration").text)},
                "anomalies": {"valeur": cell("anomalies").text, "references": references(cell("anomalies").text)},
                "commentaire": cell("commentaire").text,
                "liens": list(dict.fromkeys(sum((cell(name).links for name in ALIASES), []))),
                "source": {"page_id": str(page.get("id", "")), "titre": page.get("title", ""), "url": source_url, "version": page.get("version", {}).get("number")},
                "brut": raw_fields,
            }
            flux.append(record)
    return flux, diagnostics


def auth_headers() -> dict[str, str]:
    token = os.getenv("CONFLUENCE_TOKEN", "").strip()
    user = os.getenv("CONFLUENCE_USER", "").strip()
    cookie = os.getenv("CONFLUENCE_COOKIE", "").strip()
    headers = {"Accept": "application/json", "User-Agent": "GIL-Confluence-Importer/1.0"}
    if cookie:
        headers["Cookie"] = cookie
    elif token and user:
        encoded = base64.b64encode(f"{user}:{token}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_page(url: str, headers: dict[str, str]) -> dict:
    page_id = page_id_from_url(url)
    base = base_url_from_url(url)
    api_url = f"{base}/rest/api/content/{page_id}?expand=body.storage,version,space"
    request = urllib.request.Request(api_url, headers=headers)
    verify = os.getenv("CONFLUENCE_VERIFY_SSL", "1").lower() not in {"0", "false", "non"}
    context = None if verify else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=60, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Confluence HTTP {exc.code} pour la page {page_id}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connexion impossible à {api_url}: {exc.reason}") from exc


def read_urls(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier d'URL absent : {path}")
    urls = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            urls.append(value)
    if not urls:
        raise ValueError(f"Aucune URL active dans {path}")
    return list(dict.fromkeys(urls))


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Confluence GIL vers JSON")
    parser.add_argument("--urls", type=Path, default=DEFAULT_URLS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--diagnostic", action="store_true", help="Ajoute le mapping des tableaux au JSON")
    parser.add_argument("--html-dir", type=Path, help="Importe les pages HTML capturées par le navigateur SSO")
    args = parser.parse_args()

    urls = read_urls(args.urls)
    headers = auth_headers()
    if not args.html_dir and "Authorization" not in headers and "Cookie" not in headers:
        print("Aucune authentification configurée. Saisissez un PAT/token (il ne sera pas enregistré).")
        token = getpass.getpass("Token Confluence : ").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    pages_summary: list[dict] = []
    all_flux: list[dict] = []
    all_diagnostics: list[dict] = []
    errors: list[dict] = []

    manifest = {}
    if args.html_dir:
        manifest_path = args.html_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    for index, url in enumerate(urls, 1):
        print(f"Import : {url}")
        try:
            if args.html_dir:
                item = next((x for x in manifest.get("pages", []) if x.get("url") == url), None)
                html_path = args.html_dir / (item.get("file") if item else f"page_{index}.html")
                if not html_path.exists():
                    raise FileNotFoundError(f"Capture HTML absente : {html_path}")
                html = html_path.read_text(encoding="utf-8-sig", errors="replace")
                page = {"id": page_id_from_url(url), "title": (item or {}).get("title", html_path.stem)}
            else:
                page = fetch_page(url, headers)
                html = page.get("body", {}).get("storage", {}).get("value", "")
            records, diagnostics = parse_flux_tables(html, page, url)
            pages_summary.append({"id": str(page.get("id", "")), "titre": page.get("title", ""), "url": url, "lignes": len(records)})
            all_flux.extend(records)
            all_diagnostics.append({"url": url, "tables": diagnostics})
            print(f"  {len(records)} flux détectés")
        except Exception as exc:
            errors.append({"url": url, "erreur": str(exc)})
            print(f"  ERREUR : {exc}", file=sys.stderr)

    dedup: dict[tuple[str, str, str], dict] = {}
    for record in all_flux:
        identity = (key(record["domaine"]), key(record["sous_domaine"]), key(record["reference_flux"]))
        dedup[identity] = record

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source_type": "confluence_sso_browser" if args.html_dir else "confluence_api",
        "pages": pages_summary,
        "statistiques": {"pages_demandees": len(urls), "pages_importees": len(pages_summary), "flux": len(dedup), "erreurs": len(errors)},
        "flux": sorted(dedup.values(), key=lambda r: (r["domaine"], r["sous_domaine"], r["reference_flux"])),
        "erreurs": errors,
    }
    if args.diagnostic:
        payload["diagnostic_tables"] = all_diagnostics

    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON produit : {args.output}")
    print(f"Pages : {len(pages_summary)}/{len(urls)} | Flux uniques : {len(dedup)} | Erreurs : {len(errors)}")
    return 0 if pages_summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
