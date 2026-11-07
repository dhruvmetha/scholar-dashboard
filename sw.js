/* Scout's service worker: the app opens without a connection (4 November 2026, plan
   docs/superpowers/plans/2026-11-04-scout-offline.md, section 1).

   Online it changes nothing a person can see: the page and its bootstrap files come from the network, and each good
   answer is kept. When the network fails, or has not answered the page within NET_WAIT (a plane's Wi-Fi), the kept
   copy answers instead. The libraries the page loads from CDNs have versioned addresses, so they are kept on first use
   and served from here after that. The page lists the ones it loads later (sw-warm), so the reader and the notes work
   offline before they were ever opened.

   It handles GET requests only, and only for:
   - the page itself (APP_ROOT, or index.html under it) and its bootstrap files (APP_FILES);
   - the CDN libraries the page names (LIB_URL).
   Everything else goes to the network untouched: GitHub's API and raw files, annotations/, the chat bridge, PDF hosts,
   this file, any request with an Authorization header, a Range, or the cache mode 'no-store' or 'reload' (Phase 22's
   siteWarm and explicit configuration re-verification). A HEAD is never handled, so
   siteHead always reaches the server. A kept copy is only ever an answer the network gave with status 200.

   The worker never reloads a page, never tells a page about a new version, and has no controllerchange handler: Phase
   22's return check decides when the page reloads. When this file's caching changes, bump VERSION, which names the
   caches; activation deletes the caches of every other version. */
const VERSION = 5;
const SHELL = 'scout-shell-v' + VERSION, LIBS = 'scout-libs-v' + VERSION;
const ROOT = new URL('./', self.location).href;   // APP_ROOT: where index.html lives
const ROOT_PATH = new URL(ROOT).pathname;
const NET_WAIT = 4000;
const APP_FILES = ['brief_recipe.json', 'scholar_config.js', 'instance.json', 'scholar.config.json', 'manifest.webmanifest', 'icon.svg', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png', 'mycopy.js', 'mycopy-pdf.js'];
const COPY_LIBS = new Set(['https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/dist/pdf-lib.min.js', 'https://cdn.jsdelivr.net/npm/@pdf-lib/fontkit@1.1.1/dist/fontkit.umd.min.js', 'https://cdn.jsdelivr.net/gh/notofonts/noto-fonts@v20201206-phase3/hinted/ttf/NotoSans/NotoSans-Regular.ttf']);
const LIB_URL = url => COPY_LIBS.has(url) || /^https:\/\/(?:cdnjs\.cloudflare\.com\/ajax\/libs\/PapaParse\/|cdn\.jsdelivr\.net\/npm\/(?:pdfjs-dist|marked|dompurify|katex)@[0-9][^/]*\/|fonts\.googleapis\.com\/css2\?|fonts\.gstatic\.com\/)/.test(url);

/* Kept from the start: the page and its bootstrap files, so a page opened once opens offline next time */
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL);
    await Promise.all(['', ...APP_FILES].map(name =>
      fetch(ROOT + name, { cache: 'no-cache', credentials: 'same-origin', redirect: 'error' })
        .then(res => keepable(res, name === '') ? shell.put(ROOT + name, res) : null)
        .catch(() => null)));
    // Old pages may remain open for notes or reading after activation. Their versioned library URLs still work.
    const libs = await caches.open(LIBS);
    for (const name of await caches.keys()) {
      if (!/^scout-libs-v[0-9]+$/.test(name) || name === LIBS) continue;
      const old = await caches.open(name);
      for (const request of await old.keys()) {
        if (!LIB_URL(request.url) || request.headers.has('authorization')) continue;
        const current = await libs.match(request.url), response = await old.match(request);
        if (current && current.type !== 'opaque') continue;
        if (response && ((response.status === 200 && ['cors', 'basic'].includes(response.type)) || (response.type === 'opaque' && !current))) await libs.put(request.url, response);
      }
    }
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) if (name.startsWith('scout-') && name !== SHELL && name !== LIBS) await caches.delete(name);
    await self.clients.claim();
  })());
});

/* The page names library files it uses or will use (sw-warm): each one not kept yet is fetched and kept. A Google Fonts
   stylesheet and KaTeX's stylesheet are read for the font files they name. */
self.addEventListener('message', event => {
  const data = event.data || {};
  if (data.type !== 'sw-warm' || !Array.isArray(data.urls)) return;
  event.waitUntil(caches.open(LIBS).then(async cache => {
    const keep = async url => {
      if (typeof url !== 'string' || !LIB_URL(url)) return [];
      const kept = await cache.match(url);
      let res = kept && kept.type !== 'opaque' ? kept : null;
      if (!res) {
        try { res = await fetch(url, { mode: 'cors', credentials: 'omit' }); } catch (e) { return []; }
        if (!res.ok || res.status !== 200) return [];
        await cache.put(url, res.clone());
      }
      return /\.css(?:$|\?)|fonts\.googleapis\.com\/css2\?/.test(url) ? fontsIn(await res.text(), url) : [];
    };
    for (const url of data.urls) for (const font of await keep(url)) await keep(font);
  }).catch(() => {}));
});
function fontsIn(css, base) {
  const out = [];
  for (const m of css.matchAll(/url\(\s*['"]?([^'")\s]+)['"]?\s*\)/g)) {
    try { const u = new URL(m[1], base).href; if (/\.woff2(?:$|\?)/.test(u) && LIB_URL(u)) out.push(u); } catch (e) {}
  }
  return out;
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || req.headers.has('authorization') || req.headers.has('range')) return;
  if (req.cache === 'no-store' || req.cache === 'reload') return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin) {
    if (!url.pathname.startsWith(ROOT_PATH)) return;
    const rel = url.pathname.slice(ROOT_PATH.length);
    if (rel.startsWith('annotations/') || rel === 'sw.js') return;
    if (req.mode === 'navigate') {
      if ((rel === '' || rel === 'index.html')) event.respondWith(networkFirst(event, req, ROOT, true));
      return;
    }
    if (url.search) return;
    if (APP_FILES.includes(rel)) event.respondWith(networkFirst(event, req, ROOT + rel, false));
    return;
  }
  if (LIB_URL(req.url)) event.respondWith(keptFirst(event, req));
});

/* A response worth keeping: the network's own 200, same-origin; for the page, HTML */
function keepable(res, page) {
  return !!res && res.status === 200 && res.type === 'basic' && (!page || /text\/html/i.test(res.headers.get('content-type') || ''));
}
/* The network's answer, kept under key once it arrives (the worker stays alive until it is kept, even when the page
   got the kept copy) */
function fetchKeeping(event, req, key, page) {
  const net = fetch(req);
  event.waitUntil(net.then(res => keepable(res, page) ? caches.open(SHELL).then(cache => cache.put(key, res.clone())) : null).catch(() => {}));
  return net;
}
/* The network's answer when it comes within NET_WAIT; else the kept copy; else the network's answer whenever it comes */
async function networkFirst(event, req, key, page) {
  const net = fetchKeeping(event, req, key, page);
  let timer;
  try { return await Promise.race([net, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('slow network')), NET_WAIT); })]); }
  catch (e) { return (await caches.match(key, { cacheName: SHELL })) || net.catch(() => Response.error()); }
  finally { clearTimeout(timer); }
}
/* A library file (its address carries its version): the kept copy, else the network's, kept for next time. An opaque
   copy (from a tag without crossorigin) is never handed to a request that reads the file. */
async function keptFirst(event, req) {
  const cache = await caches.open(LIBS), kept = await cache.match(req.url);
  if (kept && !(kept.type === 'opaque' && req.mode === 'cors')) return kept;
  let res;
  try { res = await fetch(req); } catch (e) { return Response.error(); }   // a network error for the page, as without the worker
  if ((res.status === 200 && (res.type === 'cors' || res.type === 'basic')) || (res.type === 'opaque' && !kept)) event.waitUntil(cache.put(req.url, res.clone()).catch(() => {}));
  return res;
}
