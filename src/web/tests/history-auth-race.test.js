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
});
