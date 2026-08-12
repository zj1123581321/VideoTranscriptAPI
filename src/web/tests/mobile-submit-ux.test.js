// Contracts for the mobile first-screen submission flow.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const indexHtml = readFileSync(
  fileURLToPath(new URL('../static/index.html', import.meta.url)),
  'utf-8'
);
const appJs = readFileSync(
  fileURLToPath(new URL('../static/js/app.js', import.meta.url)),
  'utf-8'
);

describe('mobile first-screen submission', () => {
  it('keeps the first-screen form order and moves low-frequency settings below CTA', () => {
    const ids = [
      'share-content',
      'url-preview',
      'transcription-options-toggle',
      'auth-missing-prompt',
      'submit-btn',
      'advanced-settings',
    ].map((id) => indexHtml.indexOf(`id="${id}"`));

    expect(ids.every((position) => position >= 0)).toBe(true);
    expect(ids).toEqual([...ids].sort((a, b) => a - b));
  });

  it('hides empty URL preview and reports invalid input beside the textarea', () => {
    expect(indexHtml).toContain('id="url-preview" class="url-preview"');
    expect(indexHtml).toContain('aria-live="polite" hidden');
    expect(indexHtml).toContain('id="input-feedback"');
    expect(appJs).toContain('previewContainer.hidden = urlResults.length === 0');
    expect(appJs).toContain('inputFeedback.textContent');
  });

  it('keeps token guidance explicit and only uses blocker copy when token is absent', () => {
    expect(indexHtml).toContain('尚未配置访问令牌');
    expect(indexHtml).toContain('去设置');
    expect(appJs).toContain('authPrompt.hidden = Boolean(token)');
    expect(appJs).toContain('toggle.setAttribute(\'aria-expanded\'');
  });
});
