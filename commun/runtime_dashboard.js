(function () {
  if (window.__gilRuntimeDashboardInstalled) return;
  window.__gilRuntimeDashboardInstalled = true;

  function numberValue(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function pick(row) {
    if (!row || typeof row !== "object") return 0;
    for (var i = 1; i < arguments.length; i++) {
      var key = arguments[i];
      if (row[key] !== undefined && row[key] !== null && row[key] !== "") {
        return numberValue(row[key]);
      }
    }
    return 0;
  }

  function readInjectedRows() {
    var el = document.getElementById("jiraOfficialSprintRowsData");
    if (!el) return [];
    try {
      var rows = JSON.parse(el.textContent || "[]");
      return Array.isArray(rows) ? rows : [];
    } catch (e) {
      console.error("[GIL] Lecture jiraOfficialSprintRowsData impossible", e);
      return [];
    }
  }

  function rowsFromPayload() {
    var data = window.currentData || window.fallbackData;
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

    return Array.isArray(rows) ? rows : [];
  }

  function normalizeRows(rows) {
    return rows.slice(0, 2).map(function (r) {
      var total = pick(r, "total", "flux", "demandesTotal", "totalDemandes", "fluxTotal", "totalFlux");
      var flux = pick(r, "flux", "demandes", "demandesTotal", "fluxTotal", "totalFlux");
      var anomalies = pick(r, "anomalies", "bugs", "defauts");

      if (!total) total = flux + anomalies;
      if (!flux) flux = total;

      return {
        sprint: r.sprint || r.nom || r.label || r.name || "",
        total: total,
        flux: flux,
        anomalies: anomalies
      };
    }).filter(function (r) {
      return r.sprint && r.total > 0;
    });
  }

  function findComparisonSection() {
    var titles = Array.prototype.slice.call(document.querySelectorAll("h1,h2,h3,summary,div"));

    for (var i = 0; i < titles.length; i++) {
      var text = (titles[i].textContent || "").toLowerCase();
      if (text.indexOf("comparaison sprint") >= 0 || text.indexOf("comparaison") >= 0) {
        return titles[i].parentElement || titles[i];
      }
    }

    return document.body;
  }

  function renderOfficialComparison() {
    try {
      var rows = normalizeRows(readInjectedRows());

      if (!rows.length) {
        rows = normalizeRows(rowsFromPayload());
      }

      if (!rows.length) return;

      var max = Math.max.apply(null, rows.map(function (r) { return r.total || 0; }));
      if (!max) return;

      var old = document.getElementById("jiraOfficialComparisonStatic");
      if (old) old.remove();

      var block = document.createElement("div");
      block.id = "jiraOfficialComparisonStatic";
      block.style.margin = "18px 20px";
      block.style.padding = "16px";
      block.style.border = "1px solid #cbd5e1";
      block.style.borderRadius = "10px";
      block.style.background = "#ffffff";
      block.style.boxShadow = "0 1px 3px rgba(0,0,0,0.08)";

      var html = "";
      html += '<h3 style="margin:0 0 8px 0;font-size:18px;">Comparaison officielle Jira Agile</h3>';
      html += '<div style="font-size:13px;color:#475569;margin-bottom:12px;">Comparaison basée sur les deux derniers sprints officiels détectés via le board Jira Agile.</div>';

      rows.forEach(function (r) {
        var width = Math.max(2, Math.round((r.total / max) * 100));

        html += '<div style="margin:14px 0;">';
        html += '<div style="display:flex;justify-content:space-between;gap:12px;font-weight:700;">';
        html += '<span>' + r.sprint + '</span>';
        html += '<span>Total : ' + r.total + ' | Flux : ' + r.flux + ' | Anomalies : ' + r.anomalies + '</span>';
        html += '</div>';
        html += '<div style="height:24px;background:#e5e7eb;border-radius:999px;overflow:hidden;margin-top:6px;">';
        html += '<div style="height:24px;width:' + width + '%;background:#2563eb;border-radius:999px;"></div>';
        html += '</div>';
        html += '</div>';
      });

      block.innerHTML = html;

      var section = findComparisonSection();
      if (section && section.parentElement) {
        section.parentElement.insertBefore(block, section.nextSibling);
      } else {
        document.body.appendChild(block);
      }
    } catch (e) {
      console.error("[GIL] Comparaison officielle Jira non rendue", e);
    }
  }

  function renderFallbackData() {
    try {
      if (typeof window.fallbackData === "undefined") return;
      if (typeof window.render !== "function") return;
      window.currentData = window.fallbackData;
      window.render(window.currentData);
    } catch (e) {
      console.error("[GIL] Rendu fallbackData impossible", e);
    }
  }

  function installAutoReload() {
    var meta = document.querySelector('meta[name="gil-build-stamp"]');
    var currentStamp = meta ? (meta.getAttribute("content") || "") : "";
    var startedAt = Date.now();

    function extractStamp(text) {
      var match = String(text || "").match(/<meta name="gil-build-stamp" content="([^"]+)"/);
      return match ? match[1] : "";
    }

    function reloadDashboard() {
      try {
        var url = new URL(window.location.href);
        url.searchParams.set("_gil_refresh", String(Date.now()));
        window.location.replace(url.toString());
      } catch (e) {
        window.location.reload();
      }
    }

    function poll() {
      if (Date.now() - startedAt > 60 * 60 * 1000) return;

      fetch(window.location.pathname + "?_gil_poll=" + Date.now(), { cache: "no-store" })
        .then(function (response) { return response.text(); })
        .then(function (text) {
          var nextStamp = extractStamp(text);
          if (nextStamp && currentStamp && nextStamp !== currentStamp) {
            reloadDashboard();
            return;
          }
          setTimeout(poll, 2000);
        })
        .catch(function () {
          setTimeout(poll, 3000);
        });
    }

    setTimeout(poll, 2000);
  }

  function boot() {
    setTimeout(renderFallbackData, 0);
    setTimeout(renderFallbackData, 300);

    setTimeout(renderOfficialComparison, 0);
    setTimeout(renderOfficialComparison, 500);
    setTimeout(renderOfficialComparison, 1500);
    setTimeout(renderOfficialComparison, 3000);

    installAutoReload();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.__gilRenderOfficialSprintComparison = renderOfficialComparison;
})();
