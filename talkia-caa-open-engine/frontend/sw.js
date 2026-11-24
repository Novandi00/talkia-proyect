const CACHE_VERSION = "talkia-pwa-v2";
const STATIC_ASSETS = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./tts_provider.js",
  "./offline_store.js",
  "./contracts.js",
  "./logo.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_VERSION).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const isPictoOrStatic =
    request.url.includes("static.arasaac.org") ||
    request.url.includes("api.arasaac.org") ||
    request.url.endsWith(".svg") ||
    request.url.endsWith(".png") ||
    new URL(request.url).origin === self.location.origin;

  if (isPictoOrStatic) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((networkResp) => {
            if (networkResp.status === 200) {
              const clone = networkResp.clone();
              caches.open(CACHE_VERSION).then((cache) => cache.put(request, clone));
            }
            return networkResp;
          }).catch(() => cached)
      )
    );
  }
});
