const CACHE_NAME = "bygui-shell-v2";
const SHELL_ASSETS = ["/", "/static/css/main.css", "/static/img/pwa-icon-192.png"];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => {})
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((names) => Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))))
            .then(() => self.clients.claim())
    );
});

// Red primero, caché solo como respaldo si no hay conexión: así cada
// despliegue nuevo se ve al instante (nada de servir para siempre una
// copia vieja de "/" o del CSS), y solo se recurre a lo cacheado si de
// verdad no hay red.
self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                const copy = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
