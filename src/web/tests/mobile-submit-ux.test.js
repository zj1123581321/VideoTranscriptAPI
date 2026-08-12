// @vitest-environment jsdom
// Behavioral contracts for the mobile first-screen submission flow.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const authStoragePath = require.resolve('../static/js/auth-storage.js');
const appPath = require.resolve('../static/js/app.js');
const indexSource = readFileSync(
  'src/web/static/index.html',
  'utf-8'
);

let dom;

function installPage(token = null) {
  dom = new JSDOM(indexSource, { url: 'https://vta.test/' });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.localStorage = dom.window.localStorage;
  globalThis.sessionStorage = dom.window.sessionStorage;
  globalThis.StorageEvent = dom.window.StorageEvent;
  dom.window.HTMLElement.prototype.scrollIntoView = vi.fn();
  delete require.cache[authStoragePath];
  const authStorage = require(authStoragePath);
  if (token) authStorage.writeAuthToken(token, { remember: true });
  delete require.cache[appPath];
  require(appPath);
  document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));
}

function inputShareText(value) {
  const textarea = document.getElementById('share-content');
  textarea.value = value;
  textarea.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
}

afterEach(() => {
  dom?.window.close();
  delete globalThis.window;
  delete globalThis.document;
  delete globalThis.localStorage;
  delete globalThis.sessionStorage;
  delete globalThis.StorageEvent;
  delete globalThis.VideoTranscriptAuthStorage;
  vi.restoreAllMocks();
});

describe('mobile first-screen submission', () => {
  it('enables CTA and hides auth prompt for a saved token and valid URL', () => {
    installPage('saved-token');
    inputShareText('https://www.youtube.com/watch?v=mobile-test');

    expect(document.getElementById('submit-btn').disabled).toBe(false);
    expect(document.getElementById('auth-missing-prompt').hidden).toBe(true);
    expect(document.getElementById('advanced-settings').hidden).toBe(true);
  });

  it('shows the missing-token prompt and keeps CTA disabled', () => {
    installPage();
    expect(document.getElementById('auth-missing-prompt').hidden).toBe(false);
    expect(document.getElementById('submit-btn').disabled).toBe(true);
  });

  it('shows polite inline feedback for invalid input without a URL preview', () => {
    installPage();
    inputShareText('这不是视频链接');

    const feedback = document.getElementById('input-feedback');
    expect(feedback.hidden).toBe(false);
    expect(feedback.getAttribute('aria-live')).toBe('polite');
    expect(feedback.textContent).toContain('未检测到可识别的视频链接');
    expect(document.getElementById('url-preview').hidden).toBe(true);
  });

  it('updates aria-expanded for transcription options and advanced settings', () => {
    installPage();
    const optionsToggle = document.getElementById('transcription-options-toggle');
    const advancedToggle = document.getElementById('advanced-toggle');

    optionsToggle.click();
    advancedToggle.click();
    expect(optionsToggle.getAttribute('aria-expanded')).toBe('true');
    expect(advancedToggle.getAttribute('aria-expanded')).toBe('true');

    optionsToggle.click();
    advancedToggle.click();
    expect(optionsToggle.getAttribute('aria-expanded')).toBe('false');
    expect(advancedToggle.getAttribute('aria-expanded')).toBe('false');
  });
});
