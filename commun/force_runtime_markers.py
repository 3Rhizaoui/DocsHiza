from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"

TARGETS = [
    COMMUN / "dashboard_gil.html",
    COMMUN / ("dashboard_gil_" + "sprint21.html"),
]


STABLE_LOADER = r'''
<script id="stableFallbackLoader">
(function () {
  window.stableFallbackLoader = true;

  function getGilPayload() {
    try {
      if (typeof fallbackData !== "undefined") return fallbackData;
    } catch (e) {}

    return window.__GIL_FINAL_PAYLOAD__ || null;
  }

  var data = getGilPayload();

  if (data) {
    window.__GIL_FINAL_PAYLOAD__ = data;
    window.currentData = data;
    window.diagnosticSprintsJira = data.diagnosticSprintsJira || {};
    window.comparaisonOfficielleJira = data.comparaisonOfficielleJira || data.comparaisonSprints || [];
    window.comparaisonSprintsOfficielle = data.comparaisonSprintsOfficielle || data.comparaisonSprints || [];
    window.comparaisonOfficielleInjectee = true;
  }
})();
</script>
'''


AUTO_RELOAD = r'''
<script id="autoReloadAfterActionScript">
(function () {
  window.autoReloadAfterActionScript = true;
  window.__GIL_REFRESH_TOKEN__ = new URLSearchParams(window.location.search).get("_gil_refresh") || "";
})();
</script>
'''


OFFICIAL_COMPARISON = r'''
<script id="officialJiraComparisonMarker">
(function () {
  try {
    var data = window.__GIL_FINAL_PAYLOAD__ || window.currentData || null;
    if (data) {
      window.comparaisonOfficielleJira = data.comparaisonOfficielleJira || data.comparaisonSprints || [];
      window.comparaisonSprintsOfficielle = data.comparaisonSprintsOfficielle || data.comparaisonSprints || [];
      window.comparaisonOfficielleInjectee = true;
    }
  } catch (e) {}
})();
</script>
'''


def add_before_body(html, block):
    if "</body>" in html:
        return html.replace("</body>", block + "\n</body>", 1)
    return html + "\n" + block + "\n"


def patch_file(path):
    if not path.exists():
        print("[WARN] HTML absent :", path)
        return False

    html = path.read_text(encoding="utf-8", errors="replace")
    original = html

    if "stableFallbackLoader" not in html:
        html = add_before_body(html, STABLE_LOADER)

    if "autoReloadAfterActionScript" not in html:
        html = add_before_body(html, AUTO_RELOAD)

    if "comparaisonOfficielleJira" not in html:
        html = add_before_body(html, OFFICIAL_COMPARISON)

    if html != original:
        path.write_text(html, encoding="utf-8")
        print("[OK] Runtime markers injectés :", path)
        return True

    print("[OK] Runtime markers déjà présents :", path)
    return False


def main():
    changed = 0
    for target in TARGETS:
        if patch_file(target):
            changed += 1

    print("[OK] Contrôle runtime markers terminé | fichiers modifiés :", changed)


if __name__ == "__main__":
    main()
