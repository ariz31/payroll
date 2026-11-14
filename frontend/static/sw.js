importScripts('/shell-manifest.js');
const version = 'siteguard-shell-' + self.siteguardShell.version;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(version);
    await cache.addAll(['/', '/favicon.svg', ...self.siteguardShell.assets]);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith('siteguard-shell-') && key !== version)
      .map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  const navigation = event.request.mode === 'navigate' && url.pathname === '/';
  if (url.origin !== self.location.origin || event.request.method !== 'GET' ||
      (!navigation && !url.pathname.startsWith('/assets/'))) return;
  event.respondWith((async () => {
    const cache = await caches.open(version);
    if (navigation) {
      try {
        const response = await fetch(event.request);
        if (response.ok && response.headers.get('content-type')?.includes('text/html')) {
          await cache.put('/', response.clone());
        }
        return response;
      } catch {
        return await cache.match('/') || Response.error();
      }
    }
    const cached = await cache.match(event.request);
    if (cached) return cached;
    const response = await fetch(event.request);
    if (response.ok) await cache.put(event.request, response.clone());
    return response;
  })());
});
