
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
          class="gilGlobalHeaderGil"
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
        src="${assetUrl("IT GROUPE.png")}"
        alt="IT GROUP"
      >

      <div class="gilGlobalHeaderBrand">

        <img
          class="gilGlobalFooterBrand gilGlobalFooterItms"
          src="${assetUrl("ITMS.png")}"
          alt="ITMS - AN IT GROUP COMPANY"
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


/* ==========================================================
   GIL_FIXED_CORNER_BRANDING_V3

   Réutilise STRICTEMENT le shell existant.
   Aucun position:fixed.
   Aucun nouveau header/footer.

   Haut gauche : BNP
   Haut droite : GIL
   Bas gauche  : IT GROUP
   Bas droite  : ITMS
   ========================================================== */

(function () {

  "use strict";

  function assetBase() {

    const scripts =
      Array.from(
        document.querySelectorAll(
          'script[src*="gil-global-shell.js"]'
        )
      );

    const script =
      scripts[scripts.length - 1];

    if (
      script &&
      script.src
    ) {
      return new URL(
        ".",
        script.src
      );
    }

    return null;
  }


  function setImage(
    img,
    base,
    file,
    alt
  ) {

    if (
      !img ||
      !base
    ) {
      return;
    }

    img.src =
      new URL(
        file,
        base
      ).href;

    img.alt =
      alt;
  }


  function applyBranding() {

    const base =
      assetBase();

    if (!base) {
      return;
    }


    /*
     * ========================================================
     * HEADER
     *
     * On cherche uniquement les anciennes images GHOST
     * utilisées par le shell.
     *
     * Elles deviennent GIL.
     * ========================================================
     */

    document
      .querySelectorAll(
        'img[src*="ghost_logo.png"]'
      )
      .forEach(img => {

        /*
         * Si l'image est dans un footer,
         * elle sera traitée plus bas en ITMS.
         */
        if (
          img.closest(
            'footer, [class*="Footer"], [class*="footer"]'
          )
        ) {
          return;
        }

        setImage(
          img,
          base,
          "gil_logo.png",
          "GIL - Group Integration Layer"
        );

      });


    /*
     * ========================================================
     * FOOTERS
     * ========================================================
     */

    const footers =
      document.querySelectorAll(
        'footer, [class*="Footer"], [class*="footer"]'
      );


    footers.forEach(footer => {

      const images =
        Array.from(
          footer.querySelectorAll("img")
        );


      /*
       * BNP du footer -> IT GROUP
       */
      const bnp =
        images.find(img =>
          String(
            img.getAttribute("src") || ""
          )
          .toLowerCase()
          .includes("bnpp_logo")
        );

      if (bnp) {

        setImage(
          bnp,
          base,
          "IT GROUPE.png",
          "IT GROUP"
        );

      }


      /*
       * GHOST du footer -> ITMS
       */
      const ghost =
        images.find(img =>
          String(
            img.getAttribute("src") || ""
          )
          .toLowerCase()
          .includes("ghost_logo")
        );

      if (ghost) {

        setImage(
          ghost,
          base,
          "ITMS.png",
          "ITMS - AN IT GROUP COMPANY"
        );

      }

    });

  }


  /*
   * Le shell peut être créé dynamiquement.
   * On applique après DOMContentLoaded puis une seconde fois
   * juste après pour couvrir l'injection du shell.
   */

  function init() {

    applyBranding();

    window.setTimeout(
      applyBranding,
      0
    );

    window.setTimeout(
      applyBranding,
      150
    );

  }


  if (
    document.readyState ===
    "loading"
  ) {

    document.addEventListener(
      "DOMContentLoaded",
      init
    );

  } else {

    init();

  }

})();
