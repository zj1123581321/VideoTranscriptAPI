# 实施报告：公开分享页中英双语

本次按已批准设计实现公开分享页 UI 语言切换。访客可在中文、English 间切换；原转录/总结正文保持原文。显式语言沿公开 HTML、raw/page 导出、i18n 脚本和 OG 图片传递，错误语言返回 400。站点默认语言、Prompt 任务含义和用户自定义 Prompt 不变。

- H0：`fc2d8fd7628ccebfc955025e0b6eb7b1cff359e5`。
- H1：`ef69bc5b25e10173215173fe30ce55e85c2620f1`。
- 最终补测与审查记录在本次提交；最终 HEAD 由提交输出确认。
- H1 发现的 API 闭集错误词条与 OG URL 断言问题已在 H1 修复；没有改 API 错误生成器或新增生产抽象。
- 显式 `lang` 的共享缓存响应为 `private, no-store`；未改 CDN/代理配置、持久化数据或 schema。

## 验证记录

- `uv run --frozen pytest -q tests/unit/i18n/test_i18n.py tests/unit/test_deep_read_prompt_config.py`：20 passed。
- 扩展 i18n/deep-read/cache/route 窄测：通过；H1 修复的 3 个原失败节点 + catalog/deep-read：24 passed。
- `npm run test:web`：188 passed。
- `npm run test:browser`：33 passed；包含真实 Chromium、复制 payload、raw/page 文件字节和响应语言切换。
- H1 完整 `make test`（代码提交 H1）：退出 2，唯一失败是 `tests/unit/web/test_frontend_nav.py` 的旧 URL 断言及缺少 `ui_language` fixture。修正后最终窄测 44 passed；没有因纯测试 fixture 更新再跑完整本地套件。详见 `/tmp/vta-share-i18n-261023-h1-make-test-summary.txt`。
- H0 完整套件运行在约 21% 时收到 SIGINT，退出 130；不计为完整验证。
- 隔离 worktree 红验：将 `/view` 显式语言响应缓存头变成 `public, max-age=3600` 后，真实 route 集成用例在 raw 响应头断言失败：期望 `private, no-store`，实际 `public, max-age=3600`。
- H2 OCR 续修：旧模板 gate 下真实 resolver 的 processing/failed/file_cleaned 三状态用例均在切换链接断言红；修后 route、Content-Type/原始 UTF-8 字节及静态 i18n 路由 `17 passed`，Chromium 相关语言切换用例 `1 passed`。
- 最终提交后由 CI 对最终 HEAD 执行完整套件；未在本轮合并或部署。

### 新增测试判据

- `tests/unit/i18n/test_i18n.py`：改坏 `src/video_transcript_api/i18n/__init__.py` 的语言解析/请求局部翻译会破坏语言白名单与隔离断言；对应设计：仅允许 `zh-CN|en`，访客 UI 语言不得改变站点 Prompt 语言。
- `tests/unit/test_deep_read_prompt_config.py`：改坏 `src/video_transcript_api/api/context.py` 的内置默认 label/template 选择会破坏中英默认 Prompt 断言；对应设计：站点语言控制任务指令，自定义 preset 原样保留。
- `tests/unit/test_static_asset_versioning.py`：改坏 `src/video_transcript_api/api/app.py` 的 `/i18n.js` 显式语言解析、UTF-8 Content-Type 或正文会破坏真实响应断言；对应设计：非法/空语言 400，错误消息由站点语言编码。
- `tests/integration/test_local_upload_lifecycle.py`：旧 `view_token` gate 已使真实 resolver 的三种状态页切换链接断言红；同一 HTTP 契约检查原始状态回读、切换 query、invalid view/OG 的 Content-Type 与 UTF-8 字节，以及 raw 缓存头变异红；对应设计：状态页可切换，错误消息字节正确。
- `tests/og_card/test_view_meta.py`：改坏 `src/video_transcript_api/api/routes/views.py` 的 OG image URL 语言传播会破坏 `lang=zh-CN` 查询断言；对应设计：OG meta 与公开页面同语。
- `tests/unit/web/test_frontend_nav.py`：改坏 `src/web/templates/transcript.html` 的 raw URL 语言参数会破坏复制/导出 URL 断言；对应设计：模板链接保留当前 UI 语言。
- `e2e/tests/i18n.spec.ts`：改坏 `src/video_transcript_api/api/routes/views.py` 的请求语言切换或客户端复制 payload 会破坏真实浏览器可见断言；对应设计：切换页、按钮和提示同语且复制最终 URL。
- `e2e/tests/pages.spec.ts`：改坏 `src/video_transcript_api/api/routes/views.py` 的 page 导出语言传播会破坏浏览器 page 查询断言；对应设计：`?page` 导出随 `lang`。
