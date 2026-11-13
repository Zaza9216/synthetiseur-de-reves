/**
 * Suivi en direct du traitement d'un rêve.
 *
 * Interroge régulièrement le serveur. Le libellé de l'étape est mis à jour à
 * chaque réponse ; la page est rechargée quand l'étape change ou quand le
 * traitement se termine (succès, échec ou blocage).
 */
(() => {
  "use strict";

  const panel = document.getElementById("processing-panel");
  if (!panel) return;

  const url = panel.dataset.statusUrl;
  const label = document.getElementById("processing-label");
  const MAX_DURATION_MS = 15 * 60 * 1000; // au-delà, on arrête d'interroger
  const startedAt = Date.now();
  let delay = 2000;
  let lastStatus = null;

  async function poll() {
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!data.is_processing || data.can_retry) {
        window.location.reload();
        return;
      }
      label.textContent = data.status_label;
      if (lastStatus !== null && data.status !== lastStatus) {
        window.location.reload(); // met à jour les étapes affichées
        return;
      }
      lastStatus = data.status;
      delay = 2000;
    } catch {
      delay = Math.min(delay * 2, 15000); // serveur indisponible : on espace les essais
    }
    if (Date.now() - startedAt < MAX_DURATION_MS) {
      setTimeout(poll, delay);
    }
  }

  setTimeout(poll, delay);
})();
