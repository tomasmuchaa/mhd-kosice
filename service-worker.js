const CACHE_NAME = 'nexigo-cache-v7';
const STATIC_ASSETS = [
  '/manifest.json',
  '/static/icons/favicon.png?v=3',
  '/static/icons/icon-192.png?v=3',
  '/static/icons/icon-512.png?v=3',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('SW pre-cache warning:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('SW mazanie starej cache:', key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // 1. Pre API požiadavky: vždy použi priamu sieť bez cachovania
  if (requestUrl.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch((err) => {
        return new Response(JSON.stringify({ error: 'offline', message: 'Zariadenie je offline' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        });
      })
    );
    return;
  }

  // 2. Pre navigáciu a HTML stránku (/mapa): Network-First (vždy najčerstvejší kód zo servera)
  if (event.request.mode === 'navigate' || requestUrl.pathname === '/mapa') {
    event.respondWith(
      fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => {
        return caches.match(event.request).then((cached) => {
          return cached || caches.match('/mapa');
        });
      })
    );
    return;
  }

  // 3. Pre statické súbory (knižnice, fonty, ikony): Cache-First s fallbackom na sieť
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
          return networkResponse;
        }
        const responseToCache = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseToCache);
        });
        return networkResponse;
      });
    })
  );
});

// Spracovanie kliknutia na systémovú notifikáciu (Upozornenie pred príchodom spoja)
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = new URL('/mapa', self.location.origin).href;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // Ak už existuje otvorená karta Nexigo, zaostríme ju
      for (let client of windowClients) {
        if (client.url === targetUrl || client.url.startsWith(self.location.origin)) {
          return client.focus();
        }
      }
      // Inak otvoríme novú kartu s mapou
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

