# 长稿深度阅读工作流优化 spec

日期：2026-07-28 ｜ 风险档：personal ｜ 基线：main@7e127b1

## 背景与问题

3 小时播客校对稿 71k 字，现有单次全文总结只产出 5.3k 字（13:1 压缩必然有损）。
根因是架构性天花板，不是 prompt 措辞：

1. 单次 LLM 调用的"总结类"输出自然收敛在 3-6k 字；
2. 长输入注意力稀释（lost in the middle），中段细节召回差。

用户现有 workaround：复制 `?raw=calibrated` URL 喂给外部 ChatGPT/Claude 做深度总结 + 追问。
方向正确（追问不该自建），痛点仅是"手动拼 prompt + 复制 URL"两步摩擦。

## 需求拆解（三个 job）

| Job | 需要什么 | 结论 |
|---|---|---|
| 导航（值不值得读） | 3-5k 总结 + 章节 | 已满足，不动 |
| 替代阅读（不听 3 小时拿 90% 信息） | 15-25k 字分章详细笔记 | **缺口，增量2 补** |
| 追问/深挖 | 交互式对话 | 不自建，增量1 降摩擦 |

## 已裁决（用户拍板 2026-07-28）

- 详细笔记**按需生成**（view 页按钮触发补层），不进默认流水线，不加 processing_options 开关。
- 落地顺序：先增量1（复制 Prompt 按钮），后增量2（分章详细笔记）。串行，前序 gate 绿合并再开下一个。

## 保守默认（主会话决定，总结时上浮报备）

- v1 **不动 summary 层**：notes 只新增自己的缓存层，不用笔记反哺重写全局总结
  （避免破坏"分层缓存只增不减"，reduce-改写-summary 留作可选增量3，不排期）。
- notes 依赖 chapters 层：按钮仅在 chapters_status=generated 时展示；无章节的短内容本来不需要详细笔记。
- 逐章调用 v1 串行执行（走现有 llm 队列单线程消费模式），不引入新并发机制。

---

## 增量1：一键复制深度阅读 Prompt（PR A，分支 feat/deep-read-prompt-button）

### 设计

- `config.jsonc` `web` 段新增可选 `deep_read_prompts`：数组，每项 `{label, template}`，
  `template` 含 `{url}` 占位符。未配置时用内置默认一项（深度笔记版文案）。
- view 页 quick-copy-bar（transcript.html:173-221）为每个 preset 渲染一个按钮，
  显示条件与"Raw 校对文本"卡片一致（校对文本存在）。
- 点击后 JS 把 `{url}` 替换为绝对 raw URL（origin + `?raw=calibrated`，与现有
  `.quick-copy-btn` 同源逻辑），整段复制进剪贴板，按钮短暂显示"已复制"反馈。
- 非法配置项（缺 label/template、template 无 `{url}`）运行时跳过 + warning 日志，不崩页面。

### 完成条件

- 按钮出现在 view 页且复制内容 = 模板文本 + 该任务绝对 raw URL；配置缺省有默认值。
- 测试：配置解析（缺省 fallback / 非法项跳过）+ view 路由渲染含按钮。
- 符号命名带领域词（deep_read_prompt*），日志完整字面量；不改 llm/、cache/。
- 预估 <300 行，一个 PR。

## 增量2：分章详细笔记 map（PR B，分支 feat/chapter-detailed-notes）

### 设计（易变项在前）

- **触发**：view 页"生成详细笔记"按钮 → `POST /api/generate_notes {view_token}` →
  202 + task_id 入 llm 队列（镜像 /api/resummarize 全套：归属校验、已生成拒绝重复、前端轮询）。
- **Map 切片**：按 `llm_chapters.json` 的 `[start_seg, end_seg]` 闭区间切章节文本——
  结构化路径切 `llm_processed.json` 的 dialogs；纯文本路径切 `load_segments()` 结果。
  带时间戳与说话人。指纹校验不过（jump_ok 为 false 的场景）→ 整体 failed，不出错位笔记。
- **逐章生成**：新 `notes_processor.py`，每章一次 LLM 调用（输入：本章文本 + 章节
  title/gist + 相邻章标题做上下文；输出：分层 bullets 详细笔记，保留人名/数字/原话，
  关键论断加粗）。模型 `notes_model` 回退 `summary_model`。
- **失败语义**：任一章经 llm_client 重试后仍失败 → 整体 `notes_status=failed`，
  不落半成品文件（personal 档红线：不静默丢章）。
- **产物**：拼接为 markdown（每章 `## [HH:MM:SS – HH:MM:SS] 标题`）存
  `llm_notes.txt`；`llm_status.json` 增 `notes_status`（generated/failed）。
- **展示/导出**：view 页新增"详细笔记"折叠 section（章节锚点）；`?raw=notes`、
  `?page=notes`、`/export/{token}/notes` 全套导出。
- **触点清单**（摸底已确认）：cache_manager（_KNOWN_ARTIFACT_FILENAMES / save_llm_result /
  get_cache）、cache_analyzer.cache_files、llm_status、views.py 导出 type_map 数处、
  view_token_resolver、llm/core/config（notes_model）、transcript.html、tasks.py 新路由、
  llm_ops 队列消费分支、prompts 新增 NOTES_SYSTEM_PROMPT。

### 完成条件

- 3 小时级长稿实测：笔记总长显著高于现有总结（预期 15-25k 字），逐章时间戳正确。
- 重复点击/已生成 → 拒绝重复生成；失败可从按钮重试。
- 分层缓存回归：notes 补层不触碰 calibrated/summary/chapters 已有产物（有断言测试）。
- 成本记录进 audit token 统计（task_type="notes"）。
- 预估 <1500 行，一个 PR，TDD。

### backlog（记录不排期）

- 增量3（可选）：notes 存在时 /api/resummarize 用笔记做 reduce 重写全局总结。
- 章节侧栏与笔记 section 的点击联动。
- 多 preset prompt 的管理 UI。
