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
