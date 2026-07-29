/*
 * Service Worker for the VideoTranscriptAPI PWA (design: docs/designs/pwa.md T4).
 *
 * Served from the root path (GET /sw.js, see api/app.py) so its scope covers
 * "/". The fetch policy is a strict whitelist -- with scope "/" every
 * same-origin request passes through here:
 *   - /static/manifest.webmanifest : network-first (tiny file, always fresh)
 *   - /static/icons/*              : stale-while-revalidate
 *   - navigations to the two entry pages (index/history): network-first
 *   - every other navigation (incl. /view/{token}): network-only
 *   - /api/* and everything else   : network-only, never persisted
 *     (Bearer-auth responses must never land in Cache Storage)
 *
 * The cache name is versioned; activate prunes older versions. Icon/manifest
 * changes MUST bump CACHE_NAME (see docs/guides/pwa.md). No skipWaiting /
 * forced reload.
 *
 * The decision table below is a pure function (no SW globals) so vitest can
 * exercise it under the plain node environment; this file stays a classic
 * script because module service workers are not supported in Firefox.
 */

// Bump this version whenever sw.js, icons or the manifest change.
const CACHE_NAME = 'vta-static-v2';
const CACHE_PREFIX = 'vta-static-';

// Navigation entry pages eligible for the network-first cache.
const ENTRY_PAGES = new Set([
  '/add_task_by_web',
  '/static/index.html',
  '/static/history.html',
]);

/**
 * Decide the fetch strategy for a request.
 *
 * @param {object} req Normalized request descriptor.
 * @param {string} req.method HTTP method (GET/POST/...).
 * @param {string} req.mode Fetch mode ('navigate' for page loads).
 * @param {string} req.pathname URL pathname (same-origin).
 * @param {boolean} req.sameOrigin Whether the request is same-origin.
 * @returns {'network-first'|'stale-while-revalidate'|'network-only'}
 */
function decideFetchStrategy(req) {
  if (req.method !== 'GET' || !req.sameOrigin) {
    return 'network-only';
  }
  if (req.mode === 'navigate') {
    return ENTRY_PAGES.has(req.pathname) ? 'network-first' : 'network-only';
  }
  if (req.pathname.startsWith('/api/')) {
    return 'network-only';
  }
  if (req.pathname === '/static/manifest.webmanifest') {
    return 'network-first';
  }
  if (req.pathname.startsWith('/static/icons/')) {
    return 'stale-while-revalidate';
  }
  return 'network-only';
}

/**
 * Whether a Cache Storage entry should be deleted on activate.
 *
 * @param {string} name Cache name.
 * @returns {boolean} True for our own outdated versioned caches only.
 */
function shouldPruneCache(name) {
  return name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME;
}

/**
 * Normalize the Cache Storage key for a request (Codex R1-4).
 * Navigations (share-target launches carry ?url=&title=&text=) key by
 * pathname only, so every share reuses one entry and share content does
 * not accumulate in Cache Storage keys. Residual note: the cached
 * Response object's `url` metadata still carries the full share URL --
 * accepted (own device, own origin), recorded in the ops guide backlog
 * (Codex R5-4).
 *
 * @param {{mode: string, url: string}} request Request-like descriptor.
 * @returns {string} Cache key.
 */
function cacheKeyFor(request) {
  if (request.mode === 'navigate') {
    return new URL(request.url).pathname;
  }
  return request.url;
}

// ---- SW glue (skipped outside a service worker global scope, e.g. vitest) ----

const IS_SERVICE_WORKER =
  typeof self !== 'undefined' &&
  typeof caches !== 'undefined' &&
  typeof self.addEventListener === 'function' &&
  typeof window === 'undefined';

if (IS_SERVICE_WORKER) {
  self.addEventListener('install', () => {
    // No precache, no skipWaiting: the new worker activates naturally once
    // no old-version page is open.
  });

  self.addEventListener('activate', (event) => {
    event.waitUntil(
      caches.keys().then((names) =>
        Promise.all(names.filter(shouldPruneCache).map((name) => caches.delete(name)))
      )
    );
  });

  self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    const strategy = decideFetchStrategy({
      method: event.request.method,
      mode: event.request.mode,
      pathname: url.pathname,
      sameOrigin: url.origin === self.location.origin,
    });

    if (strategy === 'network-first') {
      event.respondWith(networkFirst(event.request, event));
    } else if (strategy === 'stale-while-revalidate') {
      event.respondWith(staleWhileRevalidate(event.request, event));
    }
    // network-only: do not call respondWith -> default browser fetch,
    // nothing is written to Cache Storage.
  });

  // E5 回退通道（Codex R1-2）：Android Chrome 上通知经
  // reg.showNotification 发出，点击在这里聚焦/打开结果页。
  self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl =
      (event.notification.data && event.notification.data.url) || '/add_task_by_web';
    event.waitUntil(
      self.clients
        .matchAll({ type: 'window', includeUncontrolled: true })
        .then((windowClients) => {
          // 只处理已在目标 URL 的 client；否则另开窗口，不覆盖无关标签页（Codex R3-3）
          const targetPath = new URL(targetUrl, self.location.origin).pathname;
          const match = windowClients.find(
            (client) => new URL(client.url).pathname === targetPath
          );
          if (match) {
            // 同 URL navigate 等价刷新：旧 processing HTML 也能拿到最新
            // 服务端渲染，再聚焦（Codex R7-2）
            return match
              .navigate(targetUrl)
              .then((client) => (client || match).focus());
          }
          return self.clients.openWindow(targetUrl);
        })
    );
  });
}

async function networkFirst(request, event) {
  let cache = null;
  try {
    cache = await caches.open(CACHE_NAME);
  } catch (cacheErr) {
    // Cache Storage 被禁用/已满：缓存不可用不拖垮请求，回退纯网络（Codex R10-3）
    console.warn('cache open failed, network-only fallback:', cacheErr);
  }
  const cacheKey = cacheKeyFor(request);
  try {
    const response = await fetch(request);
    if (response.ok && cache) {
      // 不阻塞响应；waitUntil 保证 worker 活到写入完成（Codex R1-5）
      event.waitUntil(cache.put(cacheKey, response.clone()).catch(() => {}));
    }
    return response;
  } catch (err) {
    if (cache) {
      const cached = await cache.match(cacheKey, { ignoreSearch: true }).catch(() => null);
      if (cached) {
        return cached;
      }
    }
    throw err; // 网络错误本身不吞
  }
}

async function staleWhileRevalidate(request, event) {
  let cache = null;
  try {
    cache = await caches.open(CACHE_NAME);
  } catch (cacheErr) {
    // 同上（Codex R10-3）：直接回退网络，网络错误自然向上抛
    console.warn('cache open failed, network-only fallback:', cacheErr);
    return fetch(request);
  }
  const cached = await cache.match(request).catch(() => null);
  const revalidate = fetch(request).then((response) => {
    if (response.ok) {
      // await 写入后再算作 revalidate 完成（Codex R1-5）；
      // 写缓存失败不影响把网络响应交给页面（Codex R4-2）
      return cache
        .put(request, response.clone())
        .catch((putErr) => console.warn('icon cache put failed:', putErr))
        .then(() => response);
    }
    return response;
  });
  // 后台 revalidate 期间保持 worker 存活
  event.waitUntil(revalidate.catch(() => {}));
  if (cached) {
    return cached;
  }
  return revalidate;
}

// Export for vitest (plain node, CJS interop via createRequire).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { CACHE_NAME, ENTRY_PAGES, decideFetchStrategy, shouldPruneCache, cacheKeyFor };
}
