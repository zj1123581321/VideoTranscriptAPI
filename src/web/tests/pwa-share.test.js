// Tests for the share-target prefill pure functions (PWA T7).
//
// Contract (design: docs/designs/pwa.md E4 + S3-1):
// - share_target is GET /add_task_by_web?url=&title=&text=
// - Bilibili/Douyin apps usually put the link inside `text`
//   ("【标题】 https://b23.tv/xxx"), so fall back to extracting the first
//   URL from text when `url` is empty;
// - three validation gates: scheme whitelist (http/https only, reject
//   javascript:), plain value assignment (glue side, never innerHTML),
//   overlong truncation.

import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { extractFirstUrl, sanitizeSharedUrl, getSharedUrl, MAX_SHARED_URL_LENGTH } =
  require('../static/js/pwa-share.js');

describe('extractFirstUrl', () => {
  it('extracts the first URL from mixed share text', () => {
    const text = '【时长】 这个视频讲 AI https://b23.tv/abc123 复制此链接，打开抖音';
    expect(extractFirstUrl(text)).toBe('https://b23.tv/abc123');
  });

  it('returns null when no URL is present', () => {
    expect(extractFirstUrl('纯文本没有链接')).toBeNull();
    expect(extractFirstUrl('')).toBeNull();
    expect(extractFirstUrl(null)).toBeNull();
  });

  it('picks the first of several URLs', () => {
    expect(extractFirstUrl('a https://a.com/1 b https://b.com/2')).toBe('https://a.com/1');
  });
});

describe('sanitizeSharedUrl', () => {
  it('accepts http and https', () => {
    expect(sanitizeSharedUrl('https://b23.tv/abc')).toBe('https://b23.tv/abc');
    expect(sanitizeSharedUrl('http://example.com/v')).toBe('http://example.com/v');
  });

  it('rejects non-http(s) schemes and junk', () => {
    expect(sanitizeSharedUrl('javascript:alert(1)')).toBeNull();
    expect(sanitizeSharedUrl('ftp://example.com/x')).toBeNull();
    expect(sanitizeSharedUrl('notaurl')).toBeNull();
    expect(sanitizeSharedUrl('')).toBeNull();
    expect(sanitizeSharedUrl(null)).toBeNull();
  });

  it('trims surrounding whitespace', () => {
    expect(sanitizeSharedUrl('  https://b23.tv/abc  ')).toBe('https://b23.tv/abc');
  });

  it('truncates overlong URLs', () => {
    const long = 'https://example.com/' + 'a'.repeat(MAX_SHARED_URL_LENGTH * 2);
    const result = sanitizeSharedUrl(long);
    expect(result).not.toBeNull();
    expect(result.length).toBe(MAX_SHARED_URL_LENGTH);
  });
});

describe('getSharedUrl', () => {
  it('prefers the url param when valid', () => {
    expect(getSharedUrl('?url=https%3A%2F%2Fb23.tv%2Fabc&title=t')).toBe('https://b23.tv/abc');
  });

  it('falls back to extracting from text (Bilibili/Douyin style)', () => {
    const text = encodeURIComponent('【标题】 https://b23.tv/xyz789 复制此链接');
    expect(getSharedUrl(`?title=t&text=${text}`)).toBe('https://b23.tv/xyz789');
  });

  it('rejects a javascript: url param even when text has a good link', () => {
    // a poisoned url param must not win over text extraction
    const text = encodeURIComponent('看视频 https://b23.tv/safe');
    expect(getSharedUrl(`?url=${encodeURIComponent('javascript:alert(1)')}&text=${text}`))
      .toBe('https://b23.tv/safe');
  });

  it('returns null when nothing usable is shared', () => {
    expect(getSharedUrl('?title=only-a-title')).toBeNull();
    expect(getSharedUrl('')).toBeNull();
    expect(getSharedUrl('?url=javascript%3Aalert(1)')).toBeNull();
  });
});
