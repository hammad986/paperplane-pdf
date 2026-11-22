const CACHE_NAME = 'paperplane-shell-v95';
const APP_SHELL = [
  '/',
  '/manifest.webmanifest',
  '/assets/styles.css?v=61',
  '/assets/theme-init.js?v=13',
  '/assets/app.js?v=154',
  '/assets/page_organizer.js?v=20',
  '/assets/pdf_runtime.js?v=25',
  '/assets/pdf.min.js',
  '/assets/pdf.worker.min.js',
  '/assets/pdf-lib.min.js',
  '/assets/studio_render_worker.js?v=4',
  '/assets/local_pdf_worker.js?v=26',
  '/assets/favicon.svg',
  '/assets/app-192.png',
  '/assets/app-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(name => name.startsWith('paperplane-shell-') && name !== CACHE_NAME).map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok && url.pathname === '/') {
          const cache = await caches.open(CACHE_NAME);
          await cache.put('/', response.clone());
        }
        return response;
      } catch {
        return (await caches.match('/')) || Response.error();
      }
    })());
    return;
  }
  if (!url.pathname.startsWith('/assets/')) return;
  event.respondWith((async () => {
    try {
      const response = await fetch(request);
      if (response.ok && APP_SHELL.includes(`${url.pathname}${url.search}`)) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(request, response.clone());
      }
      return response;
    } catch {
      return (await caches.match(request)) || Response.error();
    }
  })());
});
