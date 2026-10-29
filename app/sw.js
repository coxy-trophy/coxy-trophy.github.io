// Psalmist web: keeps the app itself on the device so it opens instantly and offline.
// Music and videos stream from jw.org and aren't stored here.
const SHELL = 'psalmist-shell-v1'
const IMAGES = 'psalmist-images-v1'

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL).then(c => c.addAll(['./', 'index.html', 'manifest.webmanifest', 'icon.svg', 'apple-touch-icon.png'])).then(() => self.skipWaiting()))
})

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('psalmist-') && k !== SHELL && k !== IMAGES).map(k => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', event => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  // The app's own files: network first (so updates arrive), the saved copy when offline.
  if (url.origin === location.origin) {
    if (url.pathname.endsWith('meetings.json')) return // always fresh
    event.respondWith(
      fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(SHELL).then(c => c.put(req, copy)) }
        return res
      }).catch(() => caches.match(req).then(r => r || caches.match('index.html'))),
    )
    return
  }
  // jw.org artwork: saved as it's seen, so covers show offline.
  // Only plain <img> loads; the lyric card's readable (CORS) fetches go straight to jw.org.
  if (req.mode === 'no-cors' && url.hostname.endsWith('jw-cdn.org') && /\.(jpg|jpeg|png|webp)$/i.test(url.pathname)) {
    event.respondWith(
      caches.open(IMAGES).then(async c => {
        const hit = await c.match(req)
        if (hit) return hit
        const res = await fetch(req)
        if (res.ok || res.type === 'opaque') {
          await c.put(req, res.clone())
          // Keep at most about 1,500 covers; drop the oldest beyond that.
          const keys = await c.keys()
          if (keys.length > 1500) await Promise.all(keys.slice(0, 300).map(k => c.delete(k)))
        }
        return res
      }),
    )
  }
})
