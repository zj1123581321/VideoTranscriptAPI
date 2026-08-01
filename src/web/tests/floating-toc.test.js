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
  calibratedTop = 0,
  notesOpen = true,
  mobile = false,
} = {}) {
  const summaryMarkup = includeSummary ? `
    <div class="section" id="summary-section">
      <div class="section-header"><h2>内容总结</h2></div>
      <div class="content"><h2 id="summary-heading">关键观点</h2><h3 id="summary-subheading">子观点</h3><p>summary</p></div>
    </div>` : '';
  const notesMarkup = notes.length > 0 ? `
    <details class="section notes-section" id="notes-section" ${notesOpen ? 'open' : ''}>
      <summary class="section-header"><h2>详细笔记</h2></summary>
      <div class="content" id="notes-content-block">
        ${notes.map(({ index, title }) => `<h2 id="notes-chapter-${index}">${title}</h2>`).join('')}
      </div>
    </details>` : '';
  const calibratedMarkup = calibrated.length > 0 || dialogs.length > 0 ? `
    <div class="section" id="calibrated-section">
      <div class="section-header"><h2>校对文本</h2></div>
      <div class="content" id="calibrated-content-block">
        ${calibrated.map(index => `<div class="chapter-anchor" id="chapter-anchor-${index}"><span class="chapter-anchor-title">校对章节 ${index}</span></div>`).join('')}
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
  dom.window.matchMedia = vi.fn(query => ({
    matches: mobile && query === '(max-width: 768px)',
    addEventListener: vi.fn(),
    addListener: vi.fn(),
  }));
  Object.defineProperty(dom.window, 'innerHeight', {
    configurable: true,
    value: 800,
  });
  const calibratedSection = dom.window.document.getElementById('calibrated-section');
  if (calibratedSection) {
    calibratedSection.getBoundingClientRect = vi.fn(() => ({
      top: calibratedTop,
    }));
  }
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

function scrollObserver(observers) {
  return observers.find(observer => observer.options.threshold === 0.5);
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

  it('prefers the calibrated anchor in the calibrated viewport zone', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', gist: 'gist', start_time: 65, start_seg: 0, jump_ok: true }],
      notes: [{ index: 0, title: '笔记第一章' }],
      calibrated: [0],
      dialogs: [0],
    });

    const main = pcChapter(dom).querySelector('.toc-chapter-main');
    expect(main.dataset.calTargetId).toBe('chapter-anchor-0');
    expect(main.dataset.calFallbackId).toBe('dlg-0');
    expect(main.dataset.notesTargetId).toBe('notes-chapter-0');

    const note = dom.window.document.getElementById('notes-chapter-0');
    const anchor = dom.window.document.getElementById('chapter-anchor-0');
    note.scrollIntoView = vi.fn();
    anchor.scrollIntoView = vi.fn();
    main.click();

    expect(anchor.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });
    expect(note.scrollIntoView).not.toHaveBeenCalled();
  });

  it('prefers notes outside the calibrated viewport zone', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', start_time: 65, start_seg: 0, jump_ok: true }],
      notes: [{ index: 0, title: '笔记第一章' }],
      calibrated: [0],
      dialogs: [0],
      calibratedTop: 500,
    });

    const note = dom.window.document.getElementById('notes-chapter-0');
    const main = pcChapter(dom).querySelector('.toc-chapter-main');
    note.scrollIntoView = vi.fn();
    dom.window.document.getElementById('chapter-anchor-0').scrollIntoView = vi.fn();
    main.click();

    expect(note.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });
  });

  it('uses the calibrated anchor when notes are absent', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', start_time: 65, start_seg: 0, jump_ok: true }],
      calibrated: [0],
      dialogs: [0],
    });

    expect(pcChapter(dom).querySelector('.toc-chapter-main').dataset.calTargetId)
      .toBe('chapter-anchor-0');
  });

  it('falls back to notes inside the calibrated zone when calibrated targets are absent', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', start_time: 65, start_seg: 0, jump_ok: true }],
      notes: [{ index: 0, title: '笔记第一章' }],
      calibrated: [1],
    });
    const note = dom.window.document.getElementById('notes-chapter-0');
    const main = pcChapter(dom).querySelector('.toc-chapter-main');

    expect(dom.window.document.getElementById('calibrated-section')).not.toBeNull();
    expect(dom.window.document.getElementById('chapter-anchor-0')).toBeNull();
    expect(dom.window.document.getElementById('dlg-0')).toBeNull();
    note.scrollIntoView = vi.fn();
    main.click();

    expect(note.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });
  });

  it('falls back from a missing calibrated anchor to its dialog target', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', start_time: 65, start_seg: 0, jump_ok: true }],
      dialogs: [0],
    });
    const main = pcChapter(dom).querySelector('.toc-chapter-main');
    const dialog = dom.window.document.getElementById('dlg-0');
    dialog.scrollIntoView = vi.fn();
    main.click();

    expect(dialog.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });
  });

  it('keeps a jump-disabled chapter visible and non-clickable', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '失配章节', start_time: 65, start_seg: 0, jump_ok: false }],
      calibrated: [0],
      dialogs: [0],
    });
    const item = pcChapter(dom);
    const main = item.querySelector('.toc-chapter-main');

    expect(item).not.toBeNull();
    expect(item.classList.contains('toc-chapter-disabled')).toBe(true);
    expect(main.disabled).toBe(true);
    expect(main.dataset.calTargetId || '').not.toContain('dlg-0');
    expect(main.dataset.calFallbackId || '').not.toContain('dlg-0');
  });

  it('disables a chapter when both notes and calibrated targets are absent', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '失配章节', start_time: 65, start_seg: 0, jump_ok: true }],
    });
    const item = pcChapter(dom);
    const main = item.querySelector('.toc-chapter-main');

    expect(item.classList.contains('toc-chapter-disabled')).toBe(true);
    expect(main.disabled).toBe(true);
    expect(main.dataset.notesTargetId).toBeUndefined();
    expect(main.dataset.calTargetId).toBeUndefined();
    expect(main.dataset.calFallbackId).toBeUndefined();
  });

  it('renders the full chapter gist as text', () => {
    const { dom } = createFixture({
      chapters: [{ index: 0, title: '第一章', gist: '完整 gist 文本', start_time: 65, jump_ok: false }],
    });

    expect(pcChapter(dom).querySelector('.toc-chapter-gist').textContent)
      .toBe('完整 gist 文本');
  });

  it('renders one chapter axis node and one copy of each full-text leaf', () => {
    const { dom, observers } = createFixture({
      chapters: [
        { index: 0, title: '第一章', start_time: 1, start_seg: 0, jump_ok: true },
        { index: 1, title: '第二章', start_time: 2, start_seg: 1, jump_ok: true },
      ],
      notes: [
        { index: 0, title: '笔记第一章' },
        { index: 1, title: '笔记第二章' },
      ],
      calibrated: [0, 1],
      dialogs: [0, 1],
    });
    const toc = dom.window.document.querySelector('#floating-toc');
    const chaptersNode = toc.querySelector('.toc-chapters-node');
    const scroll = scrollObserver(observers);
    const observedIds = scroll.observed.map(element => element.id);

    expect(toc.querySelectorAll('.toc-chapters-node')).toHaveLength(1);
    expect(chaptersNode.querySelector('.toc-outline-parent').textContent)
      .toBe('章节 (2)');
    expect(chaptersNode.querySelectorAll('.toc-chapter-item')).toHaveLength(2);
    expect(chaptersNode.querySelectorAll('.toc-outline-toggle')).toHaveLength(1);
    expect(chaptersNode.querySelectorAll('.toc-chapter-leaf')).toHaveLength(0);
    expect(chaptersNode.querySelectorAll('.toc-full-text-leaf')).toHaveLength(0);
    expect(chaptersNode.querySelector('.toc-chapter-item').textContent)
      .not.toContain('章节 1');
    expect(toc.querySelectorAll('.toc-full-text-leaf.toc-notes-leaf'))
      .toHaveLength(1);
    expect(toc.querySelectorAll('.toc-full-text-leaf.toc-calibrated-leaf'))
      .toHaveLength(1);

    expect(new Set(observedIds).size).toBe(observedIds.length);
    expect(observedIds).toContain('summary-heading');
    expect(observedIds).toContain('notes-section');
    expect(observedIds).toContain('calibrated-section');

    scroll.trigger([passedEntry(dom.window.document.getElementById('summary-heading'))]);
    expect(toc.querySelector('.toc-outline-child[data-id="summary-heading"]')
      .classList.contains('active')).toBe(false);
    expect(toc.querySelector('.toc-outline-parent').classList.contains('active'))
      .toBe(true);

    scroll.trigger([passedEntry(dom.window.document.getElementById('notes-section'))]);
    expect(toc.querySelector('.toc-notes-leaf').classList.contains('active'))
      .toBe(true);
    scroll.trigger([passedEntry(dom.window.document.getElementById('calibrated-section'))]);
    expect(toc.querySelector('.toc-calibrated-leaf').classList.contains('active'))
      .toBe(true);
  });

  it('falls back to the visible summary parent in both TOC copies when collapsed', () => {
    const { dom, observers } = createFixture();
    const scroll = scrollObserver(observers);
    const heading = dom.window.document.getElementById('summary-heading');
    const tocCopies = [
      dom.window.document.querySelector('#floating-toc'),
      dom.window.document.querySelector('#toc-mobile-panel'),
    ];

    scroll.trigger([passedEntry(heading)]);

    tocCopies.forEach(tocCopy => {
      const summary = tocCopy.querySelector('.toc-summary-node');
      expect(summary.classList.contains('toc-outline-collapsed')).toBe(true);
      expect(summary.querySelector('.toc-outline-child[data-id="summary-heading"]')
        .classList.contains('active')).toBe(false);
      expect(summary.querySelector('.toc-outline-parent').classList.contains('active'))
        .toBe(true);
    });
  });

  it('activates the summary child in both TOC copies after expanding the section', () => {
    const { dom, observers } = createFixture();
    const scroll = scrollObserver(observers);
    const heading = dom.window.document.getElementById('summary-heading');
    const tocCopies = [
      dom.window.document.querySelector('#floating-toc'),
      dom.window.document.querySelector('#toc-mobile-panel'),
    ];

    tocCopies.forEach(tocCopy => {
      tocCopy.querySelector('.toc-outline-toggle').click();
    });

    tocCopies.forEach(tocCopy => {
      expect(tocCopy.querySelector('.toc-summary-node')
        .classList.contains('toc-outline-collapsed')).toBe(false);
    });

    scroll.trigger([passedEntry(heading)]);

    tocCopies.forEach(tocCopy => {
      const summary = tocCopy.querySelector('.toc-summary-node');
      expect(summary.querySelector('.toc-outline-child[data-id="summary-heading"]')
        .classList.contains('active')).toBe(true);
      expect(summary.querySelector('.toc-outline-parent').classList.contains('active'))
        .toBe(false);
    });
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

    scrollObserver(observers).trigger([passedEntry(note1)]);
    expect(pcChapter(dom, 1).querySelector('.toc-chapter-main')
      .classList.contains('active')).toBe(true);
    expect(pcChapter(dom, 0).querySelector('.toc-chapter-main')
      .classList.contains('active')).toBe(false);

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

  it('adds calibrated-to-notes links only when matching notes exist and is idempotent', () => {
    const { dom } = createFixture({
      notes: [{ index: 0, title: '笔记第一章' }],
      calibrated: [0, 1],
    });
    const calibrated0 = dom.window.document.getElementById('chapter-anchor-0');
    const calibrated1 = dom.window.document.getElementById('chapter-anchor-1');

    expect(calibrated0.querySelector('a.calibrated-notes-link').textContent)
      .toBe('笔记 ↗');
    expect(calibrated0.querySelector('a.calibrated-notes-link').getAttribute('href'))
      .toBe('#notes-chapter-0');
    expect(calibrated1.querySelector('a.calibrated-notes-link')).toBeNull();

    dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));

    expect(calibrated0.querySelectorAll('a.calibrated-notes-link'))
      .toHaveLength(1);
  });

  it('uses smooth scroll and opens details for both cross-section links', () => {
    const { dom } = createFixture({
      notes: [{ index: 0, title: '笔记第一章' }],
      calibrated: [0],
      notesOpen: false,
    });
    const note = dom.window.document.getElementById('notes-chapter-0');
    const anchor = dom.window.document.getElementById('chapter-anchor-0');
    const sourceLink = note.querySelector('a.notes-source-link');
    const notesLink = anchor.querySelector('a.calibrated-notes-link');
    const noteSection = dom.window.document.getElementById('notes-section');
    const sourceEvent = new dom.window.MouseEvent('click', {
      bubbles: true,
      cancelable: true,
    });
    const notesEvent = new dom.window.MouseEvent('click', {
      bubbles: true,
      cancelable: true,
    });
    anchor.scrollIntoView = vi.fn();
    note.scrollIntoView = vi.fn();

    sourceLink.dispatchEvent(sourceEvent);
    expect(sourceEvent.defaultPrevented).toBe(true);
    expect(anchor.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });

    noteSection.open = false;
    notesLink.dispatchEvent(notesEvent);
    expect(notesEvent.defaultPrevented).toBe(true);
    expect(noteSection.open).toBe(true);
    expect(note.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });
  });

  it('routes the mobile sticky chapter entry through the shared jump handler', () => {
    const { dom, observers } = createFixture({
      chapters: [{ index: 0, title: '第一章', start_time: 1, start_seg: 0, jump_ok: true }],
      notes: [{ index: 0, title: '笔记第一章' }],
      calibrated: [0],
      mobile: true,
    });
    const anchor = dom.window.document.getElementById('chapter-anchor-0');
    const chapterTracker = chapterObserver(observers);
    const transcriptTracker = observers.find(observer => observer.observed.includes(
      dom.window.document.getElementById('calibrated-content-block')
    ));
    anchor.scrollIntoView = vi.fn();
    chapterTracker.trigger([passedEntry(anchor)]);
    transcriptTracker.trigger([passedEntry(
      dom.window.document.getElementById('calibrated-content-block')
    )]);

    const sticky = dom.window.document.querySelector('.chapter-sticky-bar');
    expect(sticky.hidden).toBe(false);
    sticky.click();

    expect(anchor.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });
  });
});
