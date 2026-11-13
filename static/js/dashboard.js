/**
 * Graphique d'évolution des émotions du tableau de bord (Chart.js).
 *
 * Les données sont calculées côté serveur et transmises via une balise
 * <script type="application/json"> (filtre Django json_script) : aucune
 * requête supplémentaire, et pas de risque d'injection dans le HTML.
 */
(() => {
  "use strict";

  const canvas = document.getElementById("timeline-chart");
  const source = document.getElementById("timeline-data");
  if (!canvas || !source || typeof Chart === "undefined") return;

  const timeline = JSON.parse(source.textContent);

  // Couleurs lisibles sur le thème sombre « nuit étoilée ».
  Chart.defaults.color = "#c9c4e8";
  Chart.defaults.borderColor = "rgba(255, 255, 255, 0.08)";
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";

  new Chart(canvas, {
    type: "bar",
    data: {
      labels: timeline.labels,
      datasets: timeline.datasets.map((dataset) => ({
        label: dataset.label,
        data: dataset.data,
        backgroundColor: dataset.color,
        borderRadius: 3,
      })),
    },
    options: {
      maintainAspectRatio: false,
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : undefined,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12 } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
})();
