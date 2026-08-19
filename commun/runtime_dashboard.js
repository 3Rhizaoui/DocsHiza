(function () {
  if (window.__gilRuntimeDashboardInstalled) return;
  window.__gilRuntimeDashboardInstalled = true;

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

  function showRuntimeError(title, message) {
    var old = document.getElementById("gilRuntimeError");
    if (old) old.remove();

    var block = document.createElement("div");
    block.id = "gilRuntimeError";
    block.style.margin = "18px 20px";
    block.style.padding = "14px";
    block.style.border = "2px solid #dc2626";
    block.style.borderRadius = "10px";
    block.style.background = "#fef2f2";
    block.style.color = "#7f1d1d";
    block.innerHTML =
      "<div style='font-size:16px;font-weight:700;margin-bottom:6px;'>" + title + "</div>" +
      "<div style='font-size:13px;'>" + message + "</div>";

    var anchor = document.querySelector("#reportTitle") || document.body.firstElementChild || document.body;
    if (anchor && anchor.parentElement) {
      anchor.parentElement.insertBefore(block, anchor.nextSibling);
    } else {
      document.body.insertBefore(block, document.body.firstChild);
    }
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

      var oldText = el.textContent || "";
      var newText = oldText.replace(/Sprint 21/g, courant);

      if (precedent) {
        newText = newText.replace(/Sprint 20/g, precedent);
      }

      if (newText !== oldText) {
        el.textContent = newText;
      }
    });
  }

  function mergeRuntimeData(base, dashboard, courant, precedent, comparaison) {
    var data = Object.assign({}, base || {}, dashboard || {});

    var nomCourant = sprintName(courant, data.sprintCourant);
    var nomPrecedent = sprintName(precedent, data.sprintPrecedent);

    if (nomCourant) data.sprintCourant = nomCourant;
    if (nomPrecedent) data.sprintPrecedent = nomPrecedent;

    data.sprintCourantDetail = courant;
    data.sprintPrecedentDetail = precedent;

    data.comparaisonSprints = comparaison;
    data.comparaisonSprintsJiraOfficielle = comparaison;

    if (data.tendanceHebdo) {
      if (data.tendanceHebdo.current && nomCourant) {
        data.tendanceHebdo.current.sprint = nomCourant;
      }

      if (Array.isArray(data.tendanceHebdo.rows) && data.tendanceHebdo.rows.length && nomCourant) {
        data.tendanceHebdo.rows[data.tendanceHebdo.rows.length - 1].sprint = nomCourant;
      }
    }

    data.architectureJira = {
      chargeeDepuisJsonRuntime: true,
      sprintCourant: !!courant,
      sprintPrecedent: !!precedent,
      comparaison: Array.isArray(comparaison) && comparaison.length >= 2
    };

    return data;
  }

  function renderExistingTemplate(data) {
    window.currentData = data;

    if (typeof window.render === "function") {
      try {
        window.render(data);
      } catch (e) {
        console.error("[GIL] render(data) impossible", e);
      }
    }

    patchTitles(data);
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

      var ok =
        !!dashboard &&
        !!courant &&
        !!precedent &&
        Array.isArray(comparaison) &&
        comparaison.length >= 2;

      if (!ok) {
        showRuntimeError(
          "Architecture sprint Jira incomplète",
          "Les fichiers commun/dashboard_gil_data.json, commun/sprint_courant.json, commun/sprint_precedent.json et commun/comparaison_sprints.json doivent être produits après l'import Jira."
        );
        console.warn("[GIL] Architecture sprint incomplète", {
          dashboard_gil_data: !!dashboard,
          sprint_courant: !!courant,
          sprint_precedent: !!precedent,
          comparaison_sprints: Array.isArray(comparaison) ? comparaison.length : 0
        });
        return;
      }

      var data = mergeRuntimeData(base, dashboard, courant, precedent, comparaison);
      renderExistingTemplate(data);

      console.log("[GIL] Template existant alimenté par JSON runtime", {
        sprintCourant: data.sprintCourant,
        sprintPrecedent: data.sprintPrecedent,
        comparaisonSprints: comparaison.length
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
