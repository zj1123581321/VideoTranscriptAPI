# OG 页面标签（og-meta）进度

Task: 分享页 `/view/{view_token}` 有卡片时输出 X / Open Graph 大图标签
Dispatch: dlg-20261016-050109-9e5512

---

## 段1：实现 + 测试 + 红验收尾

- 当前阶段：verifying
- 本段结论：`view_transcript` 成功渲染 `transcript.html` 时用 `load_share_card` 读卡；`base.html` 新增默认空的 `og_image_meta` block，`transcript.html` 有卡才覆写 5 个标签并把 `og:description` 换成第一条要点。`tests/og_card/test_view_meta.py` 7 条全绿（有卡 / 无卡 / 不合契约 / 缓存目录缺失 / 转义 / mtime `?v=` / `?page=` 导出）。两次最小注入红验均为 AssertionError：`{% if share_card %}`→`{% if true %}` 让无卡页冒出 5 个标签；`headline|safe` 让引号拆断 meta 属性。还原后 `tests/og_card` 58 passed。
- 关键决策与已否决方案：核实 `get_view_data_by_token` 成功/interrupted 载荷已含 `cache_dir`（`view_token_resolver.py:147`），成功路径直接用该字段；目录字段缺失时才回退 `get_cache_by_view_token`（与 `/og/` 同款），未改 ViewTokenResolver。读卡+stat 放进 `view_transcript` 内嵌函数经 `asyncio.to_thread` 执行，拒绝再抽模块级 helper（单消费者）。无卡不输出任何降级图。
- 下一步唯一动作：推送 `card/vta-261016-og-meta2`，开 draft PR 到 main。
