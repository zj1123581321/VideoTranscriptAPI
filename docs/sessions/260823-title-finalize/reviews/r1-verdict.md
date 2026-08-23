# r1-verdict：title-finalize 写边界元数据定稿

- **审查范围**：`5ce323aad3fbaa3525df959f74a2d873d84d85b5..f1ee994b8db722bc5862e775b7a0ac9fc8ca80ce`（PR #62）
- **审查者**：Cursor 执行器（独立 review 卡 r1）
- **日期**：2026-08-23
- **risk-tier**：personal（infra/状态机例外，降层三问必答）

## Verdict

**pass** — 无未接受的 P1。不变式 I1–I5 在审查范围内成立；`save_cache` 写边界前的定稿逻辑与测试一致。

## 本轮新证据

（以下均非复读 diff 文本，为审查过程中独立拉取的调用链与命令输出。）

1. **save_cache 站点全覆盖**：在 head `f1ee994` 上对 `transcription.py` 执行 `grep save_cache|_finalize_presentation`，6 处 `save_cache` 前均有 `_finalize_presentation_fields()`；缓存未命中主路径无遗漏写边界。
2. **LLM 队列消费字段**：阅读 `llm_ops.py` 中 `process_llm_task` — `video_title` 取自 `llm_task["video_title"]` 用于通知与 `_generate_title_if_needed`；对照 head 上缓存部分命中分支，发现 `handoff_payload` 在 `finalize_presentation_metadata` 之前组装，与 `calibrating_status_kwargs` 可能不一致（见 F2）。
3. **补拉 downloader 选择**：阅读 `_finalize_presentation_fields` 中 `retry_downloader = download_downloader or metadata_downloader`；当 `has_separate_download_url` 时 `download_downloader` 恒为 `GenericDownloader()`，会优先于 `metadata_downloader`（平台 downloader）用于 `get_metadata` 补拉（见 F3）。
4. **GenericDownloader 补拉能力**：阅读 `generic.py` `_fetch_metadata` — 依赖 `get_video_info(url)` 解析页面，对小宇宙 episode URL 无专用逻辑，补拉大概率仍得空标题后落 basename 占位。
5. **红验锚点（卡面预取，本轮用于锁死测试约束力）**：base `5ce323aa` 上拷入 `test_flow_metadata_retry_before_save_cache` 失败，断言标题为 `6a89b9b7008ed7314d3acdbe` 而非 `Real Episode Title`；helper 单测在 base 上 ImportError — 测试确实绑定本次行为而非恒真。

## 降层三问（infra 例外）

### ① 终态写入成功之前已发生哪些不可逆动作？

| 阶段 | 不可逆动作 | 是否受 finalize 保护 |
|------|-----------|-------------------|
| 第一次 `get_metadata` 失败 | 仅日志；title/author 保持空（新代码） | 是（I1） |
| 下载 / 转录 | 音频落盘、转录文本生成 | 否（设计外） |
| 中途 `notify_task_status` | 通知可能带 interim 标题 | 否（行为层） |
| `save_cache` | video_cache 行 title/author 持久化 | **是** — `_finalize_presentation_fields()` 紧邻其前 |
| 缓存部分命中 → LLM handoff | `CALIBRATING` 状态写入 | `calibrating_status_kwargs` 用 finalize 后变量；`llm_payload` 可能仍用旧值（F2） |

核心不变式针对的是 **video_cache 持久化标题**；下载/转录不可逆但不在本 PR 范围。

### ② 守卫用的值在实际部署形态下自身唯一吗？

- **写边界守卫**：`finalize_presentation_metadata` 产出的 `(title, author)` _tuple，由当前 downloader 实例内存缓存（`BaseDownloader._metadata_cache` 按 `video_id`）+ 同进程第二次 `get_metadata` 复用。
- **部署形态**：personal 单实例（n305）；同 URL 同任务内单 downloader 实例 — 补拉与下载阶段 warming 共享缓存，唯一性成立。
- **media_id / platform**：缓存键与任务状态键，单实例下无副本竞争问题。

### ③ 保护覆盖的是「写入」还是「行为」？

- **写入**：`save_cache(..., title=..., author=...)` 前定稿 — **覆盖完整**（6 站点）。
- **行为**：中途通知、`handoff_payload["video_title"]`（部分缓存命中）、成功响应 `data.video_title`（缓存全命中路径未调用 finalize）— **未全覆盖**；属展示/通知层，不导致本次设计的「错误标题永久写入 video_cache」静默错结果（F2/F4 为 P2）。

## 不变式核对

| ID | 判定 | 证据 |
|----|------|------|
| I1 | ✅ | 失败分支改为 `""` 而非 basename/Unknown（diff `1628–1636` 段）；`test_flow_metadata_retry_before_save_cache` |
| I2 | ✅ | `_finalize_presentation_fields` + `finalize_presentation_metadata` 在全部 `save_cache` 前；单测 `test_finalize_retries_get_metadata_for_blank_title_and_author` |
| I3 | ✅ | override 优先且不触发 downloader；已有非空 title 不被 retry 覆盖 — 单测 `test_finalize_applies_metadata_override_over_existing`、`test_finalize_does_not_overwrite_existing_non_empty_title` |
| I4 | ✅ | `except Exception` 吞掉后仍落 fallback，任务继续 — 单测 `test_finalize_swallows_get_metadata_exception`、流程测试 success |
| I5 | ✅ | 无新 DownloadInfo 字段/质量枚举；`finalize_presentation_metadata` 为同文件函数，非独立模块 |

## Findings

### F1 — finalize 内宽 `except Exception`（OCR medium）

| 维度 | 内容 |
|------|------|
| 工具标注 | OCR minimax `partial`，medium — 宽 except 吞掉所有异常 |
| 本仓判定 | **接受（设计内）** — 对应 I4；infra 卡锁定「补拉异常吞掉不得让任务失败」 |
| P1 两问 | ① 会触发：补拉失败时；② 后果：落 basename/Unknown 占位，任务仍 success — **可接受**（显式 fallback，非静默无结果） |
| 溯源 | I4 |
| 处置 | 不修（本 PR） |

### F2 — 缓存部分命中：handoff_payload 在 finalize 之前组装（本仓新发现）

| 维度 | 内容 |
|------|------|
| 工具标注 | — |
| 本仓判定 | **P2** |
| P1 两问 | ① 仅当 finalize 会改变 title（如 `metadata_override` 覆盖缓存标题、或缓存 title 为空走 fallback）且走部分命中 LLM 队列时触发；② LLM 通知/协调器读 `llm_task["video_title"]` 可能短时不一致，但 `video_cache` 已存正确标题 — **后果可接受，非静默持久化错误** |
| 溯源 | I2 行为层缺口 |
| 处置 | backlog：将 finalize 提前到 `handoff_payload` 组装前，或 finalize 后更新 `handoff_payload["video_title"]` |

### F3 — separate `download_url` 时 GenericDownloader 优先补拉（卡面降层观察 + 本仓核实）

| 维度 | 内容 |
|------|------|
| 工具标注 | — |
| 本仓判定 | **P2** |
| P1 两问 | ① `download_url` 与平台 URL 分离且首次 `get_metadata` 失败时触发；② GenericDownloader 对小宇宙 URL 难拿真标题，可能仍 basename — **与旧代码「立即冻 basename」同级或略好**（旧路径无任何补拉） |
| 溯源 | I2 补拉 downloader 选择 |
| 处置 | backlog：retry 优先 `metadata_downloader or download_downloader` |

### F4 — 缓存全命中路径不调用 finalize（本仓新发现）

| 维度 | 内容 |
|------|------|
| 工具标注 | — |
| 本仓判定 | **P2（接受不修）** |
| P1 两问 | ① 仅历史脏缓存（旧代码写入 basename）全命中时；② 展示仍错但 PR 范围是「防新发」— PR 描述已声明 |
| 溯源 | 非 I2 范围（无新 write） |
| 处置 | 接受；生产脏数据已单独回填 |

### F5 — 成功路径 author 为空时 finalize 仍会 `get_metadata`（OCR medium）

| 维度 | 内容 |
|------|------|
| 工具标注 | OCR medium — 成功路径可能再调 get_metadata |
| 本仓判定 | **P3** |
| P1 两问 | ① 仅 title 已填、author 仍空时；② 多一次网络调用，结果正确 — 可接受 |
| 溯源 | I2（填空白字段） |
| 处置 | backlog 可选优化：分字段判断 retry |

### F6 — f-string 日志与 PEP8 空行（OCR low）

| 维度 | 内容 |
|------|------|
| 工具标注 | OCR low |
| 本仓判定 | **P3** |
| P1 两问 | 不适用 |
| 处置 | 不修 |

## 测试与红验

- 新增单测 `tests/unit/test_finalize_presentation_metadata.py`（5 条）覆盖 override、retry、不覆盖、fallback、吞异常。
- 流程回归 `test_flow_metadata_retry_before_save_cache` 覆盖「首次 metadata 超时 → 下载 warming → save_cache 真标题」。
- 红验：base 上流程测试失败、helper ImportError — 测试非恒真。

## 结论摘要

本次 diff 守住「展示元数据在写边界定稿」核心不变式：失败路径不再早填占位符，全部 `save_cache` 前统一 `finalize_presentation_metadata`。未发现会导致 **video_cache 错误标题静默持久化** 的 P1。遗留为通知/handoff 行为层与 separate `download_url` downloader 选择，记 P2 backlog，不阻塞合并。
