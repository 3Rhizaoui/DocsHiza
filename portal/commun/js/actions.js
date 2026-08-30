/*
 * ============================================================
 * GIL Portal - Actions communes
 * ============================================================
 *
 * Le serveur local existant expose :
 * POST /action/jira
 *
 * Le pipeline JIRA existant reste inchangé.
 * ============================================================
 */

async function runLocalAction(action) {

  const button =
    document.getElementById("gilRefreshProjectButton");

  const label =
    document.getElementById("gilRefreshProjectLabel");

  const status =
    document.getElementById("gilRefreshProjectStatus");

  const previousLabel =
    label ? label.textContent : "";

  try {

    if (button) {
      button.disabled = true;
    }

    if (label) {
      label.textContent = "Rafraîchissement en cours...";
    }

    if (status) {
      status.textContent =
        "Rafraîchissement global du projet GIL...";
    }

    /*
     * Même endpoint que l'ancien dashboard.
     *
     * URL relative :
     * fonctionne depuis
     * http://127.0.0.1:8765/portal/
     */
    const response = await fetch(
      "/action/" + action,
      {
        method: "POST"
      }
    );

    const text = await response.text();

    if (!response.ok) {
      throw new Error(
        text || ("HTTP " + response.status)
      );
    }

    if (status) {
      status.textContent =
        "Pipeline lancé. Le portail sera actualisé après publication.";
    }

    /*
     * Le processus Importer_JIRA.cmd existant
     * réouvre /portal/?_gil_refresh=... après publication.
     */
    alert(text);

  } catch (error) {

    console.error(
      "[GIL Portal] erreur action",
      action,
      error
    );

    if (status) {
      status.textContent =
        "Rafraîchissement impossible - dernière version conservée.";
    }

    alert(
      "Serveur local indisponible ou action impossible.\n\n" +
      "Lance Lancer_Dashboard.cmd puis réessaie.\n\n" +
      error
    );

  } finally {

    if (button) {
      button.disabled = false;
    }

    if (label) {
      label.textContent =
        previousLabel ||
        "Rafraîchir les données du projet";
    }

  }
}
