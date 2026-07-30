import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const scriptSource = fs.readFileSync(
  path.resolve(__dirname, '../static/js/floating-toc.js'),
  'utf8',
);

class TestIntersectionObserver {
  static instances = [];

  constructor(callback, options) {
    this.callback = callback;
    this.options = options;
    this.observed = [];
    TestIntersectionObserver.instances.push(this);
  }

  observe(element) {
    this.observed.push(element);
  }

  disconnect() {}

  trigger(entries) {
    this.callback(entries, this);
  }
}

function createFixture({
  chapters = [],
  notes = [],
  calibrated = [],
  dialogs = [],
  includeSummary = true,
} = {}) {
  const summaryMarkup = includeSummary ? `
    <div class="section" id="summary-section">
      <div class="section-header"><h2>内容总结</h2></div>
      <div class="content"><h3>关键观点</h3><p>summary</p></div>
    </div>` : '';
  const notesMarkup = notes.length > 0 ? `
    <details class="section notes-section" id="notes-section" open>
      <summary class="section-header"><h2>详细笔记</h2></summary>
      <div class="content" id="notes-content-block">
        ${notes.map(({ index, title }) => `<h2 id="notes-chapter-${index}">${title}</h2>`).join('')}
      </div>
    </details>` : '';
  const calibratedMarkup = calibrated.length > 0 ? `
    <div class="section" id="calibrated-section">
      <div class="section-header"><h2>校对文本</h2></div>
      <div class="content" id="calibrated-content-block">
        ${calibrated.map(index => `<div class="chapter-anchor" id="chapter-anchor-${index}"></div>`).join('')}
        ${dialogs.map(index => `<div class="dialog-item" id="dlg-${index}"></div>`).join('')}
      </div>
    </div>` : (dialogs.length > 0 ? `
    <div id="dialog-only">${dialogs.map(index => `<div class="dialog-item" id="dlg-${index}"></div>`).join('')}</div>` : '');
  const chaptersMarkup = chapters.length > 0
    ? `<script type="application/json" id="chapters-data">${JSON.stringify(chapters)}</script>`
    : '';
  const dom = new JSDOM(`<!doctype html><body>
    ${summaryMarkup}
    ${notesMarkup}
    ${calibratedMarkup}
    ${chaptersMarkup}
  </body>`, { runScripts: 'outside-only', url: 'https://example.test/view/token' });

  TestIntersectionObserver.instances = [];
  dom.window.matchMedia = vi.fn(() => ({
    matches: false,
    addEventListener: vi.fn(),
    addListener: vi.fn(),
  }));
  dom.window.IntersectionObserver = TestIntersectionObserver;
  dom.window.HTMLElement.prototype.scrollIntoView = vi.fn();
  dom.window.console.log = vi.fn();
  dom.window.console.warn = vi.fn();
  dom.window.eval(scriptSource);
  dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));

  return { dom, observers: TestIntersectionObserver.instances };
}

function pcChapter(dom, index = 0) {
  return dom.window.document.querySelector(
    `#floating-toc .toc-chapter-item[data-chapter-index="${index}"]`,
  );
}

function chapterObserver(observers) {
  return observers.find(observer => observer.options.threshold === 0
    && observer.observed.some(
    element => element.id.startsWith('notes-chapter-')
      || element.id.startsWith('chapter-anchor-'),
    ));
}

function passedEntry(target, { isIntersecting = true, top = 0 } = {}) {
  return {
    target,
    isIntersecting,
    boundingClientRect: { top },
  };
}

describe('floating chapter-axis TOC', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('prefers the matching notes chapter target for a chapter row', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', gist: 'gist', start_time: 65, start_seg: 0, jump_ok: true }],
      notes: [{ index: 0, title: '笔记第一章' }],
      calibrated: [0],
      dialogs: [0],
    });

    expect(pcChapter(dom).querySelector('.toc-chapter-main').dataset.targetId)
      .toBe('notes-chapter-0');
  });

  it('uses the calibrated chapter anchor when notes are absent', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', start_time: 65, start_seg: 0, jump_ok: true }],
      calibrated: [0],
      dialogs: [0],
    });

    expect(pcChapter(dom).querySelector('.toc-chapter-main').dataset.targetId)
      .toBe('chapter-anchor-0');
  });

  it('keeps a jump-disabled chapter visible and non-clickable', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '失配章节', start_time: 65, start_seg: 0, jump_ok: false }],
    });
    const item = pcChapter(dom);
    const main = item.querySelector('.toc-chapter-main');

    expect(item).not.toBeNull();
    expect(item.classList.contains('toc-chapter-disabled')).toBe(true);
    expect(main.disabled).toBe(true);
  });

  it('renders the full chapter gist as text', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', gist: '完整 gist 文本', start_time: 65, jump_ok: false }],
    });

    expect(pcChapter(dom).querySelector('.toc-chapter-gist').textContent)
      .toBe('完整 gist 文本');
  });

  it('uses document-order anchor positions for scrollspy across notes and calibrated text', () => {
    const { dom, observers } = createFixture({
      chapters: [
        { index: 0, title: '第一章', start_time: 1, start_seg: 0, jump_ok: true },
        { index: 1, title: '第二章', start_time: 2, start_seg: 1, jump_ok: true },
      ],
      notes: [
        { index: 0, title: '笔记第一章' },
        { index: 1, title: '笔记第二章' },
      ],
      calibrated: [0],
      dialogs: [0, 1],
    });
    const observer = chapterObserver(observers);
    const note0 = dom.window.document.getElementById('notes-chapter-0');
    const note1 = dom.window.document.getElementById('notes-chapter-1');
    const calibrated0 = dom.window.document.getElementById('chapter-anchor-0');

    observer.trigger([passedEntry(note0), passedEntry(note1)]);
    expect(pcChapter(dom, 1).classList.contains('current')).toBe(true);
    expect(pcChapter(dom, 0).classList.contains('current')).toBe(false);

    observer.trigger([passedEntry(calibrated0)]);
    expect(pcChapter(dom, 0).classList.contains('current')).toBe(true);
    expect(pcChapter(dom, 1).classList.contains('current')).toBe(false);
  });

  it('keeps summary and calibrated full-text nodes when chapter data is absent', () => {
    const { dom } = createFixture({ calibrated: [0] });
    const labels = [...dom.window.document.querySelectorAll('#floating-toc .toc-link')]
      .map(link => link.textContent);

    expect(labels.some(label => label.includes('内容总结'))).toBe(true);
    expect(labels.some(label => label.includes('校对文本（全文）'))).toBe(true);
  });

  it('adds original-text links only when the matching calibrated anchor exists', () => {
    const { dom } = createFixture({
      notes: [
        { index: 0, title: '笔记第一章' },
        { index: 1, title: '笔记第二章' },
      ],
      calibrated: [0],
    });
    const note0 = dom.window.document.getElementById('notes-chapter-0');
    const note1 = dom.window.document.getElementById('notes-chapter-1');
    const sourceLink = note0.querySelector('a.notes-source-link');

    expect(sourceLink).not.toBeNull();
    expect(sourceLink.textContent).toBe('原文 ↗');
    expect(sourceLink.getAttribute('href')).toBe('#chapter-anchor-0');
    expect(note1.querySelector('a.notes-source-link')).toBeNull();
  });
});
