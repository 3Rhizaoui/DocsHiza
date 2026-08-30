/*
 * ============================================================
 * GIL Portal - Données communes
 *
 * Source :
 * commun/data/gil_home.json
 * ============================================================
 */

(function(){

  const DATA_URL =
    "commun/data/gil_home.json";


  function byId(id){
    return document.getElementById(id);
  }


  function text(id, value){

    const el = byId(id);

    if(
      el &&
      value !== undefined &&
      value !== null
    ){
      el.textContent = value;
    }
  }


  function norm(value){

    return String(value || "")
      .normalize("NFD")
      .replace(
        /[\u0300-\u036f]/g,
        ""
      )
      .replace(
        /\s+/g,
        " "
      )
      .trim()
      .toLowerCase();
  }


  /*
   * Recherche défensive d'une carte KPI
   * à partir de son libellé.
   *
   * Utile pour "Flux en cours", qui ne
   * possède pas encore d'id dédié.
   */
  function metricContainer(labelText){

    const target =
      norm(labelText);

    const labels =
      Array.from(
        document.querySelectorAll(
          "span,div"
        )
      );


    const label =
      labels.find(
        el =>
          el.children.length === 0
          &&
          norm(el.textContent)
            === target
      );


    if(!label){
      return null;
    }


    let node =
      label.parentElement;


    for(
      let i = 0;
      i < 6 && node;
      i++
    ){

      const t =
        norm(node.textContent);

      const hasOtherMetric =
        [
          "demandes d'arrimage d'un flux",
          "flux livres",
          "flux en cours"
        ]
        .some(
          x =>
            x !== target
            &&
            t.includes(x)
        );


      if(
        !hasOtherMetric
        &&
        /\d/.test(
          node.textContent || ""
        )
      ){
        return node;
      }


      node =
        node.parentElement;
    }


    return (
      label.parentElement
      || null
    );
  }


  function updateMetricByLabel(
    label,
    value,
    pctValue
  ){

    const container =
      metricContainer(label);

    if(!container){
      return;
    }


    const candidates =
      Array.from(
        container.querySelectorAll(
          "div,span,strong"
        )
      );


    const valueNode =
      candidates.find(
        el =>
          el.children.length === 0
          &&
          /^\s*\d+(?:[.,]\d+)?\s*$/
            .test(
              el.textContent || ""
            )
      );


    if(valueNode){
      valueNode.textContent =
        String(value);
    }


    const pctNode =
      candidates.find(
        el =>
          el.children.length === 0
          &&
          /%\s*$/
            .test(
              el.textContent || ""
            )
      );


    if(
      pctNode
      &&
      pctValue !== undefined
    ){
      pctNode.textContent =
        String(pctValue)
        .replace(".", ",")
        + "%";
    }
  }


  function formatDateTime(value){

    if(!value){
      return "";
    }


    const d =
      new Date(value);


    if(
      Number.isNaN(
        d.getTime()
      )
    ){
      return String(value);
    }


    return d.toLocaleString(
      "fr-FR",
      {
        day:"2-digit",
        month:"2-digit",
        year:"numeric",
        hour:"2-digit",
        minute:"2-digit"
      }
    );
  }


  function formatDate(value){

    if(!value){
      return "";
    }


    const d =
      new Date(value);


    if(
      Number.isNaN(
        d.getTime()
      )
    ){
      return String(value);
    }


    return d.toLocaleDateString(
      "fr-FR"
    );
  }


  function renderHome(data){

    if(
      !data
      ||
      typeof data !== "object"
    ){
      return;
    }


    const arr =
      data.arrimage || {};

    const sprint =
      data.sprint || {};


    // -------------------------------------------
    // KPI ARRIMAGE
    // -------------------------------------------

    text(
      "homeTotalFlux",
      arr.total
    );

    text(
      "homeDelivered",
      arr.delivered
    );

    text(
      "homeDeliveredPct",
      String(
        arr.deliveredPct ?? 0
      )
      .replace(".", ",")
      + "%"
    );


    updateMetricByLabel(
      "Flux en cours",
      arr.inProgress ?? 0,
      arr.inProgressPct ?? 0
    );


    // -------------------------------------------
    // SPRINT
    // -------------------------------------------

    text(
      "homeSprint",
      sprint.current || "—"
    );


    if(
      sprint.startDate
      ||
      sprint.endDate
    ){

      let dates = "";

      if(
        sprint.startDate
        &&
        sprint.endDate
      ){

        dates =
          "Du "
          + formatDate(
              sprint.startDate
            )
          + " au "
          + formatDate(
              sprint.endDate
            );

      }else{

        dates =
          formatDate(
            sprint.startDate
            ||
            sprint.endDate
          );
      }


      text(
        "homeSprintDates",
        dates
      );
    }


    const stats = [];

    if(
      Number.isFinite(
        Number(sprint.total)
      )
    ){
      stats.push(
        Number(sprint.total)
        + " flux"
      );
    }

    if(
      Number.isFinite(
        Number(sprint.delivered)
      )
    ){
      stats.push(
        Number(sprint.delivered)
        + " livrés"
      );
    }

    if(
      Number.isFinite(
        Number(sprint.inProgress)
      )
    ){
      stats.push(
        Number(sprint.inProgress)
        + " en cours"
      );
    }

    if(
      Number(sprint.blocked) > 0
    ){
      stats.push(
        Number(sprint.blocked)
        + " bloqués"
      );
    }


    if(stats.length){

      text(
        "homeSprintStats",
        stats.join(" • ")
      );
    }


    // -------------------------------------------
    // DERNIERE MISE A JOUR
    // -------------------------------------------

    text(
      "homeLastUpdate",
      formatDateTime(
        data.generatedAt
      )
    );


    window.__GIL_HOME_DATA__ =
      data;

    console.log(
      "[GIL Portal] Home actualisée",
      data
    );
  }


  async function loadHomeData(){

    try{

      const response =
        await fetch(
          DATA_URL
          + "?t="
          + Date.now(),
          {
            cache:"no-store"
          }
        );


      if(!response.ok){

        throw new Error(
          "HTTP "
          + response.status
        );
      }


      const data =
        await response.json();


      renderHome(data);


    }catch(error){

      /*
       * Les valeurs HTML existantes restent
       * affichées si aucune publication Portal
       * n'a encore été exécutée.
       */
      console.warn(
        "[GIL Portal] "
        + "gil_home.json indisponible, "
        + "fallback HTML conservé.",
        error
      );
    }
  }


  if(
    document.readyState ===
    "loading"
  ){

    document.addEventListener(
      "DOMContentLoaded",
      loadHomeData
    );

  }else{

    loadHomeData();
  }

})();
