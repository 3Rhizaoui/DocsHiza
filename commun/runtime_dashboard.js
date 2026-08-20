(function () {
  if (window.__gilRuntimeDashboardInstalled) return;
  window.__gilRuntimeDashboardInstalled = true;

  function fetchJson(path) {
    return fetch(path + "?_ts=" + Date.now(), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error(path + " HTTP " + r.status);
        return r.json();
      });
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

  function renderDashboard(data) {
    window.currentData = data;

    if (typeof window.render === "function") {
      window.render(data);
    }

    patchTitles(data);

    console.log("[GIL] Dashboard alimenté par commun/dashboard_gil_data.json", {
      sprintCourant: data.sprintCourant,
      sprintPrecedent: data.sprintPrecedent,
      santeFluxArrimage: data.santeFluxArrimage,
      comparaisonSprints: Array.isArray(data.comparaisonSprints) ? data.comparaisonSprints.length : 0
    });
  }

  function loadAndRender() {
    fetchJson("dashboard_gil_data.json")
      .then(function (data) {
        if (!data || !data.architectureDashboardFinal) {
          showRuntimeError(
            "Payload dashboard final absent",
            "commun/dashboard_gil_data.json existe, mais il n'est pas le payload final attendu. Relance l'import Jira complet."
          );
          return;
        }

        renderDashboard(data);
      })
      .catch(function (e) {
        showRuntimeError(
          "Chargement dashboard_gil_data.json impossible",
          String(e && e.message ? e.message : e)
        );
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
    setTimeout(loadAndRender, 0);
    setTimeout(loadAndRender, 1000);
    installAutoReload();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.__gilLoadDashboardData = loadAndRender;
})();
