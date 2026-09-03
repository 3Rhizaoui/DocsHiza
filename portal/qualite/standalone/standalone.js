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


  function sourceType(row) {

    return String(
      row?.sourceType || ""
    ).toUpperCase();
  }


  function hasJira(row) {

    return Boolean(
      row?.jira
      || row?.jiraKey
      || sourceType(row) === "JIRA"
    );
  }


  function hasOctane(row) {

    return Boolean(
      row?.octane
      || sourceType(row) === "OCTANE"
    );
  }


  function isJiraRow(row) {

    return sourceType(row) === "JIRA";
  }


  function isOctaneRow(row) {

    return sourceType(row) === "OCTANE";
  }


  function isMatchedRow(row) {

    return (
      hasJira(row)
      && hasOctane(row)
    );
  }


  function rowVersionRelease(row) {

    if (isOctaneRow(row)) {

      return String(
        row?.octane?.release || ""
      );
    }

    return String(
      row?.jira?.version
      || row?.version
      || ""
    );
  }


  function rowEnvironment(row) {

    if (isOctaneRow(row)) {

      return String(
        row?.octane?.environnement || ""
      ).toUpperCase();
    }

    return String(
      row?.jira?.environnement
      || row?.environnement
      || ""
    ).toUpperCase();
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


  function jiraTaskStats(rows) {

    const jiraRows =
      rows.filter(hasJira);

    const tasks =
      jiraRows.flatMap(
        row =>
          Array.isArray(
            row?.jira?.taches
          )
            ? row.jira.taches
            : []
      );

    const ready =
      tasks.filter(
        task =>
          task?.readyForTest === true
      ).length;

    return {
      total: tasks.length,
      ready,
      nonReady:
        tasks.length - ready,
      capabilitiesReady:
        jiraRows.filter(
          jiraReady
        ).length
    };
  }


  function renderKpis(rows) {

    const jiraRows =
      rows.filter(hasJira);

    const octaneRows =
      rows.filter(hasOctane);

    const matchedRows =
      rows.filter(isMatchedRow);

    const jiraStats =
      jiraTaskStats(rows);

    byId("kpiTotal").textContent =
      jiraRows.length;

    byId("kpiReadyTest").textContent =
      jiraRows.length;

    byId("kpiReadyUse").textContent =
      octaneRows.length;

    const matched =
      byId("kpiMatched");

    if (matched) {
      matched.textContent =
        matchedRows.length;
    }

    byId("kpiNonReady").textContent =
      jiraStats.capabilitiesReady;
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


  function formatDuration(value) {

    if (
      value === null
      || value === undefined
      || value === ""
    ) {
      return "—";
    }

    const numeric =
      Number(value);

    if (Number.isNaN(numeric)) {
      return String(value);
    }

    /*
     * Octane peut retourner une durée numérique.
     * On conserve la valeur source sans inventer
     * une unité si elle n'est pas connue.
     */
    return String(value);
  }


  function objectText(value) {

    if (
      value === null
      || value === undefined
      || value === ""
    ) {
      return "";
    }

    if (Array.isArray(value)) {

      return value
        .map(objectText)
        .filter(Boolean)
        .join(", ");
    }

    if (typeof value === "object") {

      if (value.name) {
        return String(value.name);
      }

      if (value.value) {
        return String(value.value);
      }

      if (value.id) {
        return String(value.id);
      }

      try {
        return JSON.stringify(value);
      } catch (_) {
        return String(value);
      }
    }

    return String(value);
  }


  function linkedDefectsText(execution) {

    const proofs =
      Array.isArray(execution?.preuves)
        ? execution.preuves
        : [];

    const defects =
      proofs
        .filter(
          proof =>
            proof?.type
            === "linked_defects"
        )
        .map(
          proof =>
            objectText(
              proof?.valeur
            )
        )
        .filter(Boolean);

    return defects.join(", ");
  }


  function executionErrorText(execution) {

    const error =
      execution?.erreur || {};

    const parts = [];

    if (error.type) {
      parts.push(
        "Type : " + error.type
      );
    }

    if (error.message) {
      parts.push(
        "Cause : " + error.message
      );
    }

    if (
      error.details
      && error.details !== error.message
    ) {
      parts.push(
        "Détail : " + error.details
      );
    }

    const defects =
      linkedDefectsText(
        execution
      );

    if (defects) {
      parts.push(
        "Bug lié : " + defects
      );
    }

    return parts.join(" | ");
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
      <div style="overflow-x:auto">
        <table class="miniTable">
          <thead>
            <tr>
              <th>ID AR</th>
              <th>Test</th>
              <th>Résultat</th>
              <th>Démarré</th>
              <th>Durée</th>
              <th>Release</th>
              <th>Sprint</th>
              <th>Jalon</th>
              <th>Exécuté par</th>
              <th>Cause / Bug lié</th>
            </tr>
          </thead>

          <tbody>
            ${
              executions.map(
                execution => {

                  const errorText =
                    executionErrorText(
                      execution
                    );

                  return `
                    <tr>
                      <td>
                        <strong>
                          ${escapeHtml(
                            execution.id || "—"
                          )}
                        </strong>
                      </td>

                      <td>
                        ${escapeHtml(
                          execution.nom || "—"
                        )}
                      </td>

                      <td>
                        ${
                          execution.pass
                            ? '<span class="status green">PASS</span>'
                            : execution.fail
                              ? '<span class="status red">FAIL</span>'
                              : '<span class="status gray">'
                                + escapeHtml(
                                    execution.statut
                                    || "—"
                                  )
                                + '</span>'
                        }
                      </td>

                      <td>
                        ${escapeHtml(
                          formatDate(
                            execution.dateExecution
                          )
                        )}
                      </td>

                      <td>
                        ${escapeHtml(
                          formatDuration(
                            execution.duree
                          )
                        )}
                      </td>

                      <td>
                        ${escapeHtml(
                          execution.release
                          || row?.octane?.release
                          || "—"
                        )}
                      </td>

                      <td>
                        ${escapeHtml(
                          execution.sprint
                          || "—"
                        )}
                      </td>

                      <td>
                        ${escapeHtml(
                          execution.jalon
                          || "—"
                        )}
                      </td>

                      <td>
                        ${escapeHtml(
                          execution.executePar
                          || "—"
                        )}
                      </td>

                      <td>
                        ${
                          errorText
                            ? escapeHtml(errorText)
                            : "—"
                        }
                      </td>
                    </tr>
                  `;
                }
              ).join("")
            }
          </tbody>
        </table>
      </div>
    `;
  }



  function matchingValue(
    row,
    name
  ) {

    return (
      row?.matching?.[name]
      || {}
    );
  }


  function coherenceBadge(row) {

    const matching =
      row?.matching || {};

    if (matching.ambigu) {
      return (
        '<span class="status orange">'
        + 'AMBIGU'
        + '</span>'
      );
    }

    if (!matching.trouve) {
      return (
        '<span class="status gray">'
        + 'OCTANE ABSENT'
        + '</span>'
      );
    }

    if (matching.coherent) {
      return (
        '<span class="status green">'
        + 'COHÉRENT'
        + '</span>'
      );
    }

    return (
      '<span class="status red">'
      + 'INCOHÉRENT'
      + '</span>'
    );
  }


  function buildMatchingDetails(row) {

    const capability =
      matchingValue(
        row,
        "capability"
      );

    const version =
      matchingValue(
        row,
        "versionRelease"
      );

    const environment =
      matchingValue(
        row,
        "environnement"
      );

    const matchMark = value =>
      value
        ? '<span class="status green">OK</span>'
        : '<span class="status red">KO</span>';

    return `
      <table class="miniTable">
        <thead>
          <tr>
            <th>Critère</th>
            <th>JIRA</th>
            <th>Octane</th>
            <th>Match</th>
          </tr>
        </thead>

        <tbody>

          <tr>
            <td>Capability</td>
            <td>
              ${escapeHtml(capability.jira || "—")}
            </td>
            <td>
              ${escapeHtml(capability.octane || "—")}
            </td>
            <td>
              ${matchMark(Boolean(capability.match))}
            </td>
          </tr>

          <tr>
            <td>Version / Release</td>
            <td>
              ${escapeHtml(version.jira || "—")}
            </td>
            <td>
              ${escapeHtml(version.octane || "—")}
            </td>
            <td>
              ${matchMark(Boolean(version.match))}
            </td>
          </tr>

          <tr>
            <td>Environnement</td>
            <td>
              ${escapeHtml(environment.jira || "—")}
            </td>
            <td>
              ${escapeHtml(environment.octane || "—")}
            </td>
            <td>
              ${matchMark(Boolean(environment.match))}
            </td>
          </tr>

        </tbody>
      </table>
    `;
  }


  function buildNonReadyReasons(row) {

    const reasons =
      Array.isArray(
        row?.raisonsNonReady
      )
        ? row.raisonsNonReady
        : [];

    if (!reasons.length) {

      return (
        '<div class="status green">'
        + 'Tous les contrôles sont satisfaits'
        + '</div>'
      );
    }

    return `
      <ul>
        ${
          reasons
            .map(
              reason =>
                `<li>${escapeHtml(reason)}</li>`
            )
            .join("")
        }
      </ul>
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

        const octane =
          row?.octane || null;

        const suite =
          octane?.testSuite || {};

        const jiraPresent =
          hasJira(row);

        const octanePresent =
          hasOctane(row);

        const capabilityJira =
          row?.capability
          || row?.jira?.capability
          || "";

        const capabilityOctane =
          octane?.capability
          || octane?.octaneFeature?.nom
          || "";

        const jiraVersion =
          row?.jira?.version
          || row?.version
          || "";

        const jiraEnvironment =
          row?.jira?.environnement
          || row?.environnement
          || "";

        const octaneEnvironment =
          octane?.environnement
          || "";

        const octaneRelease =
          octane?.release
          || "";

        const octaneDate =
          octane?.dateExecution
          || octane?.derniereExecution
          || octane?.suiteRun?.dateDebut
          || "";

        const totalTasks =
          Number(
            readiness.total || 0
          );

        const readyTasks =
          Number(
            readiness.readyForTest || 0
          );

        const octanePass =
          Boolean(
            results?.tousPass === true
          );

        const octaneFail =
          Number(
            results?.fail || 0
          ) > 0;

        let globalStatus = "—";

        if (octanePresent) {

          if (octanePass) {
            globalStatus =
              '<span class="status green">PASS</span>';
          } else if (octaneFail) {
            globalStatus =
              '<span class="status red">ÉCHEC</span>';
          } else if (octane?.statut) {
            globalStatus =
              '<span class="status">'
              + escapeHtml(octane.statut)
              + '</span>';
          }

        }

        let readyFlux =
          '<span class="status gray">—</span>';

        if (row?.readyForFlux === true) {

          readyFlux =
            '<span class="status green">✓ PRÊT</span>';

        } else if (
          row?.readyForFlux === false
        ) {

          readyFlux =
            '<span class="status orange">⚠ NON PRÊT</span>';

        }

        const main =
          document.createElement("tr");

        main.className =
          "mainRow "
          + (
            index % 2 === 0
              ? "mainRowBlueA"
              : "mainRowBlueB"
          );

        main.dataset.index =
          String(index);

        main.innerHTML = `
          <td class="jiraCell">
            <span class="rowToggle">⌄</span>
            <strong>
              ${escapeHtml(
                capabilityJira || "—"
              )}
            </strong>
          </td>

          <td class="jiraCell">
            ${escapeHtml(
              jiraVersion || "—"
            )}
          </td>

          <td class="jiraCell">
            ${escapeHtml(
              jiraEnvironment || "—"
            )}
          </td>

          <td class="jiraCell">
            <strong>
              ${readyTasks} / ${totalTasks}
            </strong>
          </td>

          <td class="jiraCell">
            ${
              jiraPresent
                ? statusBadge(
                    jiraReady(row),
                    "✓ PRÊT",
                    "⚠ NON PRÊT"
                  )
                : "—"
            }
          </td>

          <td class="octaneCell">
            ${escapeHtml(
              suite.nom || "—"
            )}
            ${
              suite.id
                ? " (" + escapeHtml(suite.id) + ")"
                : ""
            }
          </td>

          <td class="octaneCell">
            ${escapeHtml(
              capabilityOctane || "—"
            )}
          </td>

          <td class="octaneCell">
            ${escapeHtml(
              octaneEnvironment || "—"
            )}
          </td>

          <td class="octaneCell">
            ${escapeHtml(
              octaneRelease || "—"
            )}
          </td>

          <td class="octaneCell">
            ${globalStatus}
          </td>

          <td class="octaneCell">
            ${escapeHtml(
              formatDate(
                octaneDate
              )
            )}
          </td>

          <td class="octaneCell">
            ${readyFlux}
          </td>
        `;


        const detail =
          document.createElement("tr");

        detail.className =
          "detailRow";

        detail.innerHTML = `
          <td colspan="12">

            <div class="detail">

              <div class="detailGridMatched">

                <div class="detailBox detailBoxJira">

                  <h3>
                    DÉTAILS JIRA
                  </h3>

                  <div class="detailMeta">

                    <strong>Epic :</strong>
                    ${escapeHtml(
                      row.jiraKey || "—"
                    )}

                    &nbsp;&nbsp;

                    <strong>Version :</strong>
                    ${escapeHtml(
                      jiraVersion || "—"
                    )}

                    &nbsp;&nbsp;

                    <strong>Environnement :</strong>
                    ${escapeHtml(
                      jiraEnvironment || "—"
                    )}

                  </div>

                  <div class="jiraDescription">

                    <strong>Description Epic</strong>

                    <div>
                      ${escapeHtml(
                        row?.jira?.description
                        || row?.description
                        || "—"
                      )}
                    </div>

                  </div>

                  <h4>
                    Tâches JIRA (${totalTasks})
                  </h4>

                  ${buildTaskRows(row)}

                </div>


                <div class="detailBox detailBoxOctane">

                  <h3>
                    DÉTAILS OCTANE
                  </h3>

                  <div class="detailMeta">

                    <strong>Feature :</strong>
                    ${escapeHtml(
                      octane
                        ?.octaneFeature
                        ?.nom
                      || capabilityOctane
                      || "—"
                    )}

                    &nbsp;&nbsp;

                    <strong>Release :</strong>
                    ${escapeHtml(
                      octaneRelease || "—"
                    )}

                    &nbsp;&nbsp;

                    <strong>Environnement :</strong>
                    ${escapeHtml(
                      octaneEnvironment || "—"
                    )}

                  </div>

                  <div class="detailMeta">

                    <strong>Test Suite :</strong>
                    ${escapeHtml(
                      suite.nom || "—"
                    )}

                    ${
                      suite.id
                        ? " (" + escapeHtml(suite.id) + ")"
                        : ""
                    }

                    &nbsp;&nbsp;

                    <strong>Suite Run :</strong>
                    ${escapeHtml(
                      octane?.suiteRun?.id
                      || "—"
                    )}

                    ${
                      octane?.suiteRun?.nom
                        ? " - "
                          + escapeHtml(
                              octane.suiteRun.nom
                            )
                        : ""
                    }

                  </div>

                  <div class="detailMeta">

                    <strong>Résultat :</strong>
                    ${globalStatus}

                    &nbsp;&nbsp;

                    <strong>Démarré :</strong>
                    ${escapeHtml(
                      formatDate(
                        octane?.suiteRun?.dateDebut
                        || octaneDate
                      )
                    )}

                    &nbsp;&nbsp;

                    <strong>Sprint :</strong>
                    ${escapeHtml(
                      octane?.suiteRun?.sprint
                      || octane?.sprint
                      || "—"
                    )}

                    &nbsp;&nbsp;

                    <strong>Jalon :</strong>
                    ${escapeHtml(
                      octane?.suiteRun?.jalon
                      || octane?.jalon
                      || "—"
                    )}

                    &nbsp;&nbsp;

                    <strong>Exécuté par :</strong>
                    ${escapeHtml(
                      octane?.suiteRun?.executePar
                      || "—"
                    )}

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

            const toggle =
              main.querySelector(
                ".rowToggle"
              );

            if (toggle) {
              toggle.textContent =
                detail.classList.contains(
                  "open"
                )
                  ? "⌄"
                  : "›";
            }

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

    const source =
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
          && rowVersionRelease(row)
          !== version
        ) {
          return false;
        }

        if (
          env
          && rowEnvironment(row)
          !== env
        ) {
          return false;
        }

        if (
          source === "jira"
          && !hasJira(row)
        ) {
          return false;
        }

        if (
          source === "octane"
          && !hasOctane(row)
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
          .map(
            row =>
              rowVersionRelease(row)
          )
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
