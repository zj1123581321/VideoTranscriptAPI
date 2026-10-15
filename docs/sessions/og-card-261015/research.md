# X/Twitter 分享卡片（og:image）改造仓内现状调研报告

本文档针对分享页在 X/Twitter 上展示信息密集型大图卡片的设计，收集并梳理仓内代码现状与事实清单。

---

## 1. 分享页入口

- **分享链接渲染路由与模板**：
  - 路由入口：`@router.get("/view/{view_token}")`，位于 [`src/video_transcript_api/api/routes/views.py:1446-1537`](src/video_transcript_api/api/routes/views.py#L1446-L1537)。
  - 正常完成任务渲染模板：[`src/web/templates/transcript.html:1523-1526`](src/video_transcript_api/api/routes/views.py#L1523-L1526)，继承自 [`src/web/templates/base.html`](src/web/templates/base.html)。
  - 其他状态模板：`processing.html`（处理中，[`views.py:1497-1504`](src/video_transcript_api/api/routes/views.py#L1497-L1504)）、`error.html`（失败，[`views.py:1506-1513`](src/video_transcript_api/api/routes/views.py#L1506-L1513)）、`cleaned.html`（文件已清理，[`views.py:1515-1518`](src/video_transcript_api/api/routes/views.py#L1515-L1518)）。
  - 单页导出分支（爬虫友好模式）：`?page={export_type}` 走 `handle_page_export`（[`views.py:489-591`](src/video_transcript_api/api/routes/views.py#L489-L591)），由 `_build_page_html`（[`views.py:356-486`](src/video_transcript_api/api/routes/views.py#L356-L486)）动态拼接 HTML 字符串，不经过 Jinja2 模板。
  - 纯文本导出分支：`?raw={export_type}` 走 `handle_raw_export`（[`views.py:601-787`](src/video_transcript_api/api/routes/views.py#L601-L787)），返回带 YAML front matter 的纯文本。

- **所有输出 `og:` meta 的位置与对应 URL 形态**：
  1. [`src/web/templates/base.html:16-20`](src/web/templates/base.html#L16-L20)：
     ```html
     <meta property="og:title" content="{% block og_title %}{% endblock %}">
     <meta property="og:description" content="{% block og_description %}多平台视频转录与 AI 校对服务{% endblock %}">
     <meta property="og:type" content="article">
     <meta property="og:locale" content="zh_CN">
     <meta property="og:site_name" content="Video Transcript API">
     ```
     对应 URL 形态：标准分享页 URL `https://sum.zlxlabs.com/view/{view_token}`（无 raw/page query 参数）。
  2. [`src/video_transcript_api/api/routes/views.py:405-409`](src/video_transcript_api/api/routes/views.py#L405-L409)（在 `_build_page_html` 中）：
     ```python
     <meta property="og:title" content="{page_title}">
     <meta property="og:description" content="{og_desc}">
     <meta property="og:type" content="article">
     <meta property="og:locale" content="zh_CN">
     <meta property="og:site_name" content="Video Transcript API">
     ```
     对应 URL 形态：页面导出模式 URL `https://sum.zlxlabs.com/view/{view_token}?page={export_type}`（`export_type` 可为 `calibrated`, `summary`, `notes`, `transcript`）。

- **`og_title`/`og_description` block 在子模板中的重写与数据来源**：
  - 子模板覆盖情况：在所有继承 `base.html` 的子模板（`transcript.html`, `processing.html`, `error.html`, `cleaned.html`）中，**仅** [`src/web/templates/transcript.html:5-6`](src/web/templates/transcript.html#L5-L6) 覆盖了这两个 block：
    ```html
    {% block og_title %}{{ title or "视频转录" }} - 视频转录查看器{% endblock %}
    {% block og_description %}{{ title or "视频转录" }} 的转录校对结果{% endblock %}
    ```
  - 取值字段：来自模板 context 中的 `title` 字段（在 [`views.py:1525`](src/video_transcript_api/api/routes/views.py#L1525) 由 `**view_data` 传入）。
  - 其他子模板（`cleaned.html`, `error.html`, `processing.html`）未定义这两个 block，直接 fallback 到 `base.html:16-17` 的默认值（`og:title` 为空，`og:description` 固定为 `"多平台视频转录与 AI 校对服务"`）。

- **站点对外绝对地址（base URL）配置项**：
  - 配置项：`config["web"]["base_url"]`（缺省 fallback 为 `"http://localhost:8000"`，线上配置为 `"https://sum.zlxlabs.com"`）。
  - 代码位置：[`src/video_transcript_api/utils/rendering/markdown_renderer.py:370-377`](src/video_transcript_api/utils/rendering/markdown_renderer.py#L370-L377) 中的 `get_base_url()` 函数。通知与终端状态链接均调用此函数拼接（[`src/video_transcript_api/api/services/terminal_status.py:515`](src/video_transcript_api/api/services/terminal_status.py#L515)）。

---

## 2. 总结生成链路

- **LLM 总结调用入口与 Prompt**：
  - Prompt 模板定义：[`src/video_transcript_api/llm/prompts/__init__.py`](src/video_transcript_api/llm/prompts/__init__.py)。
    - 单发言人 System Prompt：`SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER`（[`prompts/__init__.py:159-209`](src/video_transcript_api/llm/prompts/__init__.py#L159-L209)）。
    - 多发言人 System Prompt：`SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER`（[`prompts/__init__.py:211-257`](src/video_transcript_api/llm/prompts/__init__.py#L211-L257)）。
    - 用户 Prompt 构建：`build_summary_user_prompt(...)`（[`prompts/__init__.py:260-313`](src/video_transcript_api/llm/prompts/__init__.py#L260-L313)）。
  - 执行处理器与调用函数：
    - `SummaryProcessor.process` 与 `_call_summary_llm` -> `LLMClient.call`（[`src/video_transcript_api/llm/processors/summary_processor.py:72-223, 269-285`](src/video_transcript_api/llm/processors/summary_processor.py#L72-L223)）。
    - 上层编排调用：`LLMCoordinator._generate_summary_if_needed`（[`src/video_transcript_api/llm/coordinator.py:598-658`](src/video_transcript_api/llm/coordinator.py#L598-L658)）。
  - 输出形式：**纯 Markdown 文本**，**不是**结构化 JSON，**未**使用 JSON Schema 或 response_format。系统提示词中规范要求按 Markdown 语法输出 `### 1. 概述（Overview）`、`### 2. 主题详述`、`### 3. 核心观点与洞察`。
  - 模型配置项：
    - 基础模型：`config["llm"]["summary_model"]`（读取至 `LLMConfig.summary_model`，[`src/video_transcript_api/llm/core/config.py:209`](src/video_transcript_api/llm/core/config.py#L209)）。
    - 推理强度：`config["llm"]["summary_reasoning_effort"]`（读取至 `LLMConfig.summary_reasoning_effort`，[`config.py:210`](src/video_transcript_api/llm/core/config.py#L210)）。
    - 动态风控覆盖：若风控规则触发，可从 `selected_models.get("summary_model")` 覆盖默认模型（[`summary_processor.py:116`](src/video_transcript_api/llm/processors/summary_processor.py#L116)）。

- **持久化位置与字段布局**：
  - 文件系统：缓存目录下的 `{cache_dir}/llm_summary.txt`（[`src/video_transcript_api/api/services/llm_ops.py:2481`](src/video_transcript_api/api/services/llm_ops.py#L2481)）。
  - 数据库状态字段：在 SQLite `task_status` 表的 `summary_status` 列记录状态枚举（`GENERATED`, `SKIPPED_SHORT`, `FAILED` 等，[`src/video_transcript_api/cache/cache_manager.py:528`](src/video_transcript_api/cache/cache_manager.py#L528)）。
  - 总结正文**未**存入 SQLite 表，页面展示时通过 `ViewTokenResolver` 从 `{cache_dir}/llm_summary.txt` 动态读取（[`src/video_transcript_api/api/routes/views.py:1276`](src/video_transcript_api/api/routes/views.py#L1276)）。

- **若让同一次总结调用额外输出 `share_headline` 与 `key_points` 的最小改动点**：
  - 最小改动在 System Prompt 与 `SummaryProcessor`：在 `prompts/__init__.py` 的总结 System Prompt 结尾增加格式指令，要求在最上方输出固定的 YAML Front Matter 或特定标记块（如 `<share_card>\ntitle: ...\npoints:\n- ...\n</share_card>`），在 `SummaryProcessor.process`（[`summary_processor.py:173`](src/video_transcript_api/llm/processors/summary_processor.py#L173)）解析提取并存入 `SummaryResult`，同时剥离该标记以保留干净的 Markdown 存入 `llm_summary.txt`，结构化字段落盘为 `llm_share_card.json`。
  - 不建议将整个总结调用切换为结构化 JSON Schema，因为现有篇幅预算控制（`SummaryBudget`）、截断重试和 Markdown 渲染高度依赖自由流式文本。

- **已存在的结构化字段复用评估**：
  - `llm_chapters.json`（[`src/video_transcript_api/llm/processors/chapters_processor.py:126-157`](src/video_transcript_api/llm/processors/chapters_processor.py#L126-L157)）：包含每个章节的 `title` 和 `gist`（一句话要点），若视频成功分章，理论上可复用前 3 章的 `gist` 作为要点。但当任务无可用时间轴或分段不足时，chapters 会判定为 `SKIPPED_NO_TIMELINE`（[`chapters_processor.py:1051`](src/video_transcript_api/llm/processors/chapters_processor.py#L1051)），因此不能作为全平台保底依赖。
  - `llm_notes.txt` / `llm_notes.json`（[`src/video_transcript_api/llm/processors/notes_processor.py:419-450`](src/video_transcript_api/llm/processors/notes_processor.py#L419-L450)）：产物为逐章深度长文 Markdown，无短精炼要点字段。

---

## 3. 元数据可得性

- **每个任务落盘数据可得字段**：
  - SQLite `video_cache` 表（[`src/video_transcript_api/cache/cache_manager.py:304-317, 1261-1265`](src/video_transcript_api/cache/cache_manager.py#L304-L317)）：
    - `platform`（平台名）
    - `media_id`（平台唯一 ID）
    - `url`（原始链接）
    - `title`（视频标题）
    - `author`（作者/频道）
    - `description`（视频原始简介）
    - `use_speaker_recognition`（说话人识别标志）
    - `files_loc`（文件存储相对路径）
    - `created_at`、`updated_at`（入库与更新时间戳）
  - SQLite `task_status` 表（[`cache_manager.py:322-344`](src/video_transcript_api/cache/cache_manager.py#L322-L344)）：包含 `task_id`, `view_token`, `status`, `progress`, `calibration_status`, `summary_status`, `chapters_status` 等。
  - 说话人名单：
    - 若开启说话人识别（`use_speaker_recognition=True`），缓存目录下存在 `speaker_mapping.json`（[`cache_manager.py:1658, 1717-1725`](src/video_transcript_api/cache/cache_manager.py#L1658)），包含 `speakers` 列表及 `result.speaker_mapping` 映射字典。单说话人或未开启识别时无此文件。

- **逐平台元数据（封面/缩略图 URL、时长、发布日期）现状**：
  - **YouTube**（[`src/video_transcript_api/downloaders/youtube.py:532-541`](src/video_transcript_api/downloaders/youtube.py#L532-L541) / [`youtube_api_client.py:227-231`](src/video_transcript_api/downloaders/youtube_api_client.py#L227-L231)）：
    - 内存中：API 客户端返回 `duration`, `upload_date`, `thumbnail`，存入 `VideoMetadata.extra`。
    - 落盘状态：`cache_manager.save_cache` 时只取 `title, author, description`，`thumbnail`、`duration`、`upload_date` **均未落盘**。
  - **Bilibili**（[`src/video_transcript_api/downloaders/bilibili.py:211-218, 298, 880-920`](src/video_transcript_api/downloaders/bilibili.py#L211-L218)）：
    - 内存中：官方 API 提取了 `title`, `description`, `author`, `author_id`, `duration`, `pubdate`；官方 API 返回的封面 `data.pic` **未被提取**，下载参数带 `--skip-cover`。
    - 落盘状态：封面、时长、发布日期**均未落盘**。
  - **抖音 (Douyin)**（[`src/video_transcript_api/downloaders/douyin.py:208-254`](src/video_transcript_api/downloaders/douyin.py#L208-L254)）：
    - 内存中：仅有 `video_title`, `author`, `description`；`origin_cover` 仅用于下载探测，最终返回无封面、无时长、无发布日期。
    - 落盘状态：无封面、无时长、无发布日期。
  - **小宇宙 (Xiaoyuzhou)**（[`src/video_transcript_api/downloaders/xiaoyuzhou.py:100-180`](src/video_transcript_api/downloaders/xiaoyuzhou.py#L100-L180)）：
    - 内存中：HTML 解析仅提取 `video_title`, `author`, `description`, `audio_url`，未解析 `og:image`，无时长、无发布日期。
    - 落盘状态：无封面、无时长、无发布日期。
  - **X / Twitter Space**（[`src/video_transcript_api/downloaders/media_resolver.py:186-217`](src/video_transcript_api/downloaders/media_resolver.py#L186-L217)）：
    - 内存中：解析服务返回 `title`, `author_name`, `description`, `duration`，未提取封面。
    - 落盘状态：无封面、无时长持久化。
  - **本地上传 (Local Upload)**（[`src/video_transcript_api/api/routes/uploads.py:343`](src/video_transcript_api/api/routes/uploads.py#L343)）：
    - 仅有 `title`, `filename`, `byte_size`，无作者、无封面。

- **封面 URL 是否已持久化**：
  - **确定事实：封面 URL 从未持久化到任何数据库表或磁盘文件中。** 即使在 YouTube 下载器中出现，也仅在内存 `VideoMetadata.extra["thumbnail"]` 中暂存，任务完成后即丢失。

---

## 4. 任务完成生命周期

- **任务完成（进入终态）的代码位置**：
  - 终态写入位置：[`src/video_transcript_api/api/services/llm_ops.py:839-864`](src/video_transcript_api/api/services/llm_ops.py#L839-L864)（在 `_handle_llm_task` 内部）。
  - 执行步骤：
    1. 产物落盘：`_save_llm_results`（[`llm_ops.py:2220-2515`](src/video_transcript_api/api/services/llm_ops.py#L2220-L2515)）将 `llm_summary.txt`、`llm_calibrated.txt`、`llm_chapters.json` 等写入缓存目录。
    2. CAS 写终态：`finalize_terminal_status_and_notify`（[`llm_ops.py:839`](src/video_transcript_api/api/services/llm_ops.py#L839)）原子更新数据库 `task_status` 为 `success` 并归档快照。
    3. 发送终态通知：`deliver_terminal_notification`（[`llm_ops.py:878-888`](src/video_transcript_api/api/services/llm_ops.py#L878-L888)）向微信/企微发送带 `view_url` 的完成消息。

- **适合挂「生成分享图」的钩子点**：
  - 主动同步钩子：挂在 `_save_llm_results` 成功之后、`deliver_terminal_notification` 之前（[`llm_ops.py:863-864`](src/video_transcript_api/api/services/llm_ops.py#L863-L864)）。优势是通知送达时分享图已经生成完毕，通知卡片甚至可直接引用该图。
  - 惰性按需钩子：在 `GET /og/{view_token}.png` 路由层检测，若本地图片缓存不存在则实时读取 `cache_data` 渲染生成并落盘。

- **重新校准/重新总结时的刷新路径**：
  - 入口路由：POST `/api/recalibrate` 与 POST `/api/resummarize`（[`src/video_transcript_api/api/routes/tasks.py:620-750, 920-1050`](src/video_transcript_api/api/routes/tasks.py#L620-L750)）。
  - 执行流：
    1. 鉴权通过后由 `ViewTokenResolver.get_cache_by_view_token` 取原缓存。
    2. 生成新 `task_id`，复用原 `view_token` 插入 `task_status`（status='processing'）。
    3. 推入 `llm_queue` 队列。
    4. 工作协程 `process_llm_queue` 消费并调用 `_handle_llm_task`。
    5. 完成时在 `_save_llm_results` 处覆盖写 `llm_summary.txt`，随后更新终态。
    6. 若在此挂钩重新生成分享图，将自然覆盖旧的分享图缓存。

---

## 5. 静态资源与依赖

- **静态文件服务与路由规范**：
  - 静态目录服务：FastAPI `app.mount("/static", NoCacheStaticFiles(directory=str(static_dir)), name="static")`，位于 [`src/video_transcript_api/api/app.py:327`](src/video_transcript_api/api/app.py#L327)。指向 `src/web/static`，响应统一带 `Cache-Control: no-cache`。
  - 特殊单文件服务：根路径如 `/sw.js`（[`app.py:334`](src/video_transcript_api/api/app.py#L334)）、`/robots.txt`（[`src/video_transcript_api/api/routes/views.py:66`](src/video_transcript_api/api/routes/views.py#L66)）均使用 FastAPI 独立路由返回 `FileResponse` 或 `Response`。
  - 新增 `/og/<id>.png` 惯例写法：在 [`src/video_transcript_api/api/routes/views.py`](src/video_transcript_api/api/routes/views.py) 中定义 `@router.get("/og/{view_token}.png")`，返回 `FileResponse(image_path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})`。

- **依赖清单中 Pillow 的现状**：
  - 在 [`pyproject.toml:51`](pyproject.toml#L51) 中包含 `"pillow>=12.3.0"`，但**仅位于 `[dependency-groups].dev`**。
  - 生产依赖 `[project].dependencies`（[`pyproject.toml:6-39`](pyproject.toml#L6-L39)）中**没有 Pillow**！

- **Dockerfile / 部署基础镜像与 CJK 字体**：
  - 基础镜像：`FROM python:3.11-slim`（[`docker/Dockerfile:1`](docker/Dockerfile#L1)）。
  - Python 依赖安装命令：`RUN uv sync --frozen --no-dev`（[`docker/Dockerfile:41`](docker/Dockerfile#L41)）。因为带有 `--no-dev`，若不将 `pillow` 移入生产依赖，容器构建时将不会安装 Pillow！
  - CJK 字体：Dockerfile 的 `apt-get` 仅安装了 `curl`, `unzip`, `git`, `libjemalloc2`（[`docker/Dockerfile:13-18`](docker/Dockerfile#L13-L18)），**镜像内完全没有安装任何中文字体包（无 fonts-noto-cjk，无 fontconfig）**。
- **部署方式**：
  - Docker Compose 容器化部署（[`docker/docker-compose.deploy.yml`](docker/docker-compose.deploy.yml)）。
  - 宿主机端口 8200 映射至容器 8000，挂载 `./config` 与 `./data` 卷，启动命令 `uv run python main.py --start`（[`docker/Dockerfile:67`](docker/Dockerfile#L67)）。

---

## 6. 抓取可达性

- **分享页鉴权情况**：
  - 路由 `@router.get("/view/{view_token}")`（[`src/video_transcript_api/api/routes/views.py:1446`](src/video_transcript_api/api/routes/views.py#L1446)）**无需任何鉴权**。
  - 无 Cookie、Authorization Header 或 API Key 校验依赖，`view_token` 为公开能力凭证，任何客户端持有该链接均可直接访问。

- **`robots.txt` 存在性及内容**：
  - 路由存在：`@router.get("/robots.txt")`（[`src/video_transcript_api/api/routes/views.py:66-71`](src/video_transcript_api/api/routes/views.py#L66-L71)）。
  - 内容定义（[`views.py:47-53`](src/video_transcript_api/api/routes/views.py#L47-L53)）：
    ```
    User-agent: *
    Allow: /
    Disallow: /api/
    Disallow: /static/
    Sitemap: {base_url}/sitemap.xml
    ```
    公开允许爬虫访问根路径与分享页 `/view/...`。
  - 注：虽在 [`base.html:6`](src/web/templates/base.html#L6) 中有 `<meta name="robots" content="noindex">`，但 Twitterbot 等社交媒体爬虫抓取 `og:` meta 生成卡片不受搜索引擎 `noindex` 限制。

- **UA 拦截中间件排查**：
  - 经全面排查，仓内中间件 `@app.middleware("http")`（[`src/video_transcript_api/api/app.py:346-370`](src/video_transcript_api/api/app.py#L346-L370)）仅对 `/view/` 和 `/export/` 记录调试日志（打印 UA、CF-IP 等），**没有拦截 Twitterbot、facebookexternalhit 或任何其他爬虫 UA**，全部直接放行。

---

## 7. 测试与 CI

- **分享页/views 现有测试文件路径与写法**：
  - 核心测试路径：
    - `tests/unit/test_detailed_notes_view.py`
    - `tests/unit/test_views_calibration_stats.py`
    - `tests/unit/test_views_deep_read_prompt.py`
    - `tests/unit/test_views_export_path.py`
    - `tests/unit/test_view_token_resolver.py`
    - `tests/integration/test_notes_export.py`
    - `tests/integration/test_local_upload_lifecycle.py`
  - 测试写法模式：
    - 使用 FastAPI 的 `starlette.testclient.TestClient(app)` 或直接通过 `ViewTokenResolver(cache_manager)` 测试。
    - 使用 pytest 的 `tmp_path` 作为临时 SQLite 与缓存目录，构造模拟的 `llm_summary.txt` 等产物，发起 `client.get(f"/view/{token}")`，断言 HTML 包含的 DOM 节点、meta 标签或 HTTP Headers（参考 [`tests/unit/test_views_calibration_stats.py:180`](tests/unit/test_views_calibration_stats.py#L180)）。

- **`scripts/ci/remote-suite.sh` 是否存在与窄测运行方式**：
  - `scripts/ci/remote-suite.sh` **不存在**（仓内无 `scripts/ci/` 目录）。
  - 窄测命令（参考 [`tests/README.md:32, 56`](tests/README.md#L32)）：
    ```bash
    uv run --frozen pytest tests/unit/test_detailed_notes_view.py tests/unit/test_views_calibration_stats.py
    ```
  - 全量本地回归门禁为 `make test`（执行 `uv sync --frozen` 并运行 `uv run --frozen pytest -q tests`，排除 `tests/manual/`）。

- **仓内 `has_ui` 等前端测试约定**：
  - 存在约定。在 [`.github/workflows/gate.yml:25`](.github/workflows/gate.yml#L25) 中显式声明了 `has_ui: true` 传入上游工作流 `zlxlabs/gate/.github/workflows/gate-v2.yml@v2`。
  - 前端独立回归在 [`.github/workflows/ui-browser.yml`](.github/workflows/ui-browser.yml) 执行：包括 `npm run test:web`（Vitest 契约测试）与 `npm run test:browser`（Playwright Chromium 浏览器回归测试）。

---

## 8. og:description 来源

- **全仓检索事实**：
  执行 `rg -n "og:description|og_description"`，全仓仅存在两处 `og:description` 输出点：
  1. [`src/web/templates/transcript.html:6`](src/web/templates/transcript.html#L6)：
     ```html
     {% block og_description %}{{ title or "视频转录" }} 的转录校对结果{% endblock %}
     ```
  2. [`src/video_transcript_api/api/routes/views.py:393, 406`](src/video_transcript_api/api/routes/views.py#L393)：
     ```python
     og_desc = f"{safe_title} 的{safe_content_type}（{safe_platform}）"
     # ...
     <meta property="og:description" content="{og_desc}">
     ```
- **关键结论**：
  **仓内没有任何代码从总结正文（summary）中截取文本填入 `og:description`。**
- **线上现象归因**：
  线上某分享页卡片显示为 `"I asked OpenAI's Head of Product..."`，是因为该视频的原生视频标题（title）本身即为 `"I asked OpenAI's Head of Product..."`（或以此开头）。模板在渲染 `transcript.html` 时填充的是 `{{ title }} 的转录校对结果`，Twitterbot 抓取后在卡片描述中展示了该内容。

---

## 9. 风险与建议（≤10行）

1. **生产依赖缺失**：`pillow>=12.3.0` 目前仅在 `[dependency-groups].dev`，必须移至 `[project].dependencies`，否则容器镜像构建（`uv sync --no-dev`）会缺失 Pillow。
2. **中文字体缺失**：基础镜像 `python:3.11-slim` 无中文字体，直接用 Pillow 绘制中文会导致方块豆腐块（tofu）；建议随代码在 `src/web/static/fonts/` 打包开源中文字体（如 Noto Sans SC TTF）并显式加载。
3. **元数据未持久化**：封面图（YouTube thumbnail、B站 pic 等）、时长、发布日期未落盘；若卡片需展示封面背景或来源发布日期，需在下载器及缓存结构中补足持久化。
4. **生成时机建议**：采用「终态主动生成 + 路由按需惰性生成」策略，既保证新任务完成时卡片就绪，又能平滑兼容全量历史任务。
