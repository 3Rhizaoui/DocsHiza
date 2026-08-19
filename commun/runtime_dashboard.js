(function () {
  if (window.__gilRuntimeDashboardInstalled) return;
  window.__gilRuntimeDashboardInstalled = true;

  function num(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function fetchJson(path) {
    return fetch(path + "?_ts=" + Date.now(), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .catch(function () {
        return null;
      });
  }

  function sprintName(doc, fallback) {
    if (!doc || typeof doc !== "object") return fallback || "";
    if (doc.sprint && doc.sprint.nom) return doc.sprint.nom;
    if (doc.sprint && doc.sprint.name) return doc.sprint.name;
    return doc.nom || doc.name || doc.sprint || doc.label || fallback || "";
  }

  function patchTitles(data) {
    var courant = data && data.sprintCourant ? data.sprintCourant : "";
    var precedent = data && data.sprintPrecedent ? data.sprintPrecedent : "";

    if (!courant) return;

    function replaceText(selector, text) {
      var el = document.querySelector(selector);
      if (el) el.textContent = text;
    }

    replaceText("#reportTitle", "Biweekly GIL - Reporting " + courant);
    replaceText("#gaugeTitle", "Statut du " + courant);
    replaceText("#generalTitle", "Statut général du " + courant);

    var all = Array.prototype.slice.call(document.querySelectorAll("h1,h2,h3,div,span,strong"));
    all.forEach(function (el) {
      if (!el || !el.childNodes || el.childNodes.length !== 1) return;
      var t = el.textContent || "";

      if (t.indexOf("Sprint 21") >= 0) {
        el.textContent = t.replace(/Sprint 21/g, courant);
      }

      if (precedent && t.indexOf("Sprint 20") >= 0) {
        el.textContent = t.replace(/Sprint 20/g, precedent);
      }
    });
  }

  function normalizeComparison(rows) {
    if (!Array.isArray(rows)) return [];

    return rows.slice(0, 2).map(function (r) {
      var total = num(r.total || r.flux || r.demandesTotal || r.totalDemandes || r.fluxTotal || r.totalFlux);
      var flux = num(r.flux || r.demandes || r.demandesTotal || r.fluxTotal || r.totalFlux);
      var anomalies = num(r.anomalies || r.bugs || r.defauts);

      if (!total) total = flux + anomalies;
      if (!flux) flux = total;

      return {
        sprint: r.sprint || r.nom || r.label || r.name || "",
        total: total,
        flux: flux,
        anomalies: anomalies,
        sitTotal: num(r.sitTotal || r.totalSIT || r.fluxSIT || r.SIT),
        uatTotal: num(r.uatTotal || r.totalUAT || r.fluxUAT || r.UAT),
        nonVentile: num(r.nonVentile)
      };
    }).filter(function (r) {
      return r.sprint && r.total > 0;
    });
  }

  function renderOfficialComparison(rows) {
    rows = normalizeComparison(rows);
    if (!rows.length) return;

    var max = Math.max.apply(null, rows.map(function (r) { return r.total; }));
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
    html += '<div style="font-size:13px;color:#475569;margin-bottom:12px;">Source : commun/comparaison_sprints.json</div>';

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

      if (r.nonVentile) {
        html += '<div style="font-size:12px;color:#64748b;margin-top:4px;">Non ventilé : ' + r.nonVentile + '</div>';
      }

      html += '</div>';
    });

    block.innerHTML = html;

    var titles = Array.prototype.slice.call(document.querySelectorAll("h1,h2,h3,summary,div"));
    var anchor = null;

    for (var i = 0; i < titles.length; i++) {
      var text = (titles[i].textContent || "").toLowerCase();
      if (text.indexOf("comparaison") >= 0) {
        anchor = titles[i].parentElement || titles[i];
        break;
      }
    }

    if (anchor && anchor.parentElement) {
      anchor.parentElement.insertBefore(block, anchor.nextSibling);
    } else {
      document.body.appendChild(block);
    }
  }

  function mergeRuntimeData(base, dashboard, courant, precedent, comparaison) {
    var data = Object.assign({}, base || {}, dashboard || {});

    var nomCourant = sprintName(courant, data.sprintCourant);
    var nomPrecedent = sprintName(precedent, data.sprintPrecedent);

    if (nomCourant) data.sprintCourant = nomCourant;
    if (nomPrecedent) data.sprintPrecedent = nomPrecedent;

    if (courant) data.sprintCourantDetail = courant;
    if (precedent) data.sprintPrecedentDetail = precedent;

    if (Array.isArray(comparaison) && comparaison.length) {
      data.comparaisonSprints = comparaison;
      data.comparaisonSprintsJiraOfficielle = comparaison;
    }

    data.architectureJira = {
      chargeeDepuisJsonRuntime: true,
      dashboard: !!dashboard,
      sprintCourant: !!courant,
      sprintPrecedent: !!precedent,
      comparaison: Array.isArray(comparaison) && comparaison.length > 0
    };

    if (data.tendanceHebdo) {
      if (data.tendanceHebdo.current && nomCourant) {
        data.tendanceHebdo.current.sprint = nomCourant;
      }

      if (Array.isArray(data.tendanceHebdo.rows) && data.tendanceHebdo.rows.length && nomCourant) {
        data.tendanceHebdo.rows[data.tendanceHebdo.rows.length - 1].sprint = nomCourant;
      }
    }

    return data;
  }

  function renderData(data) {
    window.currentData = data;

    if (typeof window.render === "function") {
      try {
        window.render(data);
      } catch (e) {
        console.error("[GIL] render(data) impossible", e);
      }
    }

    patchTitles(data);

    if (Array.isArray(data.comparaisonSprintsJiraOfficielle)) {
      renderOfficialComparison(data.comparaisonSprintsJiraOfficielle);
    } else if (Array.isArray(data.comparaisonSprints)) {
      renderOfficialComparison(data.comparaisonSprints);
    }
  }

  function loadRuntimeJsonsAndRender() {
    var base = window.fallbackData || window.currentData || {};

    return Promise.all([
      fetchJson("dashboard_gil_data.json"),
      fetchJson("sprint_courant.json"),
      fetchJson("sprint_precedent.json"),
      fetchJson("comparaison_sprints.json")
    ]).then(function (values) {
      var dashboard = values[0];
      var courant = values[1];
      var precedent = values[2];
      var comparaison = values[3];

      var data = mergeRuntimeData(base, dashboard, courant, precedent, comparaison);
      renderData(data);

      console.log("[GIL] JSON runtime chargés", {
        dashboard_gil_data: !!dashboard,
        sprint_courant: !!courant,
        sprint_precedent: !!precedent,
        comparaison_sprints: Array.isArray(comparaison) ? comparaison.length : 0,
        sprintCourant: data.sprintCourant,
        sprintPrecedent: data.sprintPrecedent
      });
    });
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
    if (window.fallbackData) {
      renderData(window.fallbackData);
    }

    setTimeout(loadRuntimeJsonsAndRender, 0);
    setTimeout(loadRuntimeJsonsAndRender, 1000);
    setTimeout(loadRuntimeJsonsAndRender, 3000);

    installAutoReload();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.__gilLoadRuntimeJsonsAndRender = loadRuntimeJsonsAndRender;
})();
