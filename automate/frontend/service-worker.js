// autoMate service worker.
//
// Two responsibilities:
//   1. Cache the SPA shell so launching from the home screen feels instant.
//   2. Receive Web Push notifications for reminders and surface them.

const SHELL = "automate-shell-v5";
const ASSETS = [
  "/", "/index.html", "/app.js", "/styles.css",
  "/icon-192.png", "/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/oauth/")) return;
  if (e.request.method !== "GET") return;
  e.respondWith(
    caches.match(e.request).then((hit) =>
      hit || fetch(e.request).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(e.request, copy));
        }
        return res;
      }).catch(() => caches.match("/index.html"))
    )
  );
});

// ---- Web Push (reminders) ----

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { /* noop */ }
  const title = data.title || "autoMate";
  const opts = {
    body: data.body || "",
    tag: data.tag || "automate",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    data: { url: data.url || "/" },
    requireInteraction: false,
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const c of wins) {
        if ("focus" in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
