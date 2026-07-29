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
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { CACHE_NAME, decideFetchStrategy, shouldPruneCache } = require('../static/sw.js');

const nav = (pathname) => ({ method: 'GET', mode: 'navigate', pathname, sameOrigin: true });
const get = (pathname) => ({ method: 'GET', mode: 'no-cors', pathname, sameOrigin: true });

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

  it('non-GET and cross-origin requests are network-only', () => {
    expect(decideFetchStrategy({ method: 'POST', mode: 'cors', pathname: '/api/transcribe', sameOrigin: true })).toBe('network-only');
    expect(decideFetchStrategy({ method: 'GET', mode: 'no-cors', pathname: '/static/icons/icon-192.png', sameOrigin: false })).toBe('network-only');
  });
});

describe('cache versioning', () => {
  it('cache name carries a version', () => {
    expect(CACHE_NAME).toMatch(/^vta-static-v\d+$/);
  });

  it('activate prunes old versions but keeps the current one', () => {
    expect(shouldPruneCache('vta-static-v0')).toBe(true);
    expect(shouldPruneCache('vta-static-v99')).toBe(true);
    expect(shouldPruneCache(CACHE_NAME)).toBe(false);
    expect(shouldPruneCache('some-other-app-cache')).toBe(false);
  });
});
