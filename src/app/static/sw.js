/* Service worker de Polla del Mundial.
   Estrategia:
   - Estáticos (/static/...): cache con respaldo a red (rápido y offline).
   - Navegación / HTML / datos: SIEMPRE a la red, sin cachear. Nunca guardamos
     páginas autenticadas (evita que en un dispositivo compartido se vea el
     contenido de otra sesión tras cerrar sesión / sin conexión). Si no hay
     red, mostramos una página offline mínima. */
const CACHE = "polla-v2";
const OFFLINE_URL = "/static/offline.html";
const ASSETS = ["/static/icon.svg", "/static/manifest.webmanifest", OFFLINE_URL];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Solo GET; nunca interceptar POST de predicciones/login.
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // no tocamos terceros (banderas, etc.)

  // Estáticos propios: cache-first, refrescando en segundo plano.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((hit) => {
        const network = fetch(req)
          .then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return res;
          })
          .catch(() => hit);
        return hit || network;
      })
    );
    return;
  }

  // Navegación / HTML / JSON autenticado: solo red. Sin cachear.
  // Si falla la red y es una navegación, mostramos la página offline.
  event.respondWith(
    fetch(req).catch(() => {
      if (req.mode === "navigate") return caches.match(OFFLINE_URL);
      return Response.error();
    })
  );
});
