/*
 * ============================================================
 * GIL Portal - Logger navigateur
 * ============================================================
 *
 * Traces :
 * - chargement de page
 * - chargement JSON
 * - erreurs HTTP
 * - ventilation des datasets par page
 *
 * Endpoint :
 * POST /log/client
 * ============================================================
 */

(function () {

  "use strict";

  const page =
    window.location.pathname || "/";

  async function send(
    level,
    event,
    details
  ) {

    const payload = {
      timestamp:
        new Date().toISOString(),

      level:
        String(level || "INFO"),

      event:
        String(event || "event"),

      page,

      url:
        window.location.href,

      details:
        details || {}
    };

    try {

      await fetch(
        "/log/client",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json"
          },
          body:
            JSON.stringify(payload),
          keepalive: true
        }
      );

    } catch (_) {
      /*
       * Le logger ne doit jamais
       * casser le Portal.
       */
    }
  }


  window.GILLog = {

    debug(event, details) {
      return send(
        "DEBUG",
        event,
        details
      );
    },

    info(event, details) {
      return send(
        "INFO",
        event,
        details
      );
    },

    warn(event, details) {
      return send(
        "WARNING",
        event,
        details
      );
    },

    error(event, details) {
      return send(
        "ERROR",
        event,
        details
      );
    },

    critical(event, details) {
      return send(
        "CRITICAL",
        event,
        details
      );
    }
  };


  /*
   * -------------------------------------------
   * Trace automatique de la page
   * -------------------------------------------
   */

  document.addEventListener(
    "DOMContentLoaded",
    function () {

      send(
        "INFO",
        "PAGE_LOADED",
        {
          title:
            document.title,

          pathname:
            window.location.pathname
        }
      );

    }
  );


  /*
   * -------------------------------------------
   * Trace automatique des datasets
   *
   * On intercepte uniquement les JSON
   * utilisés par le Portal.
   * -------------------------------------------
   */

  const originalFetch =
    window.fetch.bind(window);

  window.fetch =
    async function (...args) {

      const request =
        args[0];

      const url =
        typeof request === "string"
          ? request
          : (
              request
              && request.url
            ) || "";

      const isData =
        url.includes(
          "commun/data/"
        )
        || url.endsWith(
          ".json"
        );

      if (isData) {

        send(
          "DEBUG",
          "DATA_REQUEST",
          {
            dataset: url
          }
        );

      }

      try {

        const response =
          await originalFetch(
            ...args
          );

        if (isData) {

          send(
            response.ok
              ? "INFO"
              : (
                  response.status === 404
                    ? "WARNING"
                    : "ERROR"
                ),

            response.ok
              ? "DATA_LOADED"
              : (
                  response.status === 404
                    ? "DATA_NOT_PUBLISHED"
                    : "DATA_HTTP_ERROR"
                ),

            {
              dataset:
                url,

              status:
                response.status,

              page:
                window.location.pathname
            }
          );

        }

        return response;

      } catch (error) {

        if (isData) {

          send(
            "ERROR",
            "DATA_FETCH_ERROR",
            {
              dataset:
                url,

              error:
                String(error)
            }
          );

        }

        throw error;
      }
    };


  /*
   * -------------------------------------------
   * Erreurs JS globales
   * -------------------------------------------
   */

  window.addEventListener(
    "error",
    function (event) {

      send(
        "ERROR",
        "JS_ERROR",
        {
          message:
            event.message,

          file:
            event.filename,

          line:
            event.lineno,

          column:
            event.colno
        }
      );

    }
  );


  window.addEventListener(
    "unhandledrejection",
    function (event) {

      send(
        "ERROR",
        "PROMISE_REJECTION",
        {
          reason:
            String(
              event.reason
            )
        }
      );

    }
  );

})();
