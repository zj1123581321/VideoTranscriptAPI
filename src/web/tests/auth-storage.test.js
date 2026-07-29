import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const authStoragePath = require.resolve('../static/js/auth-storage.js');

let dom;
let authStorage;

function loadAuthStorage() {
  delete require.cache[authStoragePath];
  return require(authStoragePath);
}

function installDom() {
  dom = new JSDOM('<!doctype html>', { url: 'https://vta.test/' });
  globalThis.window = dom.window;
  globalThis.localStorage = dom.window.localStorage;
  globalThis.sessionStorage = dom.window.sessionStorage;
  globalThis.StorageEvent = dom.window.StorageEvent;
  authStorage = loadAuthStorage();
}

function uninstallDom() {
  dom?.window.close();
  delete globalThis.window;
  delete globalThis.localStorage;
  delete globalThis.sessionStorage;
  delete globalThis.StorageEvent;
  delete globalThis.VideoTranscriptAuthStorage;
  vi.restoreAllMocks();
}

beforeEach(installDom);
afterEach(uninstallDom);

describe('auth token encoding', () => {
  it('round-trips Base64 + reverse with the required suffix', () => {
    const encoded = authStorage.encodeAuthToken('token-中文');
    expect(encoded).toBeTypeOf('string');
    expect(encoded).not.toContain('token-中文');
    expect(authStorage.decodeAuthToken(encoded)).toBe('token-中文');
  });

  it('rejects corrupted payloads and suffix tampering as absent', () => {
    expect(authStorage.decodeAuthToken('not-base64')).toBeNull();
    const encoded = authStorage.encodeAuthToken('secret');
    const reversed = encoded.split('').reverse().join('');
    const bytes = Buffer.from(reversed, 'base64');
    const tampered = Buffer.from(bytes.toString('utf8').replace('vta_encrypt_key_2024', 'wrong_suffix')).toString('base64');
    expect(authStorage.decodeAuthToken(tampered.split('').reverse().join(''))).toBeNull();
  });
});

describe('auth token storage contract', () => {
  it('uses canonical vta_bearer_token before all legacy aliases', () => {
    localStorage.setItem('api_key', 'legacy-api');
    localStorage.setItem('vta_api_key_persist', 'legacy-persist');
    sessionStorage.setItem('vta_api_key', 'legacy-session');
    authStorage.writeAuthToken('canonical-token', { remember: true });
    expect(localStorage.getItem('vta_bearer_token')).toBeTypeOf('string');
    expect(authStorage.readAuthToken()).toBe('canonical-token');
  });

  it('falls back in api_key, persisted, session priority when migration is not sealed', () => {
    localStorage.setItem('api_key', 'legacy-api');
    localStorage.setItem('vta_api_key_persist', 'legacy-persist');
    sessionStorage.setItem('vta_api_key', 'legacy-session');
    expect(authStorage.readAuthToken()).toBe('legacy-api');
    localStorage.removeItem('api_key');
    expect(authStorage.readAuthToken()).toBe('legacy-persist');
    localStorage.removeItem('vta_api_key_persist');
    expect(authStorage.readAuthToken()).toBe('legacy-session');
  });

  it('writes canonical storage, removes aliases, and seals migration', () => {
    localStorage.setItem('api_key', 'legacy-api');
    localStorage.setItem('vta_api_key_persist', 'legacy-persist');
    sessionStorage.setItem('vta_api_key', 'legacy-session');
    expect(authStorage.writeAuthToken('chosen-token', { remember: true })).toBe(true);
    expect(localStorage.getItem('api_key')).toBeNull();
    expect(localStorage.getItem('vta_api_key_persist')).toBeNull();
    expect(sessionStorage.getItem('vta_api_key')).toBeNull();
    expect(localStorage.getItem('vta_auth_migration_v1')).toBe('1');
    expect(authStorage.readAuthToken()).toBe('chosen-token');
  });

  it('migrates the selected legacy alias and never resurrects old credentials', () => {
    localStorage.setItem('api_key', 'legacy-api');
    sessionStorage.setItem('vta_api_key', 'legacy-session');
    expect(authStorage.migrateAuthToken()).toBe('legacy-api');
    expect(authStorage.readAuthToken()).toBe('legacy-api');
    localStorage.removeItem('vta_bearer_token');
    expect(authStorage.readAuthToken()).toBeNull();
    localStorage.setItem('api_key', 'stale-after-migration');
    sessionStorage.setItem('vta_api_key', 'stale-session-after-migration');
    expect(authStorage.readAuthToken()).toBeNull();
  });

  it('clear seals aliases and removes canonical credentials', () => {
    authStorage.writeAuthToken('token-to-clear', { remember: true });
    expect(authStorage.clearAuthToken()).toBe(true);
    expect(authStorage.readAuthToken()).toBeNull();
    localStorage.setItem('api_key', 'old-after-clear');
    localStorage.setItem('vta_api_key_persist', 'old-persist-after-clear');
    sessionStorage.setItem('vta_api_key', 'old-session-after-clear');
    expect(authStorage.readAuthToken()).toBeNull();
  });

  it('rejects control characters without persisting them', () => {
    expect(authStorage.writeAuthToken('bad\r\nBearer forged', { remember: true })).toBe(false);
    expect(localStorage.getItem('vta_bearer_token')).toBeNull();
    expect(authStorage.buildAuthHeaders()).toEqual({});
  });
});

describe('auth token snapshots and headers', () => {
  it('builds the unified Bearer header without exposing token in logs', () => {
    const token = 'secret-header-token';
    authStorage.writeAuthToken(token, { remember: true });
    expect(authStorage.buildAuthHeaders()).toEqual({ Authorization: `Bearer ${token}` });
    expect(authStorage.buildAuthHeaders({ 'X-Request': '1' })).toEqual({
      'X-Request': '1',
      Authorization: `Bearer ${token}`,
    });
  });

  it('compare-and-clears only when the current snapshot still matches', () => {
    authStorage.writeAuthToken('first-token', { remember: true });
    const snapshot = authStorage.snapshotAuthToken();
    authStorage.writeAuthToken('second-token', { remember: true });
    expect(authStorage.clearAuthTokenIfMatch(snapshot)).toBe(false);
    expect(authStorage.readAuthToken()).toBe('second-token');
    const current = authStorage.snapshotAuthToken();
    expect(authStorage.compareAndClearAuthToken(current)).toBe(true);
    expect(authStorage.readAuthToken()).toBeNull();
  });
});

describe('auth storage failure degradation', () => {
  it('falls back to memory on SecurityError and warns once without logging token', () => {
    const token = 'memory-only-secret';
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(Object.getPrototypeOf(localStorage), 'setItem').mockImplementation(() => {
      const error = new Error('blocked');
      error.name = 'SecurityError';
      throw error;
    });
    expect(authStorage.writeAuthToken(token, { remember: true })).toBe(true);
    expect(authStorage.readAuthToken()).toBe(token);
    authStorage.writeAuthToken(token, { remember: true });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls.flat().join(' ')).not.toContain(token);
  });

  it('falls back to memory on QuotaExceededError', () => {
    vi.spyOn(Object.getPrototypeOf(localStorage), 'setItem').mockImplementation(() => {
      const error = new Error('full');
      error.name = 'QuotaExceededError';
      throw error;
    });
    expect(authStorage.writeAuthToken('quota-secret', { remember: true })).toBe(true);
    expect(authStorage.readAuthToken()).toBe('quota-secret');
  });
});

describe('auth storage events and browser compatibility', () => {
  it('clears session aliases on storage events and does not revive stale credentials', () => {
    authStorage.migrateAuthToken('migrated-token');
    sessionStorage.setItem('vta_api_key', 'stale-session');
    window.dispatchEvent(new StorageEvent('storage', { key: 'vta_api_key', newValue: 'external' }));
    expect(sessionStorage.getItem('vta_api_key')).toBeNull();
    localStorage.removeItem('vta_bearer_token');
    localStorage.setItem('api_key', 'stale-api');
    expect(authStorage.readAuthToken()).toBeNull();
  });

  it('exposes the same auth API on a browser global without CommonJS', () => {
    const source = readFileSync(fileURLToPath(new URL('../static/js/auth-storage.js', import.meta.url)), 'utf8');
    const context = { console, btoa, atob, setTimeout, clearTimeout };
    context.globalThis = context;
    vm.runInNewContext(source, context, { filename: 'auth-storage.js' });
    expect(context.VideoTranscriptAuthStorage).toBeDefined();
    expect(context.VideoTranscriptAuthStorage.buildAuthHeaders()).toEqual({});
  });
});
