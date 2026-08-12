// @vitest-environment jsdom
// Behavioral contracts for the mobile first-screen submission flow.
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const indexSource = readFileSync(
  'src/web/static/index.html',
  'utf-8'
);
const authSource = readFileSync('src/web/static/js/auth-storage.js', 'utf-8');
const appSource = readFileSync('src/web/static/js/app.js', 'utf-8');
const pwaShareSource = readFileSync('src/web/static/js/pwa-share.js', 'utf-8');
const pwaSource = readFileSync('src/web/static/pwa.js', 'utf-8');

let dom;

async function installPage({ token = null, search = '' } = {}) {
  dom = new JSDOM(indexSource, {
    url: `https://vta.test/add_task_by_web${search}`,
    runScripts: 'outside-only',
  });
  const { window } = dom;
  dom.window.HTMLElement.prototype.scrollIntoView = vi.fn();
  window.matchMedia = vi.fn((media) => ({
    matches: false,
    media,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  const initializeLog = vi.spyOn(window.console, 'log');
  window.eval(authSource);
  if (token) window.VideoTranscriptAuthStorage.writeAuthToken(token, { remember: true });
  window.eval(appSource);
  window.eval(pwaShareSource);
  window.eval(pwaSource);
  await new Promise((resolve) => {
    window.addEventListener('DOMContentLoaded', resolve, { once: true });
  });
  return initializeLog;
}

function inputShareText(value) {
  const textarea = dom.window.document.getElementById('share-content');
  textarea.value = value;
  textarea.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
}

afterEach(() => {
  vi.clearAllTimers();
  dom?.window.close();
  vi.restoreAllMocks();
});

describe('mobile first-screen submission', () => {
  it('enables CTA and hides auth prompt for a saved token and valid URL', async () => {
    await installPage({ token: 'saved-token' });
    inputShareText('https://www.youtube.com/watch?v=mobile-test');

    expect(dom.window.document.getElementById('submit-btn').disabled).toBe(false);
    expect(dom.window.document.getElementById('auth-missing-prompt').hidden).toBe(true);
    expect(dom.window.document.getElementById('advanced-settings').hidden).toBe(true);
  });

  it('shows the missing-token prompt and keeps CTA disabled', async () => {
    const initializeLog = await installPage();
    const page = dom.window.document;
    expect(page.getElementById('auth-missing-prompt').hidden).toBe(false);
    expect(page.getElementById('submit-btn').disabled).toBe(true);
    expect(initializeLog.mock.calls.filter(([message]) => message === '初始化视频转录Web应用...')).toHaveLength(1);
  });

  it('shows polite inline feedback for invalid input without a URL preview', async () => {
    await installPage();
    inputShareText('这不是视频链接');

    const feedback = dom.window.document.getElementById('input-feedback');
    expect(feedback.hidden).toBe(false);
    expect(feedback.getAttribute('aria-live')).toBe('polite');
    expect(feedback.textContent).toContain('未检测到可识别的视频链接');
    expect(dom.window.document.getElementById('url-preview').hidden).toBe(true);
  });

  it('updates aria-expanded for transcription options and advanced settings', async () => {
    await installPage();
    const optionsToggle = dom.window.document.getElementById('transcription-options-toggle');
    const advancedToggle = dom.window.document.getElementById('advanced-toggle');

    optionsToggle.click();
    advancedToggle.click();
    expect(optionsToggle.getAttribute('aria-expanded')).toBe('true');
    expect(advancedToggle.getAttribute('aria-expanded')).toBe('true');

    optionsToggle.click();
    advancedToggle.click();
    expect(optionsToggle.getAttribute('aria-expanded')).toBe('false');
    expect(advancedToggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('prefills a PWA URL, then enables CTA after token input without editing the URL', async () => {
    await installPage({ search: '?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dpwa-test' });
    const page = dom.window.document;
    const textarea = page.getElementById('share-content');
    const tokenInput = page.getElementById('bearer-token');

    expect(textarea.value).toBe('https://www.youtube.com/watch?v=pwa-test');
    expect(page.getElementById('submit-btn').disabled).toBe(true);
    expect(page.getElementById('auth-missing-prompt').hidden).toBe(false);

    tokenInput.value = 'pwa-token';
    tokenInput.dispatchEvent(new dom.window.Event('input', { bubbles: true }));

    expect(textarea.value).toBe('https://www.youtube.com/watch?v=pwa-test');
    expect(page.getElementById('auth-missing-prompt').hidden).toBe(true);
    expect(page.getElementById('submit-btn').disabled).toBe(false);
  });
});
