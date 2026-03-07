// ═══════════════════════════════════════════════
// TINKU AI — SERVICE WORKER (PWA)
// Handles: background notifications, offline cache
// ═══════════════════════════════════════════════

const CACHE_NAME = 'tinku-v5';
const OFFLINE_URL = '/';

// Files to cache for offline use
const CACHE_FILES = [
  '/',
  '/static/logo.png',
  '/static/manifest.json'
];

// ── Install: cache key files ──
self.addEventListener('install', event => {
  console.log('[SW] Installing Tinku Service Worker...');
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(CACHE_FILES).catch(err => {
        console.log('[SW] Cache addAll error (non-fatal):', err);
      });
    })
  );
  self.skipWaiting();
});

// ── Activate: clean old caches ──
self.addEventListener('activate', event => {
  console.log('[SW] Activating Tinku Service Worker...');
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME)
            .map(key => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// ── Fetch: serve from cache when offline ──
self.addEventListener('fetch', event => {
  // Only handle GET requests
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful responses
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, clone);
          });
        }
        return response;
      })
      .catch(() => {
        // Offline fallback
        return caches.match(event.request).then(cached => {
          return cached || caches.match(OFFLINE_URL);
        });
      })
  );
});

// ═══════════════════════════════════════════════
// PUSH NOTIFICATIONS
// ═══════════════════════════════════════════════

// Random "Tinku is back" messages
const BACK_MESSAGES = [
  "Hey! I'm back! Miss me? 😄",
  "Tinku is back and better than ever! 🚀",
  "The wait is over! Come chat with me 🎉",
  "I'm alive! Let's talk 🤖✨",
  "Upgrades complete! Ready to impress you 💪",
  "Did someone say Tinku? That's me — I'm back! 🎊",
  "Maintenance done! Your AI buddy is back online 🌟",
  "Back online! Let's pick up where we left off 😊"
];

// ── Push event: show notification ──
self.addEventListener('push', event => {
  console.log('[SW] Push received!');

  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch(e) {
    data = { title: 'Tinku AI', body: BACK_MESSAGES[0] };
  }

  const title = data.title || 'Tinku is back! 🎉';
  const body = data.body || BACK_MESSAGES[Math.floor(Math.random() * BACK_MESSAGES.length)];

  const options = {
    body: body,
    icon: '/static/logo.png',
    badge: '/static/logo.png',
    vibrate: [200, 100, 200],
    tag: 'tinku-notification',
    renotify: true,
    actions: [
      { action: 'open', title: '💬 Open Tinku' },
      { action: 'dismiss', title: 'Dismiss' }
    ],
    data: { url: '/' }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// ── Notification click: open Tinku ──
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      // If Tinku tab already open — focus it
      for (const client of clientList) {
        if (client.url === '/' && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise open new tab
      if (clients.openWindow) {
        return clients.openWindow('/');
      }
    })
  );
});

// ── Message from main thread ──
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'TINKU_BACK') {
    // Maintenance ended — notify all subscribed users
    const msg = BACK_MESSAGES[Math.floor(Math.random() * BACK_MESSAGES.length)];
    self.registration.showNotification('Tinku is back! 🎉', {
      body: msg,
      icon: '/static/logo.png',
      badge: '/static/logo.png',
      vibrate: [200, 100, 200],
      tag: 'tinku-back',
      data: { url: '/' }
    });
  }
});
