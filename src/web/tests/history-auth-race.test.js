import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';

const historySource = readFileSync(
  fileURLToPath(new URL('../static/history.html', import.meta.url)),
  'utf8'
);
const inlineScriptStart = historySource.indexOf(
  '<script>\n// ===================== 状态 ====================='
);
const inlineScriptEnd = historySource.indexOf('</script>', inlineScriptStart);
const inlineScript = historySource.slice(
  inlineScriptStart + '<script>'.length,
  inlineScriptEnd
);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function jsonResponse(body, status = 200) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: vi.fn(async () => body),
  };
}

function filterResponse(masked = 'old-mask') {
  return jsonResponse({
    code: 200,
    data: { api_key_masked: masked, webhooks: [], platforms: [], authors: [] },
  });
}

function historyResponse(title, viewToken) {
  return jsonResponse({
    code: 200,
    data: {
      api_key_masked: `${viewToken}-mask`,
      items: [{
        title,
        view_token: viewToken,
        status: 'success',
        request_time: '2026-07-29T12:00:00',
        platform: 'youtube',
      }],
      total: 1,
    },
  });
}

function createHistoryFixture({ token = '' } = {}) {
  const dom = new JSDOM(historySource, {
    runScripts: 'outside-only',
    url: 'https://example.test/static/history.html',
  });
  const state = { token };
  const authStorage = {
    readAuthToken: vi.fn(() => state.token),
    writeAuthToken: vi.fn((nextToken) => {
      state.token = nextToken;
      return true;
    }),
    clearAuthToken: vi.fn(() => { state.token = ''; }),
    snapshotAuthToken: vi.fn(() => state.token),
    buildAuthHeaders: vi.fn(() => (state.token ? { Authorization: `Bearer ${state.token}` } : {})),
    clearAuthTokenIfMatch: vi.fn((snapshot) => {
      if (state.token !== snapshot) return false;
      state.token = '';
      return true;
    }),
  };
  dom.window.VideoTranscriptAuthStorage = authStorage;
  dom.window.fetch = vi.fn();
  dom.window.console.error = vi.fn();
  dom.window.eval(inlineScript);
  return { dom, authStorage, state, fetchMock: dom.window.fetch };
}

async function flushPromises() {
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
}

describe('history private request generation guards', () => {
  it('does not clear the canonical token when an empty input is queried', async () => {
    const fixture = createHistoryFixture({ token: 'canonical-token' });
    const input = fixture.dom.window.document.getElementById('apiKeyInput');
    input.value = '';

    await fixture.dom.window.loadHistory(0);

    expect(fixture.authStorage.clearAuthToken).not.toHaveBeenCalled();
    expect(fixture.state.token).toBe('canonical-token');
    expect(fixture.dom.window.document.getElementById('authStatus').textContent)
      .toBe('请输入访问令牌');
  });

  it('does not apply late filter options after reset invalidates the request', async () => {
    const fixture = createHistoryFixture();
    const oldFilter = deferred();
    fixture.state.token = 'old-token';
    fixture.dom.window.document.getElementById('apiKeyInput').value = 'old-token';
    fixture.fetchMock.mockReturnValueOnce(oldFilter.promise);

    fixture.dom.window.loadHistory(0);
    await flushPromises();
    fixture.dom.window.resetPrivateHistoryState();
    oldFilter.resolve(filterResponse());
    await flushPromises();

    expect(fixture.fetchMock).toHaveBeenCalledTimes(1);
    expect(fixture.dom.window.document.getElementById('filterBar').style.display).toBe('none');
    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .toContain('请输入访问令牌后点击查询');
  });

  it('does not render a late history response or AbortError after reset', async () => {
    const fixture = createHistoryFixture();
    const oldHistory = deferred();
    fixture.state.token = 'old-token';
    fixture.dom.window.document.getElementById('apiKeyInput').value = 'old-token';
    fixture.fetchMock
      .mockResolvedValueOnce(filterResponse())
      .mockReturnValueOnce(oldHistory.promise);

    const load = fixture.dom.window.loadHistory(0);
    await flushPromises();
    expect(fixture.fetchMock).toHaveBeenCalledTimes(2);
    fixture.dom.window.resetPrivateHistoryState();
    oldHistory.resolve(historyResponse('old title', 'old-view'));
    await load;

    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .toContain('请输入访问令牌后点击查询');
    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .not.toContain('old title');

    const aborting = deferred();
    fixture.fetchMock
      .mockResolvedValueOnce(filterResponse())
      .mockReturnValueOnce(aborting.promise);
    fixture.dom.window.loadHistory(0);
    await flushPromises();
    fixture.dom.window.resetPrivateHistoryState();
    aborting.reject(new DOMException('aborted', 'AbortError'));
    await flushPromises();

    expect(fixture.dom.window.document.getElementById('authStatus').textContent)
      .not.toContain('网络错误');
  });

  it('allows a new token generation to render after the old one is reset', async () => {
    const fixture = createHistoryFixture();
    fixture.state.token = 'new-token';
    fixture.dom.window.document.getElementById('apiKeyInput').value = 'new-token';
    fixture.fetchMock
      .mockResolvedValueOnce(filterResponse('new-mask'))
      .mockResolvedValueOnce(historyResponse('new title', 'new-view'));
    await fixture.dom.window.loadHistory(0);

    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .toContain('new title');
  });

  it('keeps the newest same-token page response when pagination resolves out of order', async () => {
    const fixture = createHistoryFixture();
    fixture.state.token = 'stable-token';
    fixture.dom.window.document.getElementById('apiKeyInput').value = 'stable-token';
    const page20 = deferred();
    const page40 = deferred();
    fixture.fetchMock.mockImplementation((url) => (
      url.includes('offset=20') ? page20.promise : page40.promise
    ));

    const olderPage = fixture.dom.window.loadHistory(1);
    await flushPromises();
    const newerPage = fixture.dom.window.loadHistory(2);
    await flushPromises();
    expect(fixture.fetchMock).toHaveBeenCalledTimes(2);

    page40.resolve(historyResponse('page-40-title', 'page-40-view'));
    await flushPromises();
    page20.resolve(historyResponse('page-20-title', 'page-20-view'));
    await Promise.all([olderPage, newerPage]);

    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .toContain('page-40-title');
    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .not.toContain('page-20-title');
  });

  it('keeps the newest same-token filter response when filters resolve out of order', async () => {
    const fixture = createHistoryFixture();
    fixture.state.token = 'stable-token';
    fixture.dom.window.document.getElementById('apiKeyInput').value = 'stable-token';
    const oldFilter = deferred();
    const newFilter = deferred();
    const queryInput = fixture.dom.window.document.getElementById('filterQ');
    fixture.fetchMock.mockImplementation((url) => (
      url.includes('q=old') ? oldFilter.promise : newFilter.promise
    ));

    queryInput.value = 'old';
    const olderQuery = fixture.dom.window.loadHistory(1);
    await flushPromises();
    queryInput.value = 'new';
    const newerQuery = fixture.dom.window.loadHistory(1);
    await flushPromises();
    expect(fixture.fetchMock).toHaveBeenCalledTimes(2);

    newFilter.resolve(historyResponse('new-filter-title', 'new-filter-view'));
    await flushPromises();
    oldFilter.resolve(historyResponse('old-filter-title', 'old-filter-view'));
    await Promise.all([olderQuery, newerQuery]);

    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .toContain('new-filter-title');
    expect(fixture.dom.window.document.getElementById('listArea').textContent)
      .not.toContain('old-filter-title');
  });
});
