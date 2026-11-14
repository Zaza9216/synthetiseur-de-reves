/** Enregistre le service worker (application installable, page hors ligne). */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      /* Navigation normale si l'enregistrement échoue (navigation privée, etc.). */
    });
  });
}
