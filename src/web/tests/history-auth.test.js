import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const historySource = readFileSync(
  fileURLToPath(new URL('../static/history.html', import.meta.url)),
  'utf8'
);

describe('history page unified auth contract', () => {
  it('loads shared auth before history inline code and removes remember dual-track UI', () => {
    const authIndex = historySource.indexOf('/static/js/auth-storage.js');
    const inlineIndex = historySource.indexOf('<script>\n// ===================== 状态 =====================');
    expect(authIndex).toBeGreaterThanOrEqual(0);
    expect(authIndex).toBeLessThan(inlineIndex);
    expect(historySource).not.toContain('rememberKey');
    expect(historySource).not.toContain('vta_api_key_persist');
    expect(historySource).not.toContain('sessionStorage.setItem(\'vta_api_key\'');
  });

  it('reads canonical auth and builds every Authorization header through the module', () => {
    expect(historySource).toContain('VideoTranscriptAuthStorage');
    expect(historySource).toContain('authStorage.buildAuthHeaders()');
    expect(historySource).toContain('authStorage.readAuthToken()');
    expect(historySource).not.toContain("'Authorization': `Bearer ${currentApiKey}`");
  });

  it('resets private state atomically and aborts in-flight requests on change/clear', () => {
    expect(historySource).toContain('function resetPrivateHistoryState');
    expect(historySource).toContain('abortPrivateHistoryRequests');
    expect(historySource).toContain('selectedSet.clear()');
    expect(historySource).toContain('_filteredItems = null');
    expect(historySource).toContain('summaryVisible = false');
    expect(historySource).toContain('currentMasked =');
    expect(historySource).toContain('clearAuthTokenIfMatch');
  });

  it('compare-and-clears only the request snapshot after a 401', () => {
    expect(historySource).toContain('const requestSnapshot = authStorage.snapshotAuthToken()');
    expect(historySource).toContain('authStorage.clearAuthTokenIfMatch(requestSnapshot)');
    expect(historySource).toContain('if (cleared) {');
    expect(historySource).toContain('resetPrivateHistoryState();');
    expect(historySource).not.toContain('clearAuthToken();\n        showStatus(\'err\', \'API Key 无效\'');
  });

  it('fails closed when shared auth is missing and retains HTML escaping', () => {
    expect(historySource).toContain('安全错误：统一鉴权模块加载失败，已禁用历史私有操作');
    expect(historySource).toContain('historyAuthUnavailable');
    expect(historySource).toContain('esc(item.title)');
    expect(historySource).toContain('esc(item.view_token)');
    expect(historySource).toContain('esc(w)');
    expect(historySource).toContain(".replace(/'/g,'&#39;')");
  });
});
