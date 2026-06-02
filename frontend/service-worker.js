const APP_CACHE = "ec26b-app-shell-v20260601-3";
const APP_SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./icon-192.png",
  "./icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(APP_CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.startsWith("ec26b-app-shell-") && key !== APP_CACHE)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirstPage(request));
    return;
  }

  event.respondWith(staleWhileRevalidate(request));
});

async function networkFirstPage(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(APP_CACHE);
      await cache.put("./index.html", response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match("./index.html");
    return cached || new Response("Offline", {
      status: 503,
      headers: { "Content-Type": "text/plain;charset=UTF-8" },
    });
  }
}

async function staleWhileRevalidate(request) {
  const cached = await caches.match(request, { ignoreSearch: true });
  const responsePromise = fetch(request)
    .then(async (response) => {
      if (response.ok) {
        const cache = await caches.open(APP_CACHE);
        await cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);
  return cached || responsePromise;
}
