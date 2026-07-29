// Tests for the service worker fetch-strategy decision table (PWA T4).
//
// The decision table in src/web/static/sw.js is a pure function (no DOM / no
// service-worker globals) so it runs under the plain node environment.
// sw.js is a classic script (module service workers are not supported in
// Firefox), so it is loaded here via createRequire instead of ESM import.
//
// Contract (design: docs/designs/pwa.md):
// - manifest.webmanifest: network-first
// - /static/icons/*: stale-while-revalidate
// - navigation requests: only the two entry pages network-first, every other
//   navigation (incl. /view/{token}) network-only, never written to Cache Storage
// - /api/* and everything else: network-only (Bearer-auth responses must never
//   be persisted)
// - activate: prune old versioned caches, keep the current one

import { createRequire } from 'node:module';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const require = createRequire(import.meta.url);
const {
  CACHE_NAME,
  PRECACHE_ASSETS,
  decideFetchStrategy,
  shouldPruneCache,
  cacheKeyFor,
  networkFirst,
} = require('../static/sw.js');

const nav = (pathname) => ({ method: 'GET', mode: 'navigate', pathname, sameOrigin: true });
const get = (pathname) => ({
  method: 'GET',
  mode: 'no-cors',
  pathname: new URL(pathname, 'https://vta.example.com').pathname,
  sameOrigin: true,
});

describe('decideFetchStrategy', () => {
  it('manifest is network-first', () => {
    expect(decideFetchStrategy(get('/static/manifest.webmanifest'))).toBe('network-first');
  });

  it('icons are stale-while-revalidate', () => {
    expect(decideFetchStrategy(get('/static/icons/icon-192.png'))).toBe('stale-while-revalidate');
    expect(decideFetchStrategy(get('/static/icons/icon-maskable-512.png'))).toBe('stale-while-revalidate');
  });

  it('entry page navigations are network-first', () => {
    expect(decideFetchStrategy(nav('/add_task_by_web'))).toBe('network-first');
    expect(decideFetchStrategy(nav('/static/index.html'))).toBe('network-first');
    expect(decideFetchStrategy(nav('/static/history.html'))).toBe('network-first');
  });

  it('other navigations (incl. /view/) are network-only', () => {
    expect(decideFetchStrategy(nav('/view/some-token'))).toBe('network-only');
    expect(decideFetchStrategy(nav('/'))).toBe('network-only');
    expect(decideFetchStrategy(nav('/api/task/123'))).toBe('network-only');
  });

  it('api requests and everything else are network-only', () => {
    expect(decideFetchStrategy(get('/api/task/123'))).toBe('network-only');
    expect(decideFetchStrategy(get('/static/css/styles.css'))).toBe('network-only');
    expect(decideFetchStrategy(get('/static/js/app.js'))).toBe('network-only');
    expect(decideFetchStrategy(get('/sw.js'))).toBe('network-only');
  });

  it('auth scripts are network-first for versioned and unversioned URLs', () => {
    expect(decideFetchStrategy(get('/static/js/auth-storage.js'))).toBe('network-first');
    expect(decideFetchStrategy(get('/static/js/auth-storage.js'))).toBe('network-first');
    expect(decideFetchStrategy(get('/static/js/auth-storage.js?v=abc123'))).toBe('network-first');
    expect(decideFetchStrategy(get('/static/js/transcript-protected-action.js'))).toBe('network-first');
    expect(decideFetchStrategy(get('/static/js/transcript-protected-action.js?v=abc123'))).toBe('network-first');
  });

  it('non-GET and cross-origin requests are network-only', () => {
    expect(decideFetchStrategy({ method: 'POST', mode: 'cors', pathname: '/api/transcribe', sameOrigin: true })).toBe('network-only');
    expect(decideFetchStrategy({ method: 'GET', mode: 'no-cors', pathname: '/static/icons/icon-192.png', sameOrigin: false })).toBe('network-only');
  });
});

describe('cache versioning', () => {
  it('cache name carries a version', () => {
    expect(CACHE_NAME).toMatch(/^vta-static-v\d+$/);
    expect(CACHE_NAME).not.toBe('vta-static-v2');
  });

  it('precache explicitly names both shared auth scripts', () => {
    expect(PRECACHE_ASSETS).toEqual([
      '/static/js/auth-storage.js',
      '/static/js/transcript-protected-action.js',
    ]);
  });

  it('activate prunes old versions but keeps the current one', () => {
    expect(shouldPruneCache('vta-static-v0')).toBe(true);
    expect(shouldPruneCache('vta-static-v2')).toBe(true);
    expect(shouldPruneCache('vta-static-v99')).toBe(true);
    expect(shouldPruneCache(CACHE_NAME)).toBe(false);
    expect(shouldPruneCache('some-other-app-cache')).toBe(false);
  });
});

describe('network-first auth script cache behavior', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('caches', { open: vi.fn() });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('updates cache after a successful network response', async () => {
    const cached = { put: vi.fn().mockResolvedValue(undefined), match: vi.fn() };
    globalThis.caches.open.mockResolvedValue(cached);
    const response = { ok: true, clone: vi.fn(() => 'response-copy') };
    globalThis.fetch.mockResolvedValue(response);
    const event = { waitUntil: vi.fn() };

    await expect(networkFirst(
      { mode: 'no-cors', url: 'https://vta.example.com/static/js/auth-storage.js?v=abc' },
      event,
    )).resolves.toBe(response);

    expect(cached.put).toHaveBeenCalledWith(
      'https://vta.example.com/static/js/auth-storage.js?v=abc',
      'response-copy',
    );
    expect(event.waitUntil).toHaveBeenCalledTimes(1);
  });

  it('falls back to the cached auth script when the network fails', async () => {
    const cachedResponse = { ok: true };
    const cached = { put: vi.fn(), match: vi.fn().mockResolvedValue(cachedResponse) };
    globalThis.caches.open.mockResolvedValue(cached);
    globalThis.fetch.mockRejectedValue(new TypeError('offline'));

    await expect(networkFirst(
      { mode: 'no-cors', url: 'https://vta.example.com/static/js/auth-storage.js?v=abc' },
      { waitUntil: vi.fn() },
    )).resolves.toBe(cachedResponse);
    expect(cached.match).toHaveBeenCalledWith(
      'https://vta.example.com/static/js/auth-storage.js?v=abc',
      { ignoreSearch: true },
    );
  });

  it('surfaces network failure when cache storage is unavailable and has no fallback', async () => {
    globalThis.caches.open.mockRejectedValue(new Error('cache unavailable'));
    globalThis.fetch.mockRejectedValue(new TypeError('offline'));

    await expect(networkFirst(
      { mode: 'no-cors', url: 'https://vta.example.com/static/js/transcript-protected-action.js' },
      { waitUntil: vi.fn() },
    )).rejects.toThrow('offline');
  });
});

describe('cacheKeyFor (Codex R1-4)', () => {
  it('navigation cache key drops the query string (share-target params)', () => {
    const shared = cacheKeyFor({
      mode: 'navigate',
      url: 'https://vta.example.com/add_task_by_web?url=https%3A%2F%2Fb23.tv%2Fx&title=t&text=s',
    });
    expect(shared).toBe('/add_task_by_web');
    // every share reuses ONE cache entry instead of persisting share content
    expect(cacheKeyFor({ mode: 'navigate', url: 'https://vta.example.com/add_task_by_web?url=other' }))
      .toBe(shared);
  });

  it('non-navigation requests keep the full URL as key', () => {
    expect(cacheKeyFor({ mode: 'no-cors', url: 'https://vta.example.com/static/manifest.webmanifest' }))
      .toBe('https://vta.example.com/static/manifest.webmanifest');
  });
});
