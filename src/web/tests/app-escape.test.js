// Tests for the HTML-escape helper used when rendering URL previews (Codex R6-1).
//
// XSS chain: E4 share prefill writes a shared URL into the textarea and
// dispatches input -> app.js handleTextInput interpolates result.url /
// result.display into innerHTML unescaped (attribute AND element context),
// so any app could inject same-origin XSS via the system share sheet and
// steal the localStorage Bearer token. The fix escapes at the
// interpolation points (cleanURL return semantics unchanged).

import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { escapeHTML, buildHistoryItemHTML } = require('../static/js/app.js');

const appJsSource = readFileSync(
  fileURLToPath(new URL('../static/js/app.js', import.meta.url)),
  'utf-8'
);

describe('escapeHTML', () => {
  it('escapes attribute- and element-context metacharacters', () => {
    expect(escapeHTML('https://x.io/</span><img/src=x/onerror=alert(1)>/x'))
      .not.toContain('<');
    expect(escapeHTML('a&b')).toBe('a&amp;b');
    expect(escapeHTML('<b>')).toBe('&lt;b&gt;');
    expect(escapeHTML('"quoted"')).toBe('&quot;quoted&quot;');
    expect(escapeHTML("it's")).toBe('it&#39;s');
  });

  it('leaves normal URLs untouched', () => {
    const url = 'https://b23.tv/abc123?x=1&y=2';
    expect(escapeHTML(url)).toBe('https://b23.tv/abc123?x=1&amp;y=2');
  });

  it('coerces non-strings', () => {
    expect(escapeHTML(null)).toBe('null');
    expect(escapeHTML(42)).toBe('42');
  });
});

describe('preview interpolation points (source-level)', () => {
  it('every URL interpolation in the preview HTML goes through escapeHTML', () => {
    expect(appJsSource).toContain('data-url="${escapeHTML(result.url)}"');
    expect(appJsSource).toContain('value="${escapeHTML(result.url)}"');
    expect(appJsSource).toContain('class="url-display">${escapeHTML(result.display)}</span>');
    // the unescaped forms must be gone
    expect(appJsSource).not.toContain('data-url="${result.url}"');
    expect(appJsSource).not.toContain('value="${result.url}"');
    expect(appJsSource).not.toContain('class="url-display">${result.display}</span>');
  });

  it('copyToClipboard escapes the echoed details (Codex R9-1)', () => {
    // the copied URL is dataset-decoded raw text; echoing it unescaped into
    // showStatus' innerHTML would re-open the XSS chain on copy click
    expect(appJsSource).toContain("showStatus('success', '已复制到剪贴板', escapeHTML(text))");
    expect(appJsSource).not.toContain("showStatus('success', '已复制到剪贴板', text)");
  });
});

describe('buildHistoryItemHTML (Codex R8-1)', () => {
  const malicious = {
    id: "1'><img src=x onerror=alert(1)>",
    view_token: "vt'\"<>",
    url: "https://x.io/</span><img/src=x/onerror=alert(1)>/x",
    title: '<script>alert(1)</script>',
    original_text: "分享文案'><svg/onload=alert(1)> https://b23.tv/abc",
    timestamp: 1753800000000,
    useSpeakerRecognition: false,
  };

  it('escapes every attacker-controlled field', () => {
    const html = buildHistoryItemHTML(malicious);
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<svg');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('&#39;');
  });

  it('uses data-* + addEventListener binding, never inline onclick', () => {
    const html = buildHistoryItemHTML(malicious);
    expect(html).not.toContain('onclick=');
    expect(html).toContain('class="history-btn history-copy-btn" data-url="');
    expect(html).toContain('class="history-btn delete-btn history-delete-btn" data-task-id="');
  });

  it('renders normal tasks intact', () => {
    const html = buildHistoryItemHTML({
      id: '42',
      view_token: 'tok',
      url: 'https://b23.tv/abc',
      title: '普通标题',
      original_text: '',
      timestamp: 1753800000000,
      useSpeakerRecognition: true,
    });
    expect(html).toContain('普通标题');
    expect(html).toContain('https://b23.tv/abc');
    expect(html).toContain('href="/view/tok"');
    expect(html).toContain('说话人识别');
  });

  it('truncates long original_text to 100 chars', () => {
    const html = buildHistoryItemHTML({
      id: '1',
      view_token: 't',
      url: 'https://a.com/v',
      title: 't',
      original_text: 'x'.repeat(150),
      timestamp: 1753800000000,
      useSpeakerRecognition: false,
    });
    expect(html).toContain('x'.repeat(100) + '...');
  });
});
