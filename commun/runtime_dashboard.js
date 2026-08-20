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

  function hasUsefulLegacyBlocks(data) {
    if (!data || typeof data !== "object") return false;

    var flux = Array.isArray(data.fluxPretsArrimage) ? data.fluxPretsArrimage.length : 0;
    var histo = Array.isArray(data.histoFlux) ? data.histoFlux.length : 0;
    var comp = Array.isArray(data.comparaisonSprints) ? data.comparaisonSprints.length : 0;

    return flux > 0 && histo > 0 && comp >= 2;
  }

  function hasFinalContract(data) {
    return !!(
      data &&
      typeof data === "object" &&
      data.architectureDashboardFinal &&
      hasUsefulLegacyBlocks(data)
    );
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
    if (!data || typeof data !== "object") return;

    window.currentData = data;

    if (typeof window.render === "function") {
      window.render(data);
    }

    patchTitles(data);

    console.log("[GIL] Dashboard rendu depuis payload final", {
      sprintCourant: data.sprintCourant,
      sprintPrecedent: data.sprintPrecedent,
      fluxPretsArrimage: Array.isArray(data.fluxPretsArrimage) ? data.fluxPretsArrimage.length : 0,
      histoFlux: Array.isArray(data.histoFlux) ? data.histoFlux.length : 0,
      comparaisonSprints: Array.isArray(data.comparaisonSprints) ? data.comparaisonSprints.length : 0
    });
  }

  function loadAndRender() {
    fetchJson("dashboard_gil_data.json")
      .then(function (data) {
        if (!hasFinalContract(data)) {
          console.warn("[GIL] Payload final absent ou incomplet. Rendu HTML existant conservé.", {
            architectureDashboardFinal: !!(data && data.architectureDashboardFinal),
            fluxPretsArrimage: data && Array.isArray(data.fluxPretsArrimage) ? data.fluxPretsArrimage.length : "absent",
            histoFlux: data && Array.isArray(data.histoFlux) ? data.histoFlux.length : "absent",
            comparaisonSprints: data && Array.isArray(data.comparaisonSprints) ? data.comparaisonSprints.length : "absent"
          });

          /*
            Important :
            On ne fait PAS render(data) si le payload final est incomplet.
            Sinon on écrase le dashboard publié avec des tableaux vides.
          */
          return;
        }

        renderDashboard(data);
      })
      .catch(function (e) {
        console.warn("[GIL] dashboard_gil_data.json non chargé. Rendu HTML existant conservé.", e);
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
    /*
      Le HTML legacy rend déjà fallbackData.
      Le runtime ne vient remplacer le rendu que si le payload final est complet.
    */
    setTimeout(loadAndRender, 500);
    installAutoReload();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.__gilLoadDashboardData = loadAndRender;
})();
