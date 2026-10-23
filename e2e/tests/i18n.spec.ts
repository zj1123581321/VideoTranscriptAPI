import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { resetBackend } from '../reset-backend';

const staticTitles = JSON.parse(
  readFileSync('../tests/unit/i18n_web/fixtures/baselines/static_titles.json', 'utf8'),
) as { submit: { title: string }; history: { title: string } };

const baseURL = process.env.VTA_BROWSER_PORT
  ? `http://127.0.0.1:${process.env.VTA_BROWSER_PORT}`
  : '';
const browserErrors = new WeakMap<Page, string[]>();

function observeBrowser(page: Page): void {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('requestfailed', (request) => {
    errors.push(`request failed: ${request.method()} ${request.url()} (${request.failure()?.errorText})`);
  });
  page.on('response', (response) => {
    if (response.status() >= 400) {
      errors.push(`HTTP ${response.status()}: ${response.request().method()} ${response.url()}`);
    }
  });
}

async function setLanguage(request: APIRequestContext, language: 'zh-CN' | 'en'): Promise<void> {
  const response = await request.post(`${baseURL}/__e2e__/language`, {
    data: { language },
  });
  if (!response.ok()) {
    throw new Error(`POST /__e2e__/language failed with HTTP ${response.status()}`);
  }
}

test.beforeEach(async ({ page, request }) => {
  if (!baseURL) throw new Error('VTA_BROWSER_PORT must be set by the browser test runner');
  observeBrowser(page);
  page.context().on('page', observeBrowser);
  await resetBackend(request, baseURL);
});

test.afterEach(async ({ page }) => {
  for (const observedPage of page.context().pages()) {
    expect(browserErrors.get(observedPage) ?? []).toEqual([]);
  }
});

test('zh-CN html lang and primary copy stay Chinese', async ({ page }) => {
  await page.goto('/add_task_by_web');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: '视频转录服务' })).toBeVisible();
  await expect(page).toHaveTitle(staticTitles.submit.title);
  expect(await page.locator('body').innerText()).toContain('视频转录服务');

  await page.goto('/static/history.html');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: '任务历史' })).toBeVisible();
  await expect(page).toHaveTitle(staticTitles.history.title);
  expect(await page.locator('body').innerText()).toContain('任务历史');

  await page.goto('/view/browser-fixture-view');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: /内容总结/ })).toBeVisible();
});

const CJK_RE_SOURCE = '[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]';
const EN_PAGES: Array<{ path: string; name: string }> = [
  { path: '/', name: 'home' },
  { path: '/add_task_by_web', name: 'submit' },
  { path: '/static/history.html', name: 'history' },
  { path: '/view/browser-fixture-view', name: 'result' },
  { path: '/view/processing', name: 'processing' },
  { path: '/view/failed', name: 'error' },
  { path: '/view/cleaned', name: 'cleaned' },
];

async function collectCjkHits(page: Page): Promise<string[]> {
  return page.evaluate((reSource: string) => {
    const re = new RegExp(reSource);
    const hits: string[] = [];
    const pushSnippets = (label: string, text: string | null) => {
      if (!text || !re.test(text)) return;
      for (const line of text.split(/\n+/)) {
        const trimmed = line.trim();
        if (trimmed && re.test(trimmed)) {
          hits.push(`${label}: ${trimmed.slice(0, 160)}`);
        }
      }
    };
    pushSnippets('title', document.title);
    const languageNames = new Set(
      Array.from(document.querySelectorAll('.public-language-switch a')).map((el) => (el.textContent || '').trim()),
    );
    const bodyLines = (document.body ? document.body.innerText : '').split(/\n+/);
    pushSnippets('body', bodyLines.filter((line) => !languageNames.has(line.trim())).join('\n'));
    for (const el of Array.from(document.querySelectorAll('[placeholder], [aria-label], [title]'))) {
      pushSnippets('placeholder', el.getAttribute('placeholder'));
      pushSnippets('aria-label', el.getAttribute('aria-label'));
      pushSnippets('title-attr', el.getAttribute('title'));
    }
    return hits;
  }, CJK_RE_SOURCE);
}

test('en html lang and primary copy switch after fixture language change', async ({ page, request }) => {
  await setLanguage(request, 'en');

  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('link', { name: /Submit a task/ })).toBeVisible();

  await page.goto('/add_task_by_web');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: 'Video transcription' })).toBeVisible();

  await page.goto('/static/history.html');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: 'Task history' })).toBeVisible();

  await page.goto('/view/browser-fixture-view');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Summary/ })).toBeVisible();
  await expect(page.locator('.deep-read-prompt-btn')).toContainText('Copy deep-read prompt');
  const promptPayload = await page.locator('.deep-read-prompt-btn').getAttribute('data-template');
  expect(JSON.parse(promptPayload || 'null')).toContain('Read the full proofread podcast transcript');

  await page.goto('/view/processing');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Transcription in progress/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'English' })).toHaveAttribute(
    'href',
    '/view/processing?lang=en',
  );

  await page.goto('/view/failed');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Something went wrong/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'English' })).toHaveAttribute(
    'href',
    '/view/failed?lang=en',
  );

  await page.goto('/view/cleaned');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Content cleaned up/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'English' })).toHaveAttribute(
    'href',
    '/view/cleaned?lang=en',
  );
});

test('en pages expose no CJK in title, body text, or labeled attributes', async ({ page, request }) => {
  await setLanguage(request, 'en');
  const failures: string[] = [];
  for (const pageInfo of EN_PAGES) {
    await page.goto(pageInfo.path);
    const hits = await collectCjkHits(page);
    if (hits.length > 0) {
      failures.push(`${pageInfo.name} ${pageInfo.path}\n  ${hits.join('\n  ')}`);
    }
  }
  expect(failures, failures.join('\n\n')).toEqual([]);
});

test('public share page switches UI language while preserving original content and clipboard payloads', async ({ page }) => {
  await page.goto('/view/browser-fixture-view?source=share');
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await page.getByRole('link', { name: 'English' }).click();

  await expect(page).toHaveURL(/source=share&lang=en$/);
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Summary/ })).toBeVisible();
  await expect(page.locator('#calibrated-content-block')).toContainText('隔离浏览器夹具中的正文');
  await expect(page.locator('.deep-read-prompt-btn')).toContainText('Copy deep-read prompt');
  expect(await page.evaluate(() => (window as Window & { __VTA_LANG__?: string }).__VTA_LANG__)).toBe('en');

  const copyRaw = page.locator('.quick-copy-btn:not(.deep-read-prompt-btn):not(.share-summary-btn)').first();
  await copyRaw.click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain(
    '/view/browser-fixture-view?raw=calibrated&lang=en',
  );

  const summaryShare = page.locator('.share-summary-btn');
  await summaryShare.click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain(
    'Summary and proofread: http://127.0.0.1:',
  );
  const summaryClipboard = await page.evaluate(() => navigator.clipboard.readText());
  expect(summaryClipboard).toContain('/view/browser-fixture-view?lang=en');
  expect(summaryClipboard).toContain('这是原页面模板显示的样例总结。');

  const promptButton = page.locator('.deep-read-prompt-btn');
  await expect(promptButton).not.toHaveClass(/copied/);
  await promptButton.click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain(
    '请读取下面 URL 的播客校对稿全文',
  );
  const promptClipboard = await page.evaluate(() => navigator.clipboard.readText());
  expect(promptClipboard).toContain('/view/browser-fixture-view?raw=calibrated&lang=en');

  const pageExport = await page.request.get(
    `${baseURL}/view/browser-fixture-view?page=calibrated&lang=en`,
  );
  const pageBytes = await pageExport.body();
  expect(pageExport.status()).toBe(200);
  const pageHtmlBytes = pageBytes.toString('utf8');
  expect(pageHtmlBytes).toContain('<html lang="en">');
  expect(pageHtmlBytes).toContain('property="og:locale" content="en"');
  expect(pageHtmlBytes).toContain('隔离浏览器夹具中的正文');
  const rawExport = await page.request.get(
    `${baseURL}/view/browser-fixture-view?raw=calibrated&lang=en`,
  );
  expect((await rawExport.body()).toString('utf8')).toContain('隔离浏览器夹具中的正文');
  const invalidEmpty = await page.request.get(`${baseURL}/view/browser-fixture-view?lang=`);
  const invalidLanguage = await page.request.get(`${baseURL}/view/browser-fixture-view?lang=fr`);
  expect(invalidEmpty.status()).toBe(400);
  expect(invalidLanguage.status()).toBe(400);
  const englishCatalog = await page.request.get(`${baseURL}/i18n.js?lang=en`);
  expect(await englishCatalog.text()).toContain('window.__VTA_LANG__ = "en"');

  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const screenshotPath = resolve(process.cwd(), '../data/vta-share-i18n-261023-mobile.png');
  mkdirSync(dirname(screenshotPath), { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.getByRole('link', { name: '中文' }).click();
  await expect(page).toHaveURL(/source=share&lang=zh-CN$/);
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.locator('#calibrated-content-block')).toContainText('隔离浏览器夹具中的正文');
});

test('history processing and failed badges use the active catalog', async ({ page, request }) => {
  await setLanguage(request, 'en');
  await page.goto('/static/history.html');
  await page.locator('#apiKeyInput').fill('browser-fixture-token');
  await page.locator('#historyQueryBtn').click();
  await expect(page.locator('.task-status-badge.status-processing')).toHaveText('Processing');
  await expect(page.locator('.task-status-badge.status-failed')).toHaveText('Failed');

  await setLanguage(request, 'zh-CN');
  await page.reload();
  await page.locator('#apiKeyInput').fill('browser-fixture-token');
  await page.locator('#historyQueryBtn').click();
  await expect(page.locator('.task-status-badge.status-processing')).toHaveText('处理中');
  await expect(page.locator('.task-status-badge.status-failed')).toHaveText('失败');
});
