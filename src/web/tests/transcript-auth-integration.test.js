import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const templatePath = path.resolve(__dirname, '../templates/transcript.html');
const templateSource = fs.readFileSync(templatePath, 'utf8');
const controllerScriptMarker = '<script src="/static/js/transcript-protected-action.js?v={{ asset_v }}"></script>';

function adapterSource() {
  const markerPosition = templateSource.indexOf(controllerScriptMarker);
  const scriptStart = templateSource.indexOf('<script>', markerPosition + controllerScriptMarker.length);
  const scriptEnd = templateSource.indexOf('</script>', scriptStart);
  return templateSource
    .slice(scriptStart + '<script>'.length, scriptEnd)
    .replace('{{ view_token|tojson }}', JSON.stringify('view-token-1'));
}

function createFixture({ token = 'cached-token', withAuth = true, withController = true } = {}) {
  const dom = new JSDOM(`<!doctype html><body>
    <div id="protectedActionAuthStatus"></div>
    <dialog id="protectedActionAuthDialog" aria-labelledby="protectedActionAuthTitle" aria-describedby="protectedActionAuthDescription">
      <form id="protectedActionAuthForm">
        <h3 id="protectedActionAuthTitle">输入 API Key</h3>
        <p id="protectedActionAuthDescription">description</p>
        <label for="protectedActionTokenInput">API Key</label>
        <input id="protectedActionTokenInput" />
        <button id="protectedActionAuthCancel" type="button">取消</button>
        <button id="protectedActionAuthSubmit" type="submit">确认</button>
        <p id="protectedActionAuthDialogStatus"></p>
      </form>
    </dialog>
    <button id="protectedActionAuthChange">change</button>
    <button id="protectedActionAuthClear">clear</button>
    <span id="recalibrateArea"><button id="recalibrateBtn">recalibrate</button></span>
    <span id="resummarizeArea"><button id="resummarizeBtn">resummarize</button></span>
    <span id="generateNotesArea"><button id="generateNotesBtn">generate notes</button></span>
  </body>`, { runScripts: 'outside-only', url: 'https://example.test/view/view-token-1' });
  const authStorage = {
    readAuthToken: vi.fn(() => token),
    writeAuthToken: vi.fn(() => true),
    clearAuthToken: vi.fn(),
    snapshotAuthToken: vi.fn(() => token),
    buildAuthHeaders: vi.fn(() => (token ? { Authorization: `Bearer ${token}` } : {})),
    clearAuthTokenIfMatch: vi.fn(() => true),
  };
  const controller = {
    runProtectedAction: vi.fn(() => Promise.resolve()),
  };
  let capturedDependencies;
  if (withAuth) dom.window.VideoTranscriptAuthStorage = authStorage;
  if (withController) {
    dom.window.VideoTranscriptProtectedAction = {
      createProtectedActionController: vi.fn((dependencies) => {
        capturedDependencies = dependencies;
        return controller;
      }),
    };
  }
  dom.window.setTimeout = (callback) => {
    callback();
    return 1;
  };
  dom.window.eval(adapterSource());
  return { dom, authStorage, controller, getDependencies: () => capturedDependencies };
}

describe('transcript protected action page adapter', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('maps all three actions and sends the Jinja view token to the controller', async () => {
    const fixture = createFixture();
    fixture.dom.window.document.querySelector('#recalibrateBtn').click();
    fixture.dom.window.document.querySelector('#resummarizeBtn').click();
    fixture.dom.window.document.querySelector('#generateNotesBtn').click();
    await Promise.resolve();

    expect(fixture.controller.runProtectedAction.mock.calls.map(([action, token]) => [action, token])).toEqual([
      ['recalibrate', 'view-token-1'],
      ['resummarize', 'view-token-1'],
      ['generate_notes', 'view-token-1'],
    ]);
  });

  it('does not open the prompt for a cached-token action', async () => {
    const fixture = createFixture({ token: 'cached-token' });
    fixture.dom.window.document.querySelector('#recalibrateBtn').click();
    await Promise.resolve();

    expect(fixture.dom.window.document.querySelector('#protectedActionAuthDialog').hasAttribute('open')).toBe(false);
    expect(fixture.getDependencies().promptToken).toBeTypeOf('function');
  });

  it('shares one prompt, focuses input, submits with Enter, and restores trigger focus', async () => {
    const fixture = createFixture({ token: null });
    fixture.controller.runProtectedAction.mockImplementation(() => {
      const dependencies = fixture.getDependencies();
      return dependencies.promptToken().then((newToken) => {
        dependencies.authStorage.writeAuthToken(newToken);
      });
    });
    const firstButton = fixture.dom.window.document.querySelector('#recalibrateBtn');
    const secondButton = fixture.dom.window.document.querySelector('#resummarizeBtn');
    firstButton.focus();
    firstButton.click();
    secondButton.click();
    await Promise.resolve();
    const dialog = fixture.dom.window.document.querySelector('#protectedActionAuthDialog');
    const input = fixture.dom.window.document.querySelector('#protectedActionTokenInput');
    expect(dialog.hasAttribute('open')).toBe(true);
    expect(fixture.dom.window.document.activeElement).toBe(input);

    input.value = 'entered-token';
    fixture.dom.window.document.querySelector('#protectedActionAuthForm').dispatchEvent(
      new fixture.dom.window.Event('submit', { bubbles: true, cancelable: true })
    );
    await Promise.resolve();
    expect(fixture.authStorage.writeAuthToken).toHaveBeenCalledWith('entered-token');
    expect(dialog.hasAttribute('open')).toBe(false);
    expect(fixture.dom.window.document.activeElement).toBe(firstButton);
  });

  it('Escape rejects the prompt and clear/change never starts an action', async () => {
    const fixture = createFixture({ token: null });
    const change = fixture.dom.window.document.querySelector('#protectedActionAuthChange');
    const clear = fixture.dom.window.document.querySelector('#protectedActionAuthClear');
    change.click();
    const dialog = fixture.dom.window.document.querySelector('#protectedActionAuthDialog');
    dialog.dispatchEvent(new fixture.dom.window.Event('cancel', { bubbles: true, cancelable: true }));
    clear.click();
    await Promise.resolve();

    expect(fixture.authStorage.clearAuthToken).toHaveBeenCalledTimes(1);
    expect(fixture.controller.runProtectedAction).not.toHaveBeenCalled();
    expect(dialog.hasAttribute('open')).toBe(false);
  });

  it('Escape silently restores the action trigger and its focus', async () => {
    const fixture = createFixture({ token: null });
    fixture.controller.runProtectedAction.mockImplementation(() => (
      fixture.getDependencies().promptToken()
    ));
    const button = fixture.dom.window.document.querySelector('#recalibrateBtn');
    const area = fixture.dom.window.document.querySelector('#recalibrateArea');
    button.focus();
    button.click();

    const dialog = fixture.dom.window.document.querySelector('#protectedActionAuthDialog');
    dialog.dispatchEvent(new fixture.dom.window.Event('cancel', { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();

    expect(dialog.hasAttribute('open')).toBe(false);
    expect(button.disabled).toBe(false);
    expect(fixture.dom.window.document.activeElement).toBe(button);
    expect(area.querySelector('.recalibrate-error')).toBeNull();
    expect(area.textContent).toBe('recalibrate');
  });

  it('fails closed when either shared browser script is unavailable', () => {
    const fixture = createFixture({ withAuth: false });

    expect(fixture.dom.window.document.querySelector('#recalibrateBtn').disabled).toBe(true);
    expect(fixture.dom.window.document.querySelector('#resummarizeBtn').disabled).toBe(true);
    expect(fixture.dom.window.document.querySelector('#generateNotesBtn').disabled).toBe(true);
    expect(fixture.dom.window.document.querySelector('#protectedActionAuthStatus').textContent)
      .toContain('安全错误：统一鉴权模块加载失败，已禁用受保护操作');
  });

  it('uses text nodes for network errors and restores the action button', async () => {
    const fixture = createFixture();
    fixture.controller.runProtectedAction.mockRejectedValue(new Error('POST network failure'));
    const area = fixture.dom.window.document.querySelector('#recalibrateArea');
    fixture.dom.window.document.querySelector('#recalibrateBtn').click();
    await Promise.resolve();
    await Promise.resolve();

    expect(area.querySelector('span').textContent).toBe('提交结果不确定，请勿自动重试');
    expect(area.querySelector('span').children).toHaveLength(0);
    expect(area.querySelector('button').disabled).toBe(false);
  });
});
