import { expect, test } from '@playwright/test';
import { resetBackend } from '../reset-backend';

const baseURL = process.env.VTA_BROWSER_PORT
  ? `http://127.0.0.1:${process.env.VTA_BROWSER_PORT}`
  : '';
const longUrl = `https://x.com/${'L'.repeat(220)}`;
const longTitle = `LongTitle${'T'.repeat(220)}`;
const viewports = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 375, height: 667 },
];

test.beforeEach(async ({ request }) => {
  if (!baseURL) throw new Error('VTA_BROWSER_PORT must be set by the browser test runner');
  await resetBackend(request, baseURL);
});

async function expectNoHorizontalOverflow(page: import('@playwright/test').Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth, 'document must not scroll horizontally').toBeLessThanOrEqual(
    dimensions.clientWidth,
  );
}

async function expectControlsInsideCards(
  page: import('@playwright/test').Page,
  cardSelector: string,
  controlSelector: string,
  referenceSelector: string,
): Promise<void> {
  const reference = await page.locator(referenceSelector).first().boundingBox();
  expect(reference, 'short-text reference control must be visible').not.toBeNull();
  const controls = await page.locator(cardSelector).evaluateAll((cards, selector) =>
    cards.flatMap((card) => {
      const cardBox = card.getBoundingClientRect();
      return Array.from(card.querySelectorAll(selector)).map((control) => {
        const box = control.getBoundingClientRect();
        return {
          label: control.textContent?.trim() ?? '',
          cardLeft: cardBox.left,
          cardRight: cardBox.right,
          cardTop: cardBox.top,
          cardBottom: cardBox.bottom,
          left: box.left,
          right: box.right,
          top: box.top,
          bottom: box.bottom,
          height: box.height,
        };
      });
    }),
    controlSelector,
  );
  expect(controls.length, 'cards must contain measurable controls').toBeGreaterThan(0);
  for (const control of controls) {
    expect(control.left, `${control.label} left edge must stay inside its card`).toBeGreaterThanOrEqual(
      control.cardLeft - 0.5,
    );
    expect(control.right, `${control.label} right edge must stay inside its card`).toBeLessThanOrEqual(
      control.cardRight + 0.5,
    );
    expect(control.top, `${control.label} top edge must stay inside its card`).toBeGreaterThanOrEqual(
      control.cardTop - 0.5,
    );
    expect(control.bottom, `${control.label} bottom edge must stay inside its card`).toBeLessThanOrEqual(
      control.cardBottom + 0.5,
    );
    expect(control.height, `${control.label} must remain a single-line control`).toBeLessThanOrEqual(
      (reference?.height ?? 0) * 1.3,
    );
  }
}

for (const viewport of viewports) {
  test(`recent tasks keep long text and actions inside cards at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.addInitScript(({ longUrlValue, longTitleValue }) => {
      localStorage.setItem('vta_task_history', JSON.stringify([
        {
          id: 'layout-long',
          title: longTitleValue,
          url: longUrlValue,
          original_text: longUrlValue,
          timestamp: '2026-10-21T12:00:00.000Z',
          view_token: 'browser-fixture-view',
        },
        {
          id: 'layout-short',
          title: 'Short reference task',
          url: 'https://x.com/short',
          original_text: 'https://x.com/short',
          timestamp: '2026-10-21T11:00:00.000Z',
          view_token: 'browser-fixture-view',
        },
      ]));
    }, { longUrlValue: longUrl, longTitleValue: longTitle });
    await page.goto('/add_task_by_web');

    const longCard = page.locator('.history-item:has([data-task-id="layout-long"])');
    await expect(longCard).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await expectControlsInsideCards(
      page,
      '.history-item',
      '.history-btn',
      '.history-item:has([data-task-id="layout-short"]) .history-btn',
    );
    await expect(longCard.locator('.history-original-text')).toHaveCount(1);
    await expect(longCard.locator('.history-url')).toHaveCount(0);

    if (viewport.width === 1280) {
      await page.screenshot({ path: '/tmp/vta-layout-overflow-home-1280.png', fullPage: true });
    } else {
      await page.screenshot({ path: '/tmp/vta-layout-overflow-home-375.png', fullPage: true });
    }
  });

  test(`history rows keep long text and actions inside cards at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/static/history.html');
    await page.locator('#apiKeyInput').fill('browser-fixture-token');
    await page.locator('#historyQueryBtn').click();
    await expect(page.locator('#filterBar')).toBeVisible();
    await page.locator('#filterSource').selectOption('upload');
    const longRow = page.locator('#listArea .task-row').filter({ hasText: longTitle });
    await expect(longRow).toBeVisible();
    await expect(longRow.locator('.task-author')).toContainText(longUrl);
    await expectNoHorizontalOverflow(page);
    await expectControlsInsideCards(
      page,
      '#listArea .task-row',
      '.btn-stop-share',
      '#listArea .task-row:has(.task-title:text("浏览器本地上传样本")) .btn-stop-share',
    );
  });

  test(`transcript page keeps a long title and actions inside sections at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/view/browser-layout-overflow');
    await expect(page.locator('.header h1')).toContainText(longTitle);
    await expectNoHorizontalOverflow(page);
    await expectControlsInsideCards(
      page,
      '.section, .quick-copy-bar',
      'button, a.btn',
      '.section button, .quick-copy-bar button',
    );
  });
}
