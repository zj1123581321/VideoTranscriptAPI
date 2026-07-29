/*
 * Share-target prefill pure functions (design: docs/designs/pwa.md T7 / E4).
 *
 * The manifest share_target is GET /add_task_by_web?url=&title=&text=.
 * Bilibili/Douyin apps usually leave `url` empty and stuff the link into
 * `text` ("【标题】 https://b23.tv/xxx"), so the resolver falls back to
 * extracting the first URL from `text`.
 *
 * S3-1 validation gates:
 *   1. scheme whitelist: http/https only (javascript: etc. rejected);
 *   2. glue assigns via input.value only (never innerHTML) -- see pwa.js;
 *   3. overlong URLs are truncated.
 *
 * No DOM dependencies: loadable as a classic script in the browser
 * (defines window.PWAShare) and via createRequire under vitest.
 */
(function (global) {
  'use strict';

  // Hard cap for a prefilled URL (shares occasionally carry huge junk params).
  var MAX_SHARED_URL_LENGTH = 2000;

  // First http(s) URL in arbitrary share text; stops at whitespace and
  // common CJK/closing punctuation that apps append after the link.
  var URL_RE = /https?:\/\/[^\s"'<>，。；！？）】》]+/i;

  // Trailing punctuation the URL_RE match swallows (same charset as
  // app.js URLExtractor.cleanURL, Codex R3-4).
  var TRAILING_PUNCT_RE = /[.,;:!?)\]}>'"。，；：！？）】》'"]+$/;

  /**
   * Extract the first http(s) URL from arbitrary text.
   *
   * @param {?string} text Raw share text.
   * @returns {?string} The first URL with trailing punctuation stripped, or null.
   */
  function extractFirstUrl(text) {
    if (!text || typeof text !== 'string') {
      return null;
    }
    var match = text.match(URL_RE);
    if (!match) {
      return null;
    }
    var url = match[0].replace(TRAILING_PUNCT_RE, '');
    return url || null;
  }

  /**
   * Validate and normalize a shared URL candidate.
   *
   * @param {?string} candidate Raw URL candidate.
   * @returns {?string} Trimmed, scheme-checked, truncated URL, or null.
   */
  function sanitizeSharedUrl(candidate) {
    if (!candidate || typeof candidate !== 'string') {
      return null;
    }
    var url = candidate.trim();
    if (!url) {
      return null;
    }
    var parsed;
    try {
      parsed = new URL(url);
    } catch (e) {
      return null;
    }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    // 返回规范化结果（Codex R10-1）：混合大小写协议（HTTPS://...）会被
    // app.js cleanURL 的大小写敏感判断误拼成 https://HTTPS://...；
    // parsed.href 顺带归一化 Unicode 域名（punycode）与默认端口
    url = parsed.href;
    if (url.length > MAX_SHARED_URL_LENGTH) {
      url = url.slice(0, MAX_SHARED_URL_LENGTH);
    }
    return url;
  }

  /**
   * Resolve the URL to prefill from a share-target query string.
   *
   * @param {string} search e.g. location.search ("?url=...&title=...&text=...").
   * @returns {?string} Sanitized URL to prefill, or null (stay silent).
   */
  function getSharedUrl(search) {
    var params = new URLSearchParams(search || '');
    var fromUrl = sanitizeSharedUrl(params.get('url'));
    if (fromUrl) {
      return fromUrl;
    }
    // Bilibili/Douyin path: the link hides inside the free-form text.
    return sanitizeSharedUrl(extractFirstUrl(params.get('text')));
  }

  var api = {
    MAX_SHARED_URL_LENGTH: MAX_SHARED_URL_LENGTH,
    extractFirstUrl: extractFirstUrl,
    sanitizeSharedUrl: sanitizeSharedUrl,
    getSharedUrl: getSharedUrl,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.PWAShare = api;
  }
})(typeof self !== 'undefined' ? self : (typeof globalThis !== 'undefined' ? globalThis : null));
