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
const { escapeHTML } = require('../static/js/app.js');

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
});
