import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const authStoragePath = require.resolve('../static/js/auth-storage.js');
const appPath = require.resolve('../static/js/app.js');
const appSource = readFileSync(
  fileURLToPath(new URL('../static/js/app.js', import.meta.url)),
  'utf8'
);
const indexSource = readFileSync(
  fileURLToPath(new URL('../static/index.html', import.meta.url)),
  'utf8'
);

let dom;
let authStorage;

function loadAuthStorage() {
  delete require.cache[authStoragePath];
  return require(authStoragePath);
}

function loadApp() {
  delete require.cache[appPath];
  return require(appPath);
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
  delete globalThis.document;
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

  it('does not clear a newer persisted canonical token before its storage event arrives', () => {
    localStorage.removeItem('vta_auth_migration_v1');
    const storagePrototype = Object.getPrototypeOf(localStorage);
    const originalSetItem = storagePrototype.setItem;
    vi.spyOn(storagePrototype, 'setItem').mockImplementation(function setItem(key, value) {
      if (key === 'vta_auth_migration_v1') {
        const error = new Error('full');
        error.name = 'QuotaExceededError';
        throw error;
      }
      return originalSetItem.call(this, key, value);
    });
    expect(authStorage.writeAuthToken('old-memory-token')).toBe(true);
    vi.restoreAllMocks();

    const encodedNewToken = authStorage.encodeAuthToken('new-persisted-token');
    localStorage.setItem('vta_bearer_token', encodedNewToken);
    const oldSnapshot = authStorage.snapshotAuthToken();

    expect(oldSnapshot).toBe('old-memory-token');
    expect(authStorage.clearAuthTokenIfMatch(oldSnapshot)).toBe(false);
    expect(localStorage.getItem('vta_bearer_token')).toBe(encodedNewToken);
    expect(authStorage.decodeAuthToken(localStorage.getItem('vta_bearer_token')))
      .toBe('new-persisted-token');
  });

  it('keeps memory fallback compare-clear semantics when localStorage is unreadable', () => {
    const storagePrototype = Object.getPrototypeOf(localStorage);
    for (const method of ['getItem', 'setItem', 'removeItem']) {
      vi.spyOn(storagePrototype, method).mockImplementation(() => {
        const error = new Error('blocked');
        error.name = 'SecurityError';
        throw error;
      });
    }

    expect(authStorage.writeAuthToken('memory-only-token')).toBe(true);
    const snapshot = authStorage.snapshotAuthToken();
    expect(snapshot).toBe('memory-only-token');
    expect(authStorage.clearAuthTokenIfMatch(snapshot)).toBe(true);
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
  it('syncs a valid canonical storage event after memory fallback', () => {
    localStorage.removeItem('vta_auth_migration_v1');
    const storagePrototype = Object.getPrototypeOf(localStorage);
    const originalSetItem = storagePrototype.setItem;
    vi.spyOn(storagePrototype, 'setItem').mockImplementation(function setItem(key, value) {
      if (key === 'vta_auth_migration_v1') {
        const error = new Error('full');
        error.name = 'QuotaExceededError';
        throw error;
      }
      return originalSetItem.call(this, key, value);
    });
    expect(authStorage.writeAuthToken('old-memory-token')).toBe(true);
    vi.restoreAllMocks();
    expect(authStorage.snapshotAuthToken()).toBe('old-memory-token');

    const encodedNewToken = authStorage.encodeAuthToken('new-canonical-token');
    localStorage.setItem('vta_bearer_token', encodedNewToken);
    window.dispatchEvent(new StorageEvent('storage', {
      key: 'vta_bearer_token',
      newValue: encodedNewToken,
    }));

    expect(authStorage.snapshotAuthToken()).toBe('new-canonical-token');
    expect(authStorage.clearAuthTokenIfMatch('old-memory-token')).toBe(false);
    expect(localStorage.getItem('vta_bearer_token')).toBe(encodedNewToken);
  });

  it('rejects a malformed canonical storage event while in memory fallback', () => {
    localStorage.removeItem('vta_auth_migration_v1');
    const storagePrototype = Object.getPrototypeOf(localStorage);
    const originalSetItem = storagePrototype.setItem;
    vi.spyOn(storagePrototype, 'setItem').mockImplementation(function setItem(key, value) {
      if (key === 'vta_auth_migration_v1') {
        const error = new Error('full');
        error.name = 'QuotaExceededError';
        throw error;
      }
      return originalSetItem.call(this, key, value);
    });
    expect(authStorage.writeAuthToken('old-memory-token')).toBe(true);
    vi.restoreAllMocks();

    localStorage.setItem('vta_bearer_token', 'corrupted-canonical-value');
    window.dispatchEvent(new StorageEvent('storage', {
      key: 'vta_bearer_token',
      newValue: 'corrupted-canonical-value',
    }));

    expect(authStorage.snapshotAuthToken()).toBeNull();
  });

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

describe('homepage auth integration contract', () => {
  it('delegates token reads, writes, and clears to the shared auth module', () => {
    const app = loadApp();
    const key = 'vta_bearer_token';
    expect(app.StorageManager.get(key)).toBeNull();
    expect(app.StorageManager.set(key, 'homepage-token')).toBe(true);
    expect(authStorage.readAuthToken()).toBe('homepage-token');
    expect(app.StorageManager.get(key)).toBe('homepage-token');
    expect(app.StorageManager.remove(key)).toBe(true);
    expect(authStorage.readAuthToken()).toBeNull();
  });

  it('constructs API Authorization through buildAuthHeaders', async () => {
    const app = loadApp();
    authStorage.writeAuthToken('request-token', { remember: true });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ code: 202, data: { task_id: 'task-1' } }),
    });
    await app.APIManager.submitTranscription('https://example.com/video', false);
    const [, request] = globalThis.fetch.mock.calls[0];
    expect(request.headers.Authorization).toBe('Bearer request-token');
    expect(appSource).toContain('authStorage.buildAuthHeaders()');
  });

  it('uses a cached token without an API-key prompt', async () => {
    const app = loadApp();
    authStorage.writeAuthToken('cached-token', { remember: true });
    const prompt = vi.spyOn(window, 'prompt').mockImplementation(() => {
      throw new Error('unexpected API-key prompt');
    });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ code: 202, data: { task_id: 'task-2' } }),
    });
    await app.APIManager.submitTranscription('https://example.com/video', false);
    expect(prompt).not.toHaveBeenCalled();
  });

  it('loads auth-storage before app.js and has an explicit bootstrap failure path', () => {
    const authIndex = indexSource.indexOf('/static/js/auth-storage.js');
    const appIndex = indexSource.indexOf('/static/js/app.js');
    expect(authIndex).toBeGreaterThanOrEqual(0);
    expect(authIndex).toBeLessThan(appIndex);
    expect(appSource).toContain('VideoTranscriptAuthStorage');
    expect(appSource).toContain('安全错误：统一鉴权模块加载失败，已禁用受保护操作');
    expect(appSource).toContain('禁用受保护操作');
  });

  it('fails closed when the shared auth script is unavailable', async () => {
    const app = loadApp();
    globalThis.document = dom.window.document;
    dom.window.document.body.innerHTML = `
      <button id="submit-btn"><span class="btn-icon"></span><span class="btn-text"></span></button>
      <input id="bearer-token">
      <div id="status-container"><div id="status-content"></div></div>
    `;
    dom.window.HTMLElement.prototype.scrollIntoView = vi.fn();
    delete globalThis.VideoTranscriptAuthStorage;
    app.disableProtectedActions();
    expect(document.getElementById('submit-btn').disabled).toBe(true);
    expect(document.getElementById('bearer-token').disabled).toBe(true);
    expect(document.getElementById('status-content').textContent).toContain(
      '安全错误：统一鉴权模块加载失败，已禁用受保护操作'
    );
    expect(app.StorageManager.get('vta_bearer_token')).toBeNull();
    expect(app.StorageManager.set('vta_bearer_token', 'must-not-persist')).toBe(false);
    await expect(
      app.APIManager.submitTranscription('https://example.com/video', false)
    ).rejects.toThrow('安全错误：统一鉴权模块加载失败，已禁用受保护操作');
  });

  it('keeps URL preview escaping and removes the legacy token implementation', () => {
    expect(appSource).toContain('escapeHTML(result.url)');
    expect(appSource).toContain('escapeHTML(result.display)');
    expect(appSource).not.toContain('simpleEncrypt(value)');
    expect(appSource).not.toContain('simpleDecrypt(value)');
  });
});
