# C4 网页界面 / 渲染器 / 分享图 i18n 进度

## 2026-10-19 对照测试与文案目录

### 当前阶段
implementing

### 本段结论
已把 `web.` / `render.` / `og.` 文案写入 C1 目录（zh-CN 值等于原硬编码），并锁死说话人对话 HTML 与首页常量的 zh-CN 逐字对照。逻辑依赖已 grep：`floating-toc.js` 用「内容总结/详细笔记/校对文本」做 `findOutlineSection` 匹配，换文案前必须改成 `data-section`；`data-confidence-level` 无 JS 比较。

### 关键决策与已否决方案
- 静态页走 `/i18n.js` 注入 `window.I18N`（仅 `web.` 子集）+ 共用 `src/web/static/js/i18n.js`，不另建前端文案文件、不引入 i18n 库。
- 已否决：前端独立 JSON、gettext、模板内 `t is defined` 中文兜底。
- 已申请 Scope seq=1：`tests/conftest.py`、`tests/browser_server.py`（Jinja `t()` / `/i18n.js` / 英文 e2e）。

### 下一步唯一动作
改 `dialog_renderer.py`：待确认读 `speaker_inference_meta.applied`，中英占位名正则仅作旧数据兜底；固定文案改走 `t()`。

## 2026-10-19 渲染器 applied 判定与分享图标签

### 当前阶段
implementing

### 本段结论
说话人「待确认」改为读 `speaker_inference_meta` 的 applied 标记；无该字段时中英占位名正则兜底。结果页徽章与 OG 卡面 `AI 总结` 走目录，zh-CN 对照夹具仍绿。

### 关键决策与已否决方案
- 保留 `og_card.AI_LABEL` 常量给既有布局测试量宽，渲染路径每次调用 `t("og.ai_label")`。
- 已否决：继续只用 `^说话人\\d+$` 判定（英文 Speaker N 永远没有待确认）。

### 下一步唯一动作
`views.py` 首页/导出元数据走 `t()`，Jinja 注入 `t`/`html_lang`，改模板。

## 2026-10-19 首页导出与 /i18n.js

### 当前阶段
implementing

### 本段结论
首页 zh-CN 仍返回原 `_HOME_HTML` 常量；英文替换目录文案。导出元数据/文件名/平台展示名与 page/raw 提示走 `t()`。`GET /i18n.js` 注入 `window.I18N`（仅 `web.`）和 `__VTA_LANG__`。

### 关键决策与已否决方案
- 静态页文案源仍是 C1 目录，端点形状：`window.__VTA_LANG__ = "zh-CN"|"en"; window.I18N = {"web...": "..."}`。
- 已否决：拆前端文案文件。HTTPException JSON `detail` 留给 C5。

### 下一步唯一动作
改 Jinja 模板与静态页/app.js，并给 tests/unit/web 的 Jinja 环境安装 `t`。
