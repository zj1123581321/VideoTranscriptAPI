# 分章详细笔记

## 功能语义

详细笔记用于长音视频的替代阅读：系统读取已生成的章节边界，按章截取原始
segment 闭区间，逐章调用 LLM 生成分层 Markdown 笔记，最后拼接为
`llm_notes.txt`。每章标题格式为：

```text
## [HH:MM:SS - HH:MM:SS] 章节标题
```

章节没有可用时间时只保留章节标题。

该能力是按需补层，不进入默认转录流水线，也不在 `/api/transcribe` 的公开
`processing_options` 中增加开关。生成 notes 时，既有
`llm_calibrated.txt`、`llm_summary.txt`、`llm_chapters.json` 及其状态不会被
改写或删除。

## 前置条件与一致性校验

- `chapters_status` 必须为 `generated`，否则接口返回 HTTP 409。
- 章节的 `start_seg` / `end_seg` 是原始 segment 列表的闭区间下标。
- 结构化任务从 `llm_processed.json` 的 `dialogs` 切片；纯文本任务从
  `load_segments()` 返回的列表切片。
- 生成前会用章节层保存的 fingerprint 校验当前锚点来源。缺失或不匹配时，
  整体 `notes_status` 写为 `failed`，不会生成可能错位的笔记。

## API

```http
POST /api/generate_notes
Authorization: Bearer <api-key>
Content-Type: application/json

{"view_token": "view_..."}
```

接口执行与 `/api/resummarize` 相同的权限和 view token 归属校验。受理后返回
业务码 `202` 和新 `task_id`，前端通过 `/api/task/{task_id}` 轮询。

重复生成规则：

- `notes_status=generated`：返回 HTTP 400，拒绝重复消耗 LLM 配额。
- `notes_status=failed`：允许重试。

## 状态与失败语义

`llm_status.json` 的 `notes_status` 当前有两个终态：

- `generated`：所有章节均生成成功，且完整 `llm_notes.txt` 已落盘。
- `failed`：指纹校验、章节切片或任一章节 LLM 调用失败。

逐章调用串行执行，使用 `task_type="notes"` 记录审计 token。任一章在客户端
内置重试后仍失败时，整批失败且不写半成品 `llm_notes.txt`。

## 查看与导出

查看页在内容总结之后展示可折叠的“详细笔记”区块，每章标题带稳定锚点。
章节已生成但 notes 尚未生成时显示“生成详细笔记”按钮；失败时按钮允许重试。

生成后支持：

- `GET /view/{view_token}?raw=notes`
- `GET /view/{view_token}?page=notes`
- `GET /export/{view_token}/notes`

Raw 和 `/export` 返回带元数据头的 UTF-8 文本；page 返回渲染后的独立 HTML。
