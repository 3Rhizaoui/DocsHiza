
/* ==========================================================
   GIL BRANDING 4 CORNERS V2
   ========================================================== */

(function () {
  "use strict";

  if (window.__gilUnifiedBrandingV2) {
    return;
  }

  window.__gilUnifiedBrandingV2 = true;

  function assetsBase() {
    const script = document.currentScript;

    if (script && script.src) {
      return new URL(".", script.src);
    }

    return new URL(
      "../../assets/",
      window.location.href
    );
  }

  const base = assetsBase();

  function asset(name) {
    return new URL(name, base).href;
  }

  function createCorner(className, file, alt) {
    const wrapper = document.createElement("div");

    wrapper.className =
      "gilUnifiedBrandCorner " + className;

    const img = document.createElement("img");

    img.src = asset(file);
    img.alt = alt;
    img.loading = "eager";

    wrapper.appendChild(img);
    document.body.appendChild(wrapper);
  }

  function init() {
    if (
      document.querySelector(
        ".gilUnifiedBrandCorner"
      )
    ) {
      return;
    }

    document.body.classList.add(
      "gilUnifiedBrandingActive"
    );

    createCorner(
      "gilUnifiedBrandTopLeft",
      "bnpp_logo.png",
      "BNP Paribas"
    );

    createCorner(
      "gilUnifiedBrandTopRight",
      "gil_logo.png",
      "GIL - Group Integration Layer"
    );

    createCorner(
      "gilUnifiedBrandBottomLeft",
      "IT GROUPE.png",
      "IT GROUP"
    );

    createCorner(
      "gilUnifiedBrandBottomRight",
      "ITMS.png",
      "ITMS - AN IT GROUP COMPANY"
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      init
    );
  } else {
    init();
  }
})();
