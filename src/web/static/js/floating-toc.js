/**
 * Floating TOC (Table of Contents)
 * Responsive design for desktop and mobile.
 *
 * Features:
 * - Builds one directory tree containing summary headings, a chapter axis,
 *   detailed notes, and calibrated transcript full-text leaves
 * - Chapters are read from the #chapters-data JSON island
 *   (items: {index,title,gist,start_time,start_seg,jump_ok}); a chapter row
 *   shows time + title + full gist and targets notes-chapter-{index}, then
 *   chapter-anchor-{index}, then dlg-{start_seg}. The latter two targets are
 *   gated by jump_ok; rows remain visible but muted and disabled when they
 *   cannot jump.
 * - Chapter pages track the current chapter through notes and calibrated
 *   anchors, while summary headings and full-text sections use scrollspy
 * - Breakpoints on chapter pages:
 *     >=1400px: docked expanded panel, body gets a right margin (toc-wide-margin)
 *     769-1399px: overlay panel, expanded by default, manually collapsible
 *       (state in localStorage key vta_toc_panel_collapsed)
 *     <=768px: sticky current-chapter bar + FAB + bottom drawer
 * - Pages without chapters use a collapsed indicator bar with optional pinning
 *   (localStorage key vta_toc_pinned)
 * - Scroll highlight + smooth jump
 * - XSS: build all user/chapter text via DOM API + textContent only
 *   (never HTML-string concatenation of titles)
 */

(function() {
    'use strict';

    // ========== Config ==========
    const CONFIG = {
        STORAGE_KEY: 'vta_toc_pinned',
        COLLAPSE_STORAGE_KEY: 'vta_toc_panel_collapsed',
        OBSERVER_OPTIONS: {
            threshold: 0.5,
            rootMargin: '-100px 0px -60% 0px'
        },
        MOBILE_QUERY: '(max-width: 768px)',
        WIDE_QUERY: '(min-width: 1400px)'
    };

    // ========== State ==========
    let tocData = {
        headings: [],
        summarySection: null,
        notesSection: null,
        calibratedSection: null,
        chapters: []
    };

    let hasChapters = false;
    let observer = null;
    let chapterObserver = null;
    let transcriptObserver = null;
    let isPinned = false;
    let mode = 'mid'; // 'mobile' | 'mid' | 'wide'
    let currentChapterIndex = null;
    let transcriptInView = false;
    let stickyBar = null;
    let stickyBarLabel = null;
    const passedAnchors = new Set();

    const mobileMq = window.matchMedia(CONFIG.MOBILE_QUERY);
    const wideMq = window.matchMedia(CONFIG.WIDE_QUERY);

    // ========== Utils ==========

    function computeMode() {
        if (mobileMq.matches) return 'mobile';
        if (wideMq.matches) return 'wide';
        return 'mid';
    }

    function generateId(text, index) {
        const slug = text
            .toLowerCase()
            .replace(/[^\w\s\u4e00-\u9fa5-]/g, '')
            .replace(/\s+/g, '-')
            .substring(0, 50);
        return `toc-heading-${slug}-${index}`;
    }

    function loadPinState() {
        try {
            const state = localStorage.getItem(CONFIG.STORAGE_KEY);
            return state === 'true';
        } catch (e) {
            console.warn('Failed to load TOC pin state:', e);
            return false;
        }
    }

    function savePinState(pinned) {
        try {
            localStorage.setItem(CONFIG.STORAGE_KEY, pinned.toString());
        } catch (e) {
            console.warn('Failed to save TOC pin state:', e);
        }
    }

    function loadCollapseState() {
        try {
            return localStorage.getItem(CONFIG.COLLAPSE_STORAGE_KEY) === 'true';
        } catch (e) {
            console.warn('Failed to load TOC collapse state:', e);
            return false;
        }
    }

    function saveCollapseState(collapsed) {
        try {
            localStorage.setItem(CONFIG.COLLAPSE_STORAGE_KEY, collapsed.toString());
        } catch (e) {
            console.warn('Failed to save TOC collapse state:', e);
        }
    }

    /**
     * Format chapter start seconds as mm:ss (or h:mm:ss), matching the
     * server-side _format_chapter_seconds. Empty string when unknown.
     */
    function formatChapterSeconds(seconds) {
        if (typeof seconds !== 'number' || !isFinite(seconds) || seconds < 0) {
            return '';
        }
        const total = Math.floor(seconds);
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = total % 60;
        const mm = String(minutes).padStart(2, '0');
        const ss = String(secs).padStart(2, '0');
        return hours > 0 ? (hours + ':' + mm + ':' + ss) : (mm + ':' + ss);
    }

    /**
     * Create an element with optional className and safe textContent.
     */
    function createEl(tag, className, text) {
        const el = document.createElement(tag);
        if (className) {
            el.className = className;
        }
        if (text != null && text !== '') {
            el.textContent = text;
        }
        return el;
    }

    /**
     * Append a TOC link item using DOM API only (textContent for labels).
     * List items default to li; outline section headers opt into div items.
     */
    function appendTocLink(listEl, options) {
        const item = createEl(options.itemTag || 'li', 'toc-item');
        const tagName = options.disabled ? 'span' : 'a';
        const link = createEl(tagName, options.className || 'toc-link');
        if (!options.disabled) {
            link.setAttribute('href', options.href || '#');
        }
        if (options.id != null) {
            link.dataset.id = String(options.id);
        }
        if (options.targetId != null) {
            link.dataset.targetId = String(options.targetId);
        }
        if (options.fallbackId != null) {
            link.dataset.fallbackId = String(options.fallbackId);
        }
        if (options.level != null) {
            link.setAttribute('data-level', String(options.level));
        }
        if (options.disabled) {
            link.setAttribute('aria-disabled', 'true');
            link.classList.add('toc-link-disabled');
        }
        // XSS-safe: never interpolate user text into HTML strings
        link.textContent = options.text || '';
        item.appendChild(link);
        listEl.appendChild(item);
        return link;
    }

    /**
     * Scroll the container just enough to reveal the item; no-op when the
     * item is already fully visible (avoids panel jitter).
     */
    function ensureItemVisible(container, item) {
        if (!container || !item) return;
        const cRect = container.getBoundingClientRect();
        const iRect = item.getBoundingClientRect();
        if (iRect.top >= cRect.top && iRect.bottom <= cRect.bottom) {
            return;
        }
        const delta = iRect.top - cRect.top - (cRect.height - iRect.height) / 2;
        container.scrollTop += delta;
    }

    // ========== Data extraction ==========

    function findOutlineSection(label) {
        return Array.from(document.querySelectorAll('.section')).find(section => {
            const h2 = section.querySelector('h2');
            return h2 && h2.textContent.includes(label);
        }) || null;
    }

    function extractHeadings() {
        const headings = [];

        const summarySection = findOutlineSection('内容总结');

        if (!summarySection) {
            console.warn('Summary section not found');
            return headings;
        }

        const contentDiv = summarySection.querySelector('.content');
        if (!contentDiv) {
            console.warn('Summary content area not found');
            return headings;
        }

        const headingElements = contentDiv.querySelectorAll('h1, h2, h3, h4');

        headingElements.forEach((element, index) => {
            const level = parseInt(element.tagName.substring(1), 10);
            const text = element.textContent.trim();

            if (!text) return;

            if (!element.id) {
                element.id = generateId(text, index);
            }

            headings.push({
                level: level,
                text,
                id: element.id,
                element: element
            });
        });

        console.log('Extracted headings: ' + headings.length);
        return headings;
    }

    function parseChapterAnchorIndex(anchorId, prefix) {
        const match = anchorId.match(new RegExp('^' + prefix + '-(\\d+)$'));
        return match ? Number(match[1]) : null;
    }

    /**
     * Append the original calibrated-text jump to every note chapter heading
     * that has the matching zero-based chapter anchor.
     */
    function appendNotesSourceLinks() {
        document.querySelectorAll(
            '#notes-content-block h2[id^="notes-chapter-"]'
        ).forEach((heading) => {
            const chapterIndex = parseChapterAnchorIndex(
                heading.id,
                'notes-chapter'
            );
            if (chapterIndex === null) return;

            const sourceId = 'chapter-anchor-' + chapterIndex;
            if (!document.getElementById(sourceId)) return;
            if (heading.querySelector('a.notes-source-link')) return;

            heading.appendChild(document.createTextNode(' '));
            const sourceLink = createEl('a', 'notes-source-link', '原文 ↗');
            sourceLink.setAttribute('href', '#' + sourceId);
            heading.appendChild(sourceLink);
        });
    }

    function findNotesSection() {
        return document.getElementById('notes-content-block')
            ? findOutlineSection('详细笔记')
            : null;
    }

    function findCalibratedSection() {
        return findOutlineSection('校对文本');
    }

    /**
     * Assign stable section ids used by the full-text leaf links.
     */
    function ensureOutlineSectionId(section, fallbackId) {
        if (!section.id) {
            section.id = fallbackId;
        }
        return section.id;
    }

    /**
     * Read chapters from the #chapters-data JSON island. The row target
     * priority is notes anchor, jumpable calibrated anchor, then #dlg-
     * fallback; a row remains visible even when none exists.
     */
    function readChaptersData() {
        const island = document.getElementById('chapters-data');
        if (!island) {
            return [];
        }

        let raw = null;
        try {
            raw = JSON.parse(island.textContent);
        } catch (e) {
            console.warn('Failed to parse chapters data island:', e);
            return [];
        }
        if (!Array.isArray(raw)) {
            return [];
        }

        const chapters = [];
        raw.forEach((ch) => {
            if (!ch || typeof ch !== 'object') return;

            let index = parseInt(ch.index, 10);
            if (isNaN(index)) index = chapters.length;

            const title = (typeof ch.title === 'string' ? ch.title : '').trim();
            if (!title) return;

            const gist = typeof ch.gist === 'string' ? ch.gist : '';

            let startSeg = parseInt(ch.start_seg, 10);
            if (isNaN(startSeg)) startSeg = null;

            const jumpOk = ch.jump_ok === true;
            const anchorId = 'chapter-anchor-' + index;
            const dlgId = startSeg === null ? null : 'dlg-' + startSeg;
            const notesEl = document.getElementById('notes-chapter-' + index);
            const anchorEl = jumpOk ? document.getElementById(anchorId) : null;
            const dlgEl = jumpOk && dlgId ? document.getElementById(dlgId) : null;

            let targetId = null;
            let fallbackId = null;
            let targetElement = null;
            if (notesEl) {
                targetId = notesEl.id;
                targetElement = notesEl;
            } else if (anchorEl) {
                targetId = anchorId;
                targetElement = anchorEl;
            } else if (dlgEl) {
                fallbackId = dlgId;
                targetElement = dlgEl;
            }

            const canJump = Boolean(targetElement);

            chapters.push({
                index: index,
                title: title,
                gist: gist,
                timeLabel: formatChapterSeconds(ch.start_time),
                startSeg: startSeg,
                jumpOk: jumpOk,
                anchorId: anchorId,
                anchorEl: anchorEl,
                dlgId: dlgId,
                targetId: targetId,
                fallbackId: fallbackId,
                targetElement: targetElement,
                canJump: canJump
            });
        });

        console.log('Loaded chapters: ' + chapters.length);
        return chapters;
    }

    // ========== UI (DOM API) ==========

    function appendOutlineToggle(header, label, expanded) {
        const toggle = createEl('button', 'toc-outline-toggle', expanded ? '▾' : '▸');
        toggle.type = 'button';
        toggle.setAttribute('aria-expanded', String(expanded));
        toggle.setAttribute('aria-label', (expanded ? '折叠' : '展开') + label);
        header.appendChild(toggle);
        return toggle;
    }

    function appendSummaryNode(listEl) {
        if (!tocData.summarySection) return;

        const sectionId = ensureOutlineSectionId(
            tocData.summarySection,
            'summary-section'
        );
        const item = createEl('li', 'toc-outline-section toc-summary-node');
        const header = createEl('div', 'toc-outline-header');
        const parent = appendTocLink(header, {
            href: '#' + sectionId,
            text: '内容总结',
            id: sectionId,
            itemTag: 'div',
            className: 'toc-link toc-outline-parent'
        });
        parent.dataset.outlineRole = 'section';

        if (tocData.headings.length > 0) {
            item.classList.add('toc-outline-collapsed');
            appendOutlineToggle(header, '内容总结', false);
        }
        item.appendChild(header);

        if (tocData.headings.length > 0) {
            const childList = createEl('ul', 'toc-outline-children');
            tocData.headings.forEach((heading) => {
                appendTocLink(childList, {
                    href: '#' + heading.id,
                    text: heading.text,
                    level: heading.level,
                    id: heading.id,
                    className: 'toc-link toc-outline-child'
                });
            });
            item.appendChild(childList);
        }

        listEl.appendChild(item);
    }

    /**
     * One chapter row, shared by the PC panel and the mobile drawer.
     * Time + title row (whole-row jump) with the full gist text below it.
     * Gists are short, so the gist is plain inert text: no clamping and
     * no expand/collapse interaction.
     */
    function buildChapterItem(chapter) {
        const item = createEl('li', 'toc-outline-section toc-chapter-node toc-chapter-item');
        item.dataset.chapterIndex = String(chapter.index);
        if (!chapter.canJump) {
            item.classList.add('toc-chapter-disabled');
        }

        const header = createEl('div', 'toc-outline-header toc-chapter-header');
        const main = createEl('button', 'toc-chapter-main');
        main.type = 'button';
        main.dataset.chapterIndex = String(chapter.index);
        main.dataset.id = 'toc-chapter-' + chapter.index;
        if (chapter.targetId) {
            main.dataset.targetId = chapter.targetId;
        }
        if (chapter.fallbackId) {
            main.dataset.fallbackId = chapter.fallbackId;
        }
        if (!chapter.canJump) {
            main.disabled = true;
            main.setAttribute('aria-disabled', 'true');
        }
        if (chapter.timeLabel) {
            main.appendChild(createEl('span', 'toc-chapter-time', chapter.timeLabel));
        }
        main.appendChild(createEl('span', 'toc-chapter-title', chapter.title));
        header.appendChild(main);
        item.appendChild(header);

        if (chapter.gist) {
            item.appendChild(createEl('div', 'toc-chapter-gist', chapter.gist));
        }

        return item;
    }

    function buildChaptersNode(listEl) {
        const item = createEl('li', 'toc-outline-section toc-chapters-node');
        const header = createEl('div', 'toc-outline-header toc-chapters-header');
        const title = createEl(
            'div',
            'toc-link toc-outline-parent',
            '章节 (' + tocData.chapters.length + ')'
        );
        title.dataset.outlineRole = 'chapters';
        header.appendChild(title);
        appendOutlineToggle(
            header,
            '章节 (' + tocData.chapters.length + ')',
            true
        );
        item.appendChild(header);

        const childList = createEl('ul', 'toc-outline-children');
        tocData.chapters.forEach((chapter) => {
            childList.appendChild(buildChapterItem(chapter));
        });
        item.appendChild(childList);
        listEl.appendChild(item);
    }

    function appendFullTextLeaf(listEl, label, section, className) {
        if (!section) return;
        const sectionId = ensureOutlineSectionId(
            section,
            className === 'toc-notes-leaf' ? 'notes-section' : 'calibrated-section'
        );
        appendTocLink(listEl, {
            href: '#' + sectionId,
            text: label,
            id: sectionId,
            targetId: sectionId,
            level: 1,
            className: 'toc-link toc-full-text-leaf ' + className
        });
    }

    function buildTocTree(listEl) {
        appendSummaryNode(listEl);

        if (hasChapters) {
            buildChaptersNode(listEl);
        }

        appendFullTextLeaf(
            listEl,
            '详细笔记（全文）',
            tocData.notesSection,
            'toc-notes-leaf'
        );
        appendFullTextLeaf(
            listEl,
            '校对文本（全文）',
            tocData.calibratedSection,
            'toc-calibrated-leaf'
        );
    }

    function createPCToc() {
        const container = createEl('div', 'floating-toc-container');
        container.id = 'floating-toc';

        if (hasChapters) {
            container.classList.add('toc-new');
        } else {
            container.classList.add('collapsed');
        }

        const indicator = createEl('div', 'toc-indicator');
        for (let i = 0; i < 4; i++) {
            indicator.appendChild(createEl('div', 'toc-indicator-line'));
        }
        container.appendChild(indicator);

        const header = createEl('div', 'toc-header');
        if (hasChapters) {
            header.appendChild(createEl('div', 'toc-title', '目录'));
            const collapseBtn = createEl('button', 'toc-collapse-btn');
            collapseBtn.id = 'toc-collapse-btn';
            collapseBtn.type = 'button';
            collapseBtn.title = '收起目录';
            collapseBtn.textContent = '»';
            header.appendChild(collapseBtn);
        } else {
            header.appendChild(createEl('div', 'toc-title', '目录'));
            const pinBtn = createEl('button', 'toc-pin-btn');
            pinBtn.id = 'toc-pin-btn';
            pinBtn.title = '固定目录（点击保持展开）';
            pinBtn.type = 'button';
            pinBtn.textContent = '📌';
            header.appendChild(pinBtn);
        }
        container.appendChild(header);

        const content = createEl('div', 'toc-content');
        const list = createEl('ul', 'toc-list');
        buildTocTree(list);
        content.appendChild(list);
        container.appendChild(content);

        return container;
    }

    function createMobileTocParts() {
        const btn = createEl('button', 'floating-toc-mobile-btn');
        btn.id = 'toc-mobile-btn';
        btn.title = '目录';
        btn.type = 'button';
        btn.textContent = '📑';

        const panel = createEl('div', 'floating-toc-mobile-panel');
        panel.id = 'toc-mobile-panel';

        const overlay = createEl('div', 'toc-mobile-overlay');
        overlay.id = 'toc-mobile-overlay';
        panel.appendChild(overlay);

        const mobileContent = createEl('div', 'toc-mobile-content');
        const mobileHeader = createEl('div', 'toc-mobile-header');
        mobileHeader.appendChild(createEl('div', 'toc-mobile-title', '目录'));
        const closeBtn = createEl('button', 'toc-mobile-close-btn');
        closeBtn.id = 'toc-mobile-close-btn';
        closeBtn.type = 'button';
        closeBtn.textContent = '✕';
        mobileHeader.appendChild(closeBtn);
        mobileContent.appendChild(mobileHeader);

        const body = createEl('div', 'toc-mobile-body');
        const list = createEl('ul', 'toc-list');
        buildTocTree(list);
        body.appendChild(list);
        mobileContent.appendChild(body);
        panel.appendChild(mobileContent);

        return { btn: btn, panel: panel };
    }

    /**
     * Sticky current-chapter bar (mobile only). Created once, JS toggles the
     * hidden attribute and the label text.
     */
    function createStickyBar() {
        const bar = createEl('div', 'chapter-sticky-bar');
        bar.setAttribute('role', 'button');
        bar.hidden = true;
        stickyBarLabel = createEl('span', 'chapter-sticky-bar-label');
        bar.appendChild(stickyBarLabel);
        bar.appendChild(createEl('span', 'chapter-sticky-bar-icon', '☰'));
        stickyBar = bar;
        return bar;
    }

    function hasTocContent() {
        return !!tocData.summarySection
            || !!tocData.notesSection
            || !!tocData.calibratedSection
            || tocData.headings.length > 0
            || tocData.chapters.length > 0;
    }

    function renderTOC() {
        const existingPC = document.getElementById('floating-toc');
        const existingMobileBtn = document.getElementById('toc-mobile-btn');
        const existingMobilePanel = document.getElementById('toc-mobile-panel');
        const existingSticky = document.querySelector('.chapter-sticky-bar');

        if (existingPC) existingPC.remove();
        if (existingMobileBtn) existingMobileBtn.remove();
        if (existingMobilePanel) existingMobilePanel.remove();
        if (existingSticky) existingSticky.remove();
        stickyBar = null;
        stickyBarLabel = null;

        if (!hasTocContent()) {
            console.log('No TOC data, skip render');
            return;
        }

        // Pure DOM append — user text is never inserted as an HTML string.
        document.body.appendChild(createPCToc());
        const mobile = createMobileTocParts();
        document.body.appendChild(mobile.btn);
        document.body.appendChild(mobile.panel);
        if (hasChapters) {
            document.body.appendChild(createStickyBar());
        }

        console.log('TOC render complete');
    }

    // ========== Mode / breakpoints ==========

    function applyCollapsed(container, collapsed) {
        container.classList.toggle('toc-collapsed', collapsed);
        const btn = container.querySelector('#toc-collapse-btn');
        if (btn) {
            btn.textContent = collapsed ? '«' : '»';
            btn.title = collapsed ? '展开目录' : '收起目录';
        }
    }

    function applyMode() {
        const prevMode = mode;
        mode = computeMode();

        if (prevMode === 'mobile' && mode !== 'mobile') {
            closeMobilePanel();
        }

        if (hasChapters) {
            const container = document.getElementById('floating-toc');
            if (container) {
                if (mode === 'wide') {
                    container.classList.add('toc-docked');
                    applyCollapsed(container, false);
                } else {
                    container.classList.remove('toc-docked');
                    applyCollapsed(container, mode === 'mid' && loadCollapseState());
                }
            }
        }

        document.body.classList.toggle('toc-wide-margin', hasChapters && mode === 'wide');
        updateStickyBar();
        scrollPanelToCurrentChapter();
    }

    function setupBreakpointListeners() {
        const onChange = () => applyMode();
        if (typeof mobileMq.addEventListener === 'function') {
            mobileMq.addEventListener('change', onChange);
            wideMq.addEventListener('change', onChange);
        } else if (typeof mobileMq.addListener === 'function') {
            mobileMq.addListener(onChange);
            wideMq.addListener(onChange);
        }
    }

    // ========== Events ==========

    function resolveTocTarget(targetId, fallbackId) {
        let targetElement = targetId ? document.getElementById(targetId) : null;
        if (!targetElement && fallbackId) {
            targetElement = document.getElementById(fallbackId);
        }
        return targetElement;
    }

    /**
     * Open closed details ancestors before a TOC target is scrolled into view.
     */
    function openTocDetailsAncestors(targetElement) {
        let currentElement = targetElement;
        while (currentElement) {
            if (currentElement instanceof HTMLDetailsElement && !currentElement.open) {
                currentElement.open = true;
            }
            currentElement = currentElement.parentElement;
        }
    }

    /**
     * Scroll tree targets through one fallback-aware path and open any closed
     * details ancestor before the smooth jump.
     */
    function scrollToTocTarget(targetId, fallbackId) {
        const targetElement = resolveTocTarget(targetId, fallbackId);
        if (!targetElement) {
            console.warn('TOC target not found:', targetId || fallbackId);
            return false;
        }

        openTocDetailsAncestors(targetElement);
        targetElement.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
        return true;
    }

    function handleTocClick(e) {
        const link = e.target.closest('.toc-link');
        if (!link || link.tagName !== 'A') return;

        e.preventDefault();

        const targetId = link.dataset.targetId || link.dataset.id;
        const activeId = link.dataset.id || targetId;
        if (!scrollToTocTarget(targetId, link.dataset.fallbackId)) {
            return;
        }

        if (mode === 'mobile') {
            closeMobilePanel();
        }

        setTimeout(() => {
            updateActiveLink(activeId);
        }, 100);
    }

    function handleChapterJump(mainEl) {
        if (mainEl.disabled || mainEl.getAttribute('aria-disabled') === 'true') {
            return;
        }

        const targetId = mainEl.dataset.targetId;
        const fallbackId = mainEl.dataset.fallbackId;
        if (!targetId && !fallbackId) {
            return;
        }

        if (!scrollToTocTarget(targetId, fallbackId)) {
            return;
        }

        if (mode === 'mobile') {
            closeMobilePanel();
        }
    }

    function handlePinClick() {
        const container = document.getElementById('floating-toc');
        const pinBtn = document.getElementById('toc-pin-btn');

        if (!container || !pinBtn) return;

        isPinned = !isPinned;

        if (isPinned) {
            pinBtn.classList.add('animating-pin');
            setTimeout(() => {
                pinBtn.classList.remove('animating-pin');
            }, 400);

            container.classList.add('pinned');
            container.classList.remove('collapsed');
            pinBtn.classList.add('pinned');
            pinBtn.title = '取消固定目录（已固定）';
        } else {
            pinBtn.classList.add('animating-unpin');
            setTimeout(() => {
                pinBtn.classList.remove('animating-unpin');
            }, 400);

            container.classList.remove('pinned');
            container.classList.add('collapsed');
            pinBtn.classList.remove('pinned');
            pinBtn.title = '固定目录（点击保持展开）';
        }

        savePinState(isPinned);
    }

    function handleCollapseToggle() {
        // Manual collapse only applies to the mid breakpoint; the wide
        // breakpoint keeps the panel docked/expanded.
        if (mode !== 'mid') return;

        const container = document.getElementById('floating-toc');
        if (!container) return;

        const collapsed = !container.classList.contains('toc-collapsed');
        applyCollapsed(container, collapsed);
        saveCollapseState(collapsed);
    }

    function toggleOutlineSection(toggleEl) {
        const section = toggleEl.closest('.toc-outline-section');
        if (!section) return;

        const expanded = toggleEl.getAttribute('aria-expanded') === 'true';
        const label = section.querySelector('.toc-outline-parent, .toc-chapter-main');
        toggleEl.setAttribute('aria-expanded', String(!expanded));
        toggleEl.textContent = expanded ? '▸' : '▾';
        toggleEl.setAttribute(
            'aria-label',
            (expanded ? '展开' : '折叠') + (label ? label.textContent : '区块')
        );
        section.classList.toggle('toc-outline-collapsed', expanded);
    }

    function openMobilePanel() {
        const panel = document.getElementById('toc-mobile-panel');
        if (!panel) return;

        panel.classList.add('show');
        document.body.style.overflow = 'hidden';

        // Reveal the current chapter row when the drawer opens.
        if (hasChapters && currentChapterIndex !== null) {
            const body = panel.querySelector('.toc-mobile-body');
            const item = panel.querySelector('.toc-chapter-item.current');
            if (body && item) {
                ensureItemVisible(body, item);
            }
        }
    }

    function closeMobilePanel() {
        const panel = document.getElementById('toc-mobile-panel');
        if (panel) {
            panel.classList.remove('show');
            document.body.style.overflow = '';
        }
    }

    function updateActiveLink(activeId) {
        const links = document.querySelectorAll('.toc-link, .toc-chapter-main');
        links.forEach(link => {
            if (link.dataset && link.dataset.id === activeId) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    // ========== Current chapter tracking ==========

    function updateStickyBar() {
        if (!stickyBar) return;

        const show = hasChapters
            && mode === 'mobile'
            && transcriptInView
            && currentChapterIndex !== null;

        if (!show) {
            stickyBar.hidden = true;
            return;
        }

        const chapter = tocData.chapters.find(c => c.index === currentChapterIndex);
        if (!chapter) {
            stickyBar.hidden = true;
            return;
        }

        if (stickyBarLabel) {
            stickyBarLabel.textContent = (chapter.index + 1) + '. ' + chapter.title;
        }
        stickyBar.hidden = false;
    }

    function scrollPanelToCurrentChapter() {
        if (currentChapterIndex === null || mode === 'mobile') return;
        const container = document.getElementById('floating-toc');
        if (!container) return;
        const content = container.querySelector('.toc-content');
        const item = container.querySelector('.toc-chapter-item.current');
        if (content && item) {
            ensureItemVisible(content, item);
        }
    }

    function setCurrentChapter(index) {
        const changed = currentChapterIndex !== index;
        currentChapterIndex = index;

        document.querySelectorAll('.toc-chapter-item').forEach(item => {
            const match = index !== null && item.dataset.chapterIndex === String(index);
            item.classList.toggle('current', match);
        });

        if (changed) {
            scrollPanelToCurrentChapter();
        }
        updateStickyBar();
    }

    function collectChapterObserverAnchors() {
        return Array.from(document.querySelectorAll(
            '#notes-content-block h2[id^="notes-chapter-"], '
                + '#calibrated-content-block [id^="chapter-anchor-"]'
        )).map((element) => {
            const chapterIndex = element.id.startsWith('notes-chapter-')
                ? parseChapterAnchorIndex(element.id, 'notes-chapter')
                : parseChapterAnchorIndex(element.id, 'chapter-anchor');
            return { element: element, chapterIndex: chapterIndex };
        }).filter(anchor => anchor.chapterIndex !== null);
    }

    function setupChapterObserver() {
        const chapterAnchors = collectChapterObserverAnchors();
        if (chapterAnchors.length === 0) return;

        if (chapterObserver) {
            chapterObserver.disconnect();
        }
        passedAnchors.clear();
        const positionByElement = new Map(
            chapterAnchors.map((anchor, position) => [anchor.element, position])
        );

        chapterObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                const position = positionByElement.get(entry.target);
                if (position === undefined) return;
                // Anchor in view, or already scrolled above the viewport top,
                // means its chapter has been reached.
                const passed = entry.isIntersecting
                    || entry.boundingClientRect.top < 0;
                if (passed) {
                    passedAnchors.add(position);
                } else {
                    passedAnchors.delete(position);
                }
            });

            if (passedAnchors.size > 0) {
                const latestPosition = Math.max(...Array.from(passedAnchors));
                setCurrentChapter(chapterAnchors[latestPosition].chapterIndex);
            } else {
                setCurrentChapter(null);
            }
        }, { threshold: 0 });

        chapterAnchors.forEach((anchor) => {
            chapterObserver.observe(anchor.element);
        });

        console.log('Chapter observer ready');
    }

    function setupTranscriptObserver() {
        if (!hasChapters) return;

        const block = document.getElementById('calibrated-content-block');
        if (!block) return;

        transcriptObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                transcriptInView = entry.isIntersecting;
            });
            updateStickyBar();
        }, { threshold: 0 });

        transcriptObserver.observe(block);
    }

    // ========== Scroll observer (outline) ==========

    function setupScrollObserver() {
        if (observer) {
            observer.disconnect();
        }

        const idByElement = new Map();
        const addTarget = (element, activeId) => {
            if (!element || !activeId || idByElement.has(element)) return;
            idByElement.set(element, activeId);
        };

        if (tocData.summarySection) {
            addTarget(
                tocData.summarySection,
                ensureOutlineSectionId(tocData.summarySection, 'summary-section')
            );
        }
        tocData.headings.forEach(heading => {
            addTarget(heading.element, heading.id);
        });
        tocData.chapters.forEach(chapter => {
            if (!chapter.targetElement) return;
            addTarget(chapter.targetElement, 'toc-chapter-' + chapter.index);
        });
        if (tocData.notesSection) {
            addTarget(
                tocData.notesSection,
                ensureOutlineSectionId(tocData.notesSection, 'notes-section')
            );
        }
        if (tocData.calibratedSection) {
            addTarget(
                tocData.calibratedSection,
                ensureOutlineSectionId(
                    tocData.calibratedSection,
                    'calibrated-section'
                )
            );
        }

        if (idByElement.size === 0) return;

        observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = idByElement.get(entry.target)
                        || entry.target.id;
                    updateActiveLink(id);
                }
            });
        }, CONFIG.OBSERVER_OPTIONS);

        idByElement.forEach((_activeId, element) => {
            observer.observe(element);
        });

        console.log('Scroll observer ready');
    }

    // ========== Init ==========

    function bindEvents() {
        document.addEventListener('click', (e) => {
            if (e.target.closest('#toc-pin-btn')) {
                handlePinClick();
                return;
            }

            if (e.target.closest('#toc-collapse-btn')) {
                handleCollapseToggle();
                return;
            }

            // Collapsed chapter panel: clicking the indicator bar re-expands.
            if (e.target.closest('#floating-toc.toc-collapsed .toc-indicator')) {
                handleCollapseToggle();
                return;
            }

            if (e.target.closest('.toc-outline-toggle')) {
                toggleOutlineSection(e.target.closest('.toc-outline-toggle'));
                return;
            }

            // Whole chapter row is one jump target: title row or gist.
            // Route through the row's .toc-chapter-main (it carries the
            // target priority and disabled state).
            if (e.target.closest('.toc-chapter-main, .toc-chapter-gist')) {
                const item = e.target.closest('.toc-chapter-item');
                const main = item ? item.querySelector('.toc-chapter-main') : null;
                if (main) {
                    handleChapterJump(main);
                }
                return;
            }

            if (e.target.closest('.chapter-sticky-bar')) {
                openMobilePanel();
                return;
            }

            if (e.target.closest('#toc-mobile-btn')) {
                openMobilePanel();
                return;
            }

            if (e.target.closest('#toc-mobile-close-btn')) {
                e.preventDefault();
                e.stopPropagation();
                closeMobilePanel();
                return;
            }

            if (e.target.closest('#toc-mobile-overlay')) {
                closeMobilePanel();
                return;
            }

            if (e.target.closest('a.toc-link')) {
                handleTocClick(e);
                return;
            }
        });

        console.log('TOC events bound');
    }

    function init() {
        console.log('Init floating TOC...');

        mode = computeMode();

        tocData.summarySection = findOutlineSection('内容总结');
        tocData.notesSection = findNotesSection();
        tocData.calibratedSection = findCalibratedSection();
        tocData.headings = extractHeadings();
        appendNotesSourceLinks();
        tocData.chapters = readChaptersData();
        hasChapters = tocData.chapters.length > 0;

        if (!hasTocContent()) {
            console.log('No headings/chapters/calibrated section; skip TOC');
            return;
        }

        renderTOC();
        bindEvents();
        applyMode();

        if (!hasChapters) {
            // Legacy behavior: collapsed indicator bar, pin to keep expanded.
            isPinned = loadPinState();
            if (isPinned && mode !== 'mobile') {
                const container = document.getElementById('floating-toc');
                const pinBtn = document.getElementById('toc-pin-btn');
                if (container && pinBtn) {
                    container.classList.add('pinned');
                    container.classList.remove('collapsed');
                    pinBtn.classList.add('pinned');
                    pinBtn.title = '取消固定目录（已固定）';
                }
            } else {
                const pinBtn = document.getElementById('toc-pin-btn');
                if (pinBtn) {
                    pinBtn.title = '固定目录（点击保持展开）';
                }
            }
        }

        setupScrollObserver();
        setupChapterObserver();
        setupTranscriptObserver();
        setupBreakpointListeners();

        console.log('Floating TOC ready');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
