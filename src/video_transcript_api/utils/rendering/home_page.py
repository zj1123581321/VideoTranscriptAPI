"""Landing-page HTML rendered from the C1 catalog.

Both zh-CN and en go through ``t()``; there is no language-specific branch
that returns a frozen HTML constant.
"""

from ...i18n import get_language, t

_HOME_SKELETON = """\
<!DOCTYPE html>
<html lang="@@LANG@@">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VideoTranscriptAPI</title>
    <meta name="description" content="Multi-platform video transcription with AI-powered proofreading and summarization. Supports YouTube, Bilibili, Douyin, Xiaohongshu and more.">
    <meta name="theme-color" content="#667eea">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
            line-height: 1.6;
            color: #333;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }
        .card {
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.15);
            padding: 48px;
            max-width: 560px;
            width: 100%;
            text-align: center;
        }
        .logo { font-size: 3rem; margin-bottom: 16px; }
        h1 { font-size: 1.8rem; margin-bottom: 8px; font-weight: 700; }
        .subtitle { color: #6b7280; margin-bottom: 32px; font-size: 0.95rem; }
        .features {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 32px;
            text-align: left;
        }
        .feature {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 14px 16px;
            font-size: 0.88rem;
            color: #374151;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .feature-icon { font-size: 1.2rem; flex-shrink: 0; }
        .cta {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            text-decoration: none;
            padding: 12px 32px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 500;
            transition: opacity 0.2s, transform 0.2s;
        }
        .cta:hover { opacity: 0.9; transform: translateY(-1px); }
        .footer {
            margin-top: 24px;
            font-size: 0.78rem;
            color: #9ca3af;
            opacity: 0.8;
        }
        .footer a { color: #9ca3af; text-decoration: none; }
        .footer a:hover { text-decoration: underline; }
        @media (max-width: 480px) {
            .card { padding: 32px 24px; }
            .features { grid-template-columns: 1fr; }
            h1 { font-size: 1.5rem; }
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">🎬</div>
        <h1>VideoTranscriptAPI</h1>
        <p class="subtitle">@@SUBTITLE@@</p>
        <div class="features">
            <div class="feature"><span class="feature-icon">🌐</span>@@FEATURE_PLATFORMS@@</div>
            <div class="feature"><span class="feature-icon">🎙️</span>@@FEATURE_ASR@@</div>
            <div class="feature"><span class="feature-icon">📝</span>@@FEATURE_SUMMARY@@</div>
            <div class="feature"><span class="feature-icon">👀</span>@@FEATURE_VIEW@@</div>
            <div class="feature"><span class="feature-icon">📋</span>@@FEATURE_HISTORY@@</div>
        </div>
        <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
            <a class="cta" href="/add_task_by_web">@@CTA_SUBMIT@@</a>
            <a class="cta" href="/static/history.html" style="background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);">@@CTA_HISTORY@@</a>
        </div>
        <p style="margin-top: 16px; font-size: 0.85rem;">
            <a href="https://mp.weixin.qq.com/s/w8VnWJcUp5VkD5J-fYCUrg" target="_blank" rel="noopener" style="color: #667eea; text-decoration: none;">@@STORY_LINK@@</a>
        </p>
        <p class="footer">
            Powered by <a href="https://github.com/zlxlabs/VideoTranscriptAPI" target="_blank" rel="noopener">VideoTranscriptAPI</a>
            · Open Source ·
            <a href="https://github.com/zlxlabs/VideoTranscriptAPI" target="_blank" rel="noopener">☆ Star on GitHub</a>
        </p>
    </div>
</body>
</html>
"""


def render_home_html() -> str:
    """Return the landing page HTML for the current UI language."""
    html = _HOME_SKELETON
    replacements = (
        ("@@LANG@@", get_language()),
        ("@@SUBTITLE@@", t("web.home.subtitle")),
        ("@@FEATURE_PLATFORMS@@", t("web.home.feature_platforms")),
        ("@@FEATURE_ASR@@", t("web.home.feature_asr")),
        ("@@FEATURE_SUMMARY@@", t("web.home.feature_summary")),
        ("@@FEATURE_VIEW@@", t("web.home.feature_view")),
        ("@@FEATURE_HISTORY@@", t("web.home.feature_history")),
        ("@@CTA_SUBMIT@@", t("web.home.cta_submit")),
        ("@@CTA_HISTORY@@", t("web.home.cta_history")),
        ("@@STORY_LINK@@", t("web.home.story_link")),
    )
    for token, value in replacements:
        html = html.replace(token, value, 1)
    return html
