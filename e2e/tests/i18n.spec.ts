import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { resetBackend } from '../reset-backend';

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

  await page.goto('/static/history.html');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: '任务历史' })).toBeVisible();

  await page.goto('/view/browser-fixture-view');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: /内容总结/ })).toBeVisible();
});

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

  await page.goto('/view/processing');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Transcription in progress/ })).toBeVisible();

  await page.goto('/view/failed');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Something went wrong/ })).toBeVisible();

  await page.goto('/view/cleaned');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: /Content cleaned up/ })).toBeVisible();
});
