import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const baseTemplateSource = fs.readFileSync(
  path.resolve(__dirname, '../templates/base.html'),
  'utf8',
);
const copyScriptMarker = '<!-- 通用剪贴板复制脚本（供 URL 复制、正文复制共用） -->';
const copyScriptMarkerIndex = baseTemplateSource.indexOf(copyScriptMarker);
const copyScriptStart = baseTemplateSource.indexOf('<script>', copyScriptMarkerIndex) + '<script>'.length;
const copyScriptEnd = baseTemplateSource.indexOf('</script>', copyScriptStart);
const copyScriptSource = baseTemplateSource.slice(copyScriptStart, copyScriptEnd);

function installInnerTextFixture(dom, targetEl) {
  Object.defineProperty(targetEl, 'innerText', {
    configurable: true,
    get() {
      const walker = dom.window.document.createTreeWalker(
        targetEl,
        dom.window.NodeFilter.SHOW_TEXT,
      );
      const textNodes = [];
      let node = walker.nextNode();
      while (node) {
        const hiddenSourceLink = node.parentElement?.closest('.notes-source-link');
        if (hiddenSourceLink?.style.display !== 'none') {
          textNodes.push(node.nodeValue);
        }
        node = walker.nextNode();
      }
      return textNodes.join('');
    },
  });
}

function createCopyFixture(markup, copyHelper) {
  const dom = new JSDOM(`<!doctype html><body>${markup}</body>`, {
    runScripts: 'outside-only',
    url: 'https://example.test/view/token',
  });
  dom.window.setTimeout = vi.fn();
  dom.window.eval(copyScriptSource);
  dom.window.copyTextToClipboard = copyHelper;
  dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));
  return dom;
}

describe('base template copy-content handler', () => {
  it('omits notes source links while preserving chapter headings and body text', () => {
    let sourceLink;
    const copyHelper = vi.fn((text, onDone) => {
      expect(sourceLink.style.display).toBe('');
      onDone();
    });
    const dom = createCopyFixture(`
      <button class="copy-content-btn" data-copy-target="notes-content-block">复制内容</button>
      <div id="notes-content-block">
        <h2>第一章：问题背景</h2>
        <p>这是章节正文。</p>
        <a class="notes-source-link" href="#chapter-anchor-0">原文 ↗</a>
      </div>
    `, copyHelper);
    const targetEl = dom.window.document.getElementById('notes-content-block');
    sourceLink = targetEl.querySelector('.notes-source-link');
    installInnerTextFixture(dom, targetEl);

    dom.window.document.querySelector('.copy-content-btn').click();

    const copiedText = copyHelper.mock.calls[0][0];
    expect(copiedText).toContain('第一章：问题背景');
    expect(copiedText).toContain('这是章节正文。');
    expect(copiedText).not.toContain('原文 ↗');
    expect(sourceLink.style.display).toBe('');
  });

  it('keeps calibrated content copy behavior unchanged without notes source links', () => {
    const copyHelper = vi.fn((text, onDone) => onDone());
    const dom = createCopyFixture(`
      <button class="copy-content-btn" data-copy-target="calibrated-content-block">复制内容</button>
      <div id="calibrated-content-block">
        <h2>校对章节</h2>
        <p>校对正文。</p>
      </div>
    `, copyHelper);
    const targetEl = dom.window.document.getElementById('calibrated-content-block');
    installInnerTextFixture(dom, targetEl);
    const expectedText = targetEl.innerText;

    dom.window.document.querySelector('.copy-content-btn').click();

    expect(copyHelper).toHaveBeenCalledWith(expectedText, expect.any(Function));
  });
});
