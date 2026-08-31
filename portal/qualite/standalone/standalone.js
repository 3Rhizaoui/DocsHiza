(function () {

  "use strict";

  const DATA_URL =
    "../../commun/data/standalone/"
    + "payload_standalone.json";

  let sourceRows = [];


  function byId(id) {
    return document.getElementById(id);
  }


  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }


  function formatDate(value) {

    if (!value) {
      return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return String(value);
    }

    return date.toLocaleString(
      "fr-FR",
      {
        dateStyle: "short",
        timeStyle: "short"
      }
    );
  }


  function jiraReady(row) {

    return Boolean(
      row?.jira?.readiness?.pret
    );
  }


  function octaneResults(row) {

    return (
      row?.octane?.resultats
      || {}
    );
  }


  function statusBadge(
    ok,
    yesText,
    noText
  ) {

    return (
      '<span class="status '
      + (ok ? "green" : "orange")
      + '">'
      + escapeHtml(
        ok ? yesText : noText
      )
      + "</span>"
    );
  }


  function renderKpis(rows) {

    const total =
      rows.length;

    const readyTest =
      rows.filter(
        jiraReady
      ).length;

    const readyUse =
      rows.filter(
        row => row.readyForUse
      ).length;

    byId("kpiTotal").textContent =
      total;

    byId("kpiReadyTest").textContent =
      readyTest;

    byId("kpiReadyUse").textContent =
      readyUse;

    byId("kpiNonReady").textContent =
      total - readyUse;
  }


  function buildTaskRows(row) {

    const tasks =
      row?.jira?.taches || [];

    if (!tasks.length) {
      return (
        '<div class="empty">'
        + "Aucune tâche JIRA."
        + "</div>"
      );
    }

    return `
      <table class="miniTable">
        <thead>
          <tr>
            <th>JIRA</th>
            <th>Tâche</th>
            <th>Statut</th>
            <th>Ready</th>
          </tr>
        </thead>

        <tbody>
          ${
            tasks.map(task => `
              <tr>
                <td>
                  ${escapeHtml(task.jiraKey)}
                </td>

                <td>
                  ${escapeHtml(task.titre)}
                </td>

                <td>
                  ${escapeHtml(task.statut)}
                </td>

                <td>
                  ${
                    task.readyForTest
                      ? "✓"
                      : "—"
                  }
                </td>
              </tr>
            `).join("")
          }
        </tbody>
      </table>
    `;
  }


  function buildExecutionRows(row) {

    const executions =
      row?.octane?.executions || [];

    if (!executions.length) {

      return (
        '<div class="empty">'
        + "Aucune exécution Octane."
        + "</div>"
      );
    }

    return `
      <table class="miniTable">
        <thead>
          <tr>
            <th>Exécution</th>
            <th>Résultat</th>
            <th>Date</th>
            <th>Preuves</th>
          </tr>
        </thead>

        <tbody>
          ${
            executions.map(execution => `
              <tr>
                <td>
                  ${escapeHtml(execution.nom)}
                </td>

                <td>
                  ${
                    execution.pass
                      ? '<span class="status green">PASS</span>'
                      : execution.fail
                        ? '<span class="status red">FAIL</span>'
                        : '<span class="status gray">'
                          + escapeHtml(execution.statut)
                          + '</span>'
                  }
                </td>

                <td>
                  ${
                    escapeHtml(
                      formatDate(
                        execution.dateExecution
                      )
                    )
                  }
                </td>

                <td>
                  ${
                    Array.isArray(execution.preuves)
                      ? execution.preuves.length
                      : 0
                  }
                </td>
              </tr>
            `).join("")
          }
        </tbody>
      </table>
    `;
  }


  function renderRows(rows) {

    const body =
      byId("standaloneBody");

    body.innerHTML = "";

    byId("emptyMessage").hidden =
      rows.length > 0;

    rows.forEach(
      (row, index) => {

        const readiness =
          row?.jira?.readiness || {};

        const results =
          octaneResults(row);

        const suite =
          row?.octane?.testSuite || {};

        const main =
          document.createElement("tr");

        main.className =
          "mainRow";

        main.dataset.index =
          String(index);

        main.innerHTML = `
          <td>
            <strong>
              ${escapeHtml(row.capability)}
            </strong>
          </td>

          <td>
            ${escapeHtml(row.jiraKey)}
          </td>

          <td>
            ${escapeHtml(row.version || "—")}
          </td>

          <td>
            ${escapeHtml(row.environnement || "—")}
          </td>

          <td>
            ${
              Number(
                readiness.readyForTest || 0
              )
            }
            /
            ${
              Number(
                readiness.total || 0
              )
            }
          </td>

          <td>
            ${
              statusBadge(
                jiraReady(row),
                "Ready for Test",
                "Non Ready"
              )
            }
          </td>

          <td>
            ${
              escapeHtml(
                suite.nom || "Non trouvé"
              )
            }
          </td>

          <td>
            ${
              Number(
                results.pass || 0
              )
            }
          </td>

          <td>
            ${
              Number(
                results.fail || 0
              )
            }
          </td>

          <td>
            ${
              escapeHtml(
                formatDate(
                  row?.octane
                    ?.derniereExecution
                )
              )
            }
          </td>

          <td>
            ${
              row.readyForUse
                ? '<span class="status green">READY</span>'
                : '<span class="status red">NON READY</span>'
            }
          </td>
        `;

        const detail =
          document.createElement("tr");

        detail.className =
          "detailRow";

        detail.innerHTML = `
          <td colspan="11">
            <div class="detail">

              <div class="detailGrid">

                <div class="detailBox">
                  <h3>
                    JIRA - Tâches de la Capability
                  </h3>

                  ${buildTaskRows(row)}
                </div>

                <div class="detailBox">
                  <h3>
                    OCTANE - Qualification
                  </h3>

                  <div style="margin-bottom:12px">
                    <strong>Release :</strong>
                    ${
                      escapeHtml(
                        row?.octane?.release
                        || "—"
                      )
                    }
                    &nbsp;&nbsp;

                    <strong>Environnement :</strong>
                    ${
                      escapeHtml(
                        row?.octane?.environnement
                        || "—"
                      )
                    }
                  </div>

                  ${buildExecutionRows(row)}
                </div>

              </div>

            </div>
          </td>
        `;

        main.addEventListener(
          "click",
          () => {
            detail.classList.toggle(
              "open"
            );
          }
        );

        body.appendChild(main);
        body.appendChild(detail);
      }
    );
  }


  function applyFilters() {

    const version =
      byId("filterVersion").value;

    const env =
      byId("filterEnv").value;

    const status =
      byId("filterStatus").value;

    const capability =
      byId("filterCapability")
        .value
        .trim()
        .toLowerCase();

    const rows =
      sourceRows.filter(row => {

        if (
          version
          && row.version !== version
        ) {
          return false;
        }

        if (
          env
          && row.environnement !== env
        ) {
          return false;
        }

        if (
          status === "ready"
          && !row.readyForUse
        ) {
          return false;
        }

        if (
          status === "not-ready"
          && row.readyForUse
        ) {
          return false;
        }

        if (
          capability
          && !String(
            row.capability || ""
          )
            .toLowerCase()
            .includes(capability)
        ) {
          return false;
        }

        return true;
      });

    renderKpis(rows);
    renderRows(rows);
  }


  function populateVersions() {

    const select =
      byId("filterVersion");

    const values = [
      ...new Set(
        sourceRows
          .map(row => row.version)
          .filter(Boolean)
      )
    ].sort();

    values.forEach(value => {

      const option =
        document.createElement(
          "option"
        );

      option.value = value;
      option.textContent = value;

      select.appendChild(option);
    });
  }


  async function load() {

    const url =
      DATA_URL
      + "?t="
      + Date.now();

    const response =
      await fetch(
        url,
        {
          cache: "no-store"
        }
      );

    if (!response.ok) {

      throw new Error(
        "Payload Standalone indisponible : HTTP "
        + response.status
      );
    }

    const data =
      await response.json();

    sourceRows =
      Array.isArray(data.capabilities)
        ? data.capabilities
        : [];

    populateVersions();

    renderKpis(sourceRows);
    renderRows(sourceRows);

    byId("generatedAt").textContent =
      "Dernière génération : "
      + formatDate(
        data.generatedAt
      );
  }


  [
    "filterVersion",
    "filterEnv",
    "filterStatus",
    "filterCapability"
  ].forEach(id => {

    const element = byId(id);

    element.addEventListener(
      id === "filterCapability"
        ? "input"
        : "change",
      applyFilters
    );
  });


  load().catch(error => {

    console.error(
      "[GIL Standalone]",
      error
    );

    byId("emptyMessage").hidden =
      false;

    byId("emptyMessage").textContent =
      error.message;
  });

})();
