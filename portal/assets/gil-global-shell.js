
(function () {

  "use strict";

  const STORAGE_KEY = "gil_show_ghost";


  /*
   * IMPORTANT :
   * capturé immédiatement pendant le chargement
   * du fichier JS.
   *
   * Ainsi les assets sont TOUJOURS cherchés
   * dans portal/assets/, quelle que soit
   * la profondeur de la page courante.
   */
  const SCRIPT_URL =
    document.currentScript &&
    document.currentScript.src
      ? document.currentScript.src
      : null;

  const ASSET_BASE =
    SCRIPT_URL
      ? new URL(".", SCRIPT_URL)
      : null;


  function assetUrl(name) {

    if (ASSET_BASE) {
      return new URL(
        name,
        ASSET_BASE
      ).href;
    }

    return name;
  }


  function getPageSubtitle() {

    const configured =
      document.body.dataset.gilPageTitle;

    if (configured) {
      return configured;
    }

    const h1 =
      document.querySelector("h1");

    if (h1) {
      return h1.textContent.trim();
    }

    return document.title || "Portail GIL";
  }


  function applyGhostPreference() {

    const saved =
      localStorage.getItem(
        STORAGE_KEY
      );

    const visible =
      saved === null
        ? true
        : saved === "1";

    document.body.classList.toggle(
      "gilGhostHidden",
      !visible
    );
  }


  function buildHeader() {

    if (
      document.querySelector(
        ".gilGlobalHeader"
      )
    ) {
      return;
    }

    const header =
      document.createElement(
        "header"
      );

    header.className =
      "gilGlobalHeader";

    header.innerHTML = `
      <div class="gilGlobalHeaderBnp">

        <img
          src="${assetUrl("bnpp_logo.png")}"
          alt="BNP Paribas"
        >

      </div>

      <div class="gilGlobalHeaderCenter">

        <h1 class="gilGlobalHeaderTitle">
          GIL - Group Integration Layer
        </h1>

        <p class="gilGlobalHeaderSubtitle">
          Reporting &amp; Suivi du Projet GIL
        </p>

      </div>

      <div class="gilGlobalHeaderBrand">

        <img
          class="gilGlobalGhost"
          src="${assetUrl("ghost_logo.png")}"
          alt="GHOST - Test & Quality"
        >

        <img
          class="gilGlobalGilReplacement"
          src="${assetUrl("gil_logo.png")}"
          alt="GIL - Group Integration Layer"
        >

      </div>
    `;

    document.body.prepend(
      header
    );
  }


  function buildFooter() {

    if (
      document.querySelector(
        ".gilGlobalFooter"
      )
    ) {
      return;
    }

    const footer =
      document.createElement(
        "footer"
      );

    footer.className =
      "gilGlobalFooter";

    footer.innerHTML = `
      <img
        class="gilGlobalFooterBnp"
        src="${assetUrl("bnpp_logo.png")}"
        alt="BNP Paribas"
      >

      <div class="gilGlobalHeaderBrand">

        <img
          class="gilGlobalFooterBrand gilGlobalGhost"
          src="${assetUrl("ghost_logo.png")}"
          alt="GHOST - Test & Quality"
        >

        <img
          class="gilGlobalFooterBrand gilGlobalGilReplacement"
          src="${assetUrl("gil_logo.png")}"
          alt="GIL - Group Integration Layer"
        >

      </div>
    `;

    document.body.appendChild(
      footer
    );
  }


  function init() {

    document.body.classList.add(
      "gilNormalizedPage"
    );

    applyGhostPreference();

    buildHeader();
    buildFooter();
  }


  if (
    document.readyState === "loading"
  ) {

    document.addEventListener(
      "DOMContentLoaded",
      init
    );

  } else {

    init();
  }

})();
