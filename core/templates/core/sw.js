{% load static %}/* Service worker du Synthétiseur de rêves (version {{ version }}).
 *
 * Volontairement minimal : il met en cache la page « hors ligne » et quelques
 * fichiers statiques. Les pages personnelles (rêves, tableau de bord) ne sont
 * JAMAIS mises en cache : elles contiennent des données privées.
 */
const CACHE = "reves-{{ version }}";
const OFFLINE_URL = "{% url 'core:offline' %}";
const PRECACHE = [
  OFFLINE_URL,
  "{% static 'css/theme.css' %}",
  "{% static 'icons/icon-192.png' %}",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  // Navigation : toujours le réseau ; la page hors ligne seulement en cas de coupure.
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  // Fichiers statiques pré-chargés : depuis le cache s'ils y sont.
  if (request.method === "GET" && PRECACHE.includes(new URL(request.url).pathname)) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
  }
});
