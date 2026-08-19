from pathlib import Path
import argparse
import datetime as dt
import re

ROOT = Path(__file__).resolve().parents[1]
COMMUN = ROOT / "commun"

parser = argparse.ArgumentParser()
parser.add_argument("--bootstrap", action="store_true")
parser.add_argument("--after-import", action="store_true")
args = parser.parse_args()

HTML_FILES = [
    COMMUN / "dashboard_gil.html",
    COMMUN / "dashboard_gil_sprint21.html",
]


def inject_once(html: str, script_id: str, script: str) -> str:
    html = re.sub(
        r'\n?<script id="' + re.escape(script_id) + r'">[\s\S]*?</script>\n?',
        "\n",
        html,
        flags=re.S,
    )

    if "</body>" in html:
        return html.replace("</body>", script + "\n</body>", 1)

    return html + "\n" + script


def inject_build_stamp(html: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")

    html = re.sub(
        r'\n?<meta name="gil-build-stamp" content="[^"]*">\n?',
        "\n",
        html,
        flags=re.S,
    )

    meta = f'<meta name="gil-build-stamp" content="{stamp}">'

    if "</head>" in html:
        return html.replace("</head>", meta + "\n</head>", 1)

    return meta + "\n" + html


STABLE_FALLBACK = r"""
<script id="stableFallbackLoader">
(function(){
  if (window.__gilStableFallbackInstalled) return;
  window.__gilStableFallbackInstalled = true;

  function renderFallback(){
    try {
      if (typeof fallbackData === "undefined") return;
      if (typeof render !== "function") return;
      window.currentData = fallbackData;
      render(window.currentData);
    } catch(e) {
      console.error("[GIL] rendu fallbackData impossible", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function(){
      setTimeout(renderFallback, 0);
      setTimeout(renderFallback, 300);
    });
  } else {
    setTimeout(renderFallback, 0);
    setTimeout(renderFallback, 300);
  }

  window.__gilRenderFallback = renderFallback;
})();
</script>
"""


AUTO_RELOAD = r"""
<script id="autoReloadAfterActionScript">
(function(){
  if (window.__gilAutoReloadPollingInstalled) return;
  window.__gilAutoReloadPollingInstalled = true;

  var meta = document.querySelector('meta[name="gil-build-stamp"]');
  var currentStamp = meta ? (meta.getAttribute("content") || "") : "";
  var startedAt = Date.now();

  function extractStamp(text) {
    var m = String(text || "").match(/<meta name="gil-build-stamp" content="([^"]+)"/);
    return m ? m[1] : "";
  }

  function reloadDashboard() {
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("_gil_refresh", String(Date.now()));
      window.location.replace(url.toString());
    } catch(e) {
      window.location.reload();
    }
  }

  function poll() {
    if (Date.now() - startedAt > 60 * 60 * 1000) return;

    fetch(window.location.pathname + "?_gil_poll=" + Date.now(), { cache: "no-store" })
      .then(function(r){ return r.text(); })
      .then(function(text){
        var nextStamp = extractStamp(text);

        if (nextStamp && currentStamp && nextStamp !== currentStamp) {
          reloadDashboard();
          return;
        }

        setTimeout(poll, 2000);
      })
      .catch(function(){
        setTimeout(poll, 3000);
      });
  }

  setTimeout(poll, 2000);
})();
</script>
"""


COMPARISON_FALLBACK = r"""
<script id="jiraOfficialComparisonFallbackScript">
(function(){
  if (window.__gilJiraComparisonFallbackInstalled) return;
  window.__gilJiraComparisonFallbackInstalled = true;

  function n(value) {
    var x = Number(value);
    return Number.isFinite(x) ? x : 0;
  }

  function pick(row) {
    if (!row || typeof row !== "object") return 0;
    for (var i = 1; i < arguments.length; i++) {
      var key = arguments[i];
      if (row[key] !== undefined && row[key] !== null && row[key] !== "") {
        return n(row[key]);
      }
    }
    return 0;
  }

  function rowsFromPayload(data) {
    if (!data || typeof data !== "object") return [];

    var rows = data.comparaisonSprintsJiraOfficielle || data.comparaisonSprints || [];

    if ((!Array.isArray(rows) || rows.length < 2) && data.diagnosticSprintsJira) {
      var d = data.diagnosticSprintsJira;
      rows = [];

      if (d.precedent) {
        rows.push({
          sprint: d.precedent.nom || d.precedent.name || data.sprintPrecedent || "Sprint précédent",
          total: d.precedent.total,
          flux: d.precedent.flux,
          anomalies: d.precedent.anomalies
        });
      }

      if (d.courant) {
        rows.push({
          sprint: d.courant.nom || d.courant.name || data.sprintCourant || "Sprint courant",
          total: d.courant.total,
          flux: d.courant.flux,
          anomalies: d.courant.anomalies
        });
      }
    }

    if (!Array.isArray(rows)) return [];

    return rows.slice(0, 2).map(function(r){
      var total = pick(r, "total", "flux", "demandesTotal", "totalDemandes", "fluxTotal", "totalFlux");
      var flux = pick(r, "flux", "demandes", "demandesTotal", "fluxTotal", "totalFlux");
      var anomalies = pick(r, "anomalies", "bugs", "defauts");

      if (!total) total = flux + anomalies;

      return {
        sprint: r.sprint || r.nom || r.label || r.name || "",
        total: total,
        flux: flux || total,
        anomalies: anomalies
      };
    });
  }

  function findComparisonSection() {
    var titles = Array.prototype.slice.call(document.querySelectorAll("h1,h2,h3,summary"));
    for (var i = 0; i < titles.length; i++) {
      var txt = (titles[i].textContent || "").toLowerCase();
      if (txt.indexOf("comparaison") >= 0) {
        return titles[i].parentElement || titles[i];
      }
    }
    return document.body;
  }

  function renderComparison() {
    try {
      var data = window.currentData || window.fallbackData;
      var rows = rowsFromPayload(data);
      if (!rows.length) return;

      var max = Math.max.apply(null, rows.map(function(r){ return r.total || 0; }));
      if (!max) return;

      var section = findComparisonSection();
      if (!section) return;

      var old = document.getElementById("jiraOfficialComparisonFallback");
      if (old) old.remove();

      var block = document.createElement("div");
      block.id = "jiraOfficialComparisonFallback";
      block.style.margin = "16px 0";
      block.style.padding = "14px";
      block.style.border = "1px solid #d0d7de";
      block.style.borderRadius = "10px";
      block.style.background = "#fff";

      var html = "";
      html += '<h3 style="margin:0 0 10px 0;">Comparaison officielle Jira Agile</h3>';
      html += '<div style="font-size:13px;margin-bottom:10px;color:#555;">Source : sprints Jira officiels détectés via board Agile.</div>';

      rows.forEach(function(r){
        var width = Math.max(3, Math.round((r.total / max) * 100));
        html += '<div style="margin:10px 0;">';
        html += '<div style="display:flex;justify-content:space-between;font-weight:600;">';
        html += '<span>' + r.sprint + '</span>';
        html += '<span>Total ' + r.total + ' | Flux ' + r.flux + ' | Anomalies ' + r.anomalies + '</span>';
        html += '</div>';
        html += '<div style="height:22px;background:#eef2f7;border-radius:999px;overflow:hidden;margin-top:5px;">';
        html += '<div style="height:22px;width:' + width + '%;background:#2563eb;border-radius:999px;"></div>';
        html += '</div>';
        html += '</div>';
      });

      block.innerHTML = html;
      section.appendChild(block);
    } catch(e) {
      console.error("[GIL] comparaison officielle Jira non rendue", e);
    }
  }

  function schedule() {
    setTimeout(renderComparison, 0);
    setTimeout(renderComparison, 500);
    setTimeout(renderComparison, 1500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", schedule);
  } else {
    schedule();
  }

  window.__gilRenderJiraOfficialComparison = renderComparison;
})();
</script>
"""


def patch_html(path: Path) -> bool:
    if not path.exists():
        return False

    html = path.read_text(encoding="utf-8", errors="replace")
    html = inject_build_stamp(html)
    html = inject_once(html, "stableFallbackLoader", STABLE_FALLBACK)
    html = inject_once(html, "autoReloadAfterActionScript", AUTO_RELOAD)
    html = inject_once(html, "jiraOfficialComparisonFallbackScript", COMPARISON_FALLBACK)

    path.write_text(html, encoding="utf-8")
    return True


def main():
    done = []

    for path in HTML_FILES:
        if patch_html(path):
            done.append(str(path.relative_to(ROOT)))

    if not done:
        raise SystemExit("[ERREUR] Aucun HTML dashboard trouvé à préparer.")

    print("[OK] Dashboard runtime préparé :")
    for item in done:
        print(" -", item)


if __name__ == "__main__":
    main()
