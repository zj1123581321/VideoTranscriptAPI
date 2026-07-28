# 说话人归属可观测性与纠错 — 实施 Spec v1

> Session：`260728-1050-q7m2` ／ 基线：`main` ／ 风险等级：internal（仓库未声明 GATE_TIER，按 internal 处理，建议后续在 AGENTS.md 补声明）
> 前置调研结论见同目录 HANDOFF.md；用户已确认总方向（2026-07-28）。

## 0. 已定裁决（用户拍板）

- 主攻 VideoTranscriptAPI 侧「检测 + 诚实呈现 + 局部覆盖」；**不** fork/patch funasr 库去拿声学置信度（调研证实该信号在句子粒度从未被计算过，成本不可接受）。
- 引擎侧改动（preset_spk_num 透传、hotword 热词）只记 backlog，本轮不动——用户担心 AI 提取的人数不准反而干扰 ASR 聚类。
- 实现外包给 Codex CLI（`codex exec`，TDD）；主会话负责拆卡与验收。

## 1. 关键不变式

- **I1 raw 不丢**：`speaker_id`（Speaker1…）从 `transcript_funasr.json` 到 `llm_processed.json` 全程保留（现状已满足，需测试锁死）。
- **I2 可追溯**：任何姓名判定带 `assignment_source`（`global_mapping` | `semantic_evidence` | `manual`）；自动纠正必须有 `evidence_segment_ids`，不落盘自由推理文本。
- **I3 双置信度分离**：mapping confidence（簇→名，已有）与 segment confidence（段→名，未来）不共用字段、不混合呈现。
- **I4 呈现诚实**：未校准置信度不以数字/百分比示人，只用等级词（较可靠 / AI 推断 / 待确认）。
- **I5 允许弃答**：低置信降级为「说话人N（待确认）」比自信地错更好（confidence gate 已做降级，本轮补呈现语义）。
- **I6 向后兼容**：旧缓存（无新字段的 `llm_processed.json`）渲染行为不变。

## 2. Increment 1（本次实现）：可观测性基建

**不改变任何姓名判定结果**，只加结构、信号与呈现。

### 2.1 稳定 segment id

- 生成时机：`speaker_aware_processor` 合并归一化之后（`_normalize_and_merge_dialogs` 产物上）。
- 形式：`seg_{start_ms:08d}_{speaker_id 全小写}`（start_ms 为该 dialog 起始毫秒）；同 key 冲突追加 `-2`、`-3`。
- 落盘：`llm_processed.json` 每条 dialog 带 `segment_id`；渲染层元素锚点**保持 `dlg-{index}` 不变**（floating-toc.js 章节跳转依赖它），segment_id 以 `data-segment-id` 属性暴露在同一元素上。
  （修订记录：v1 初稿曾写「锚点优先用 segment_id」，review 发现会打断章节跳转，已按上述方案修正。）

### 2.2 归属来源与 override 容器

- 每条 dialog 落盘 `assignment_source: "global_mapping"`（本增量唯一取值）。
- `structured_data` 顶层新增 `segment_overrides: {}`；渲染层实现读取逻辑：若 dialog 的 segment_id 命中 override，展示名以 `override.name` 为准并显示状态徽标。本增量**不产生任何 override 内容**，只锁机制与测试。
- override 条目 schema（为 Increment 2/3 预留）：
  ```json
  {"name": "李自然", "status": "confirmed|suspect",
   "assignment_source": "semantic_evidence",
   "evidence_segment_ids": ["seg_..."]}
  ```

### 2.3 全局风险信号（纯规则，零 LLM 成本）

计算时机：speaker inference 完成后；落盘 `llm_processed.json` 顶层 `speaker_risk_flags: [str]`。

- R1 `low_confidence_cluster_dropped`：存在被 gate 降级的簇（confidence < 阈值），且该簇段数占比 ≥5%。
- R2 `low_average_mapping_confidence`：被采用簇的平均 confidence < 0.7。

flag 名写完整字面量，禁止模板拼接（grep 可检索）。

### 2.4 采样分层修复

- `speaker_inferencer._extract_sample_dialogs`：每说话人从「时间轴前 K 条」改为**头/中/尾分层**（K=3 时各取 1 条，不足退化为现有顺序），字符预算等其余逻辑不变。
- 意图：簇后半段被污染时能拉低该簇 mapping confidence，而不是完全不可见。

### 2.5 呈现（transcript.html + dialog_renderer）

- 全局免责声明：由「包含说话人识别」改为「说话人姓名为 AI 推断，可能有误；关键引用请核对原音频」。
- `speaker_risk_flags` 非空时页面顶部显著提示「本集说话人区分可能不准」。
- 「说话人N」类 abstain 名称带「待确认」徽标。
- speaker 图例 tooltip 显示 mapping 等级词：≥0.8 较可靠、0.6–0.8 AI 推断（不外显数字）。

### 2.6 本增量明确不做

语义矛盾检测（Inc2）、自动改归属（Inc3）、人工修正入口（Inc4）、任何引擎侧改动。

## 3. 验收与测试

- 单测：id 生成与冲突；`_coerce/_normalize/merge/_apply_corrections` 全链路新字段保留；override 渲染优先级；I6 旧缓存兼容；R1/R2 规则边界；分层采样分布。
- fixture：`fixtures/raw/` 下的生产 task（task_d4870757…）裁剪成小型测试 fixture 放 `tests/` 对应目录——保留 Speaker4 低置信簇、S2「刚才大卫」与 S5 相关矛盾段落附近数据。raw 原件**不进 git**。
- 命令：`uv run pytest tests/unit`（存在 `tests/llm` 等相关目录则一并跑）；console 输出纯英文；pytest 不叠 `-q`，以 exit code 为准。
- 行数预算 ≤3500（体感目标 ≤800 手写行）。

## 4. Increment 2–4 概述（后续拆卡）

- **Inc2 语义矛盾检测**：LLM 单次扫描全文（直接称呼、自述、第三人称矛盾、问答关系）→ 写 `status=suspect` 的 override，不改名；成本目标 ≤ 现有说话人推断一次调用量级。
- **Inc3 有证据局部纠正**：≥2 个独立语义信号才写 `confirmed` override；只改可疑段，不重写全文。
- **Inc4 人工锚点与修正入口**；用户修正进评测集。

## 5. Backlog（引擎侧，已裁决本轮不动）

- funasr_spk_server 透传 `preset_spk_num`（funasr 原生支持 per-call oracle_num，`auto_model.py:578`；风险：人数提示错误会强制错聚类，等有评测集后再验证收益）。
- funasr_spk_server 透传 hotword 人名热词（内部已布线、调用点硬编码 `''`，`funasr_transcriber.py:233`）。
- 长期：Qwen3 自研管线暴露 per-segment margin（`cluster_merge.py` 已有 cosine/centroid 基建）。

## 6. 实施与协作

- 分支 `feat/speaker-obs-inc1`，Codex（`codex exec`，workspace-write）实现；TDD，测试绿即 commit（[codex] 署名），**不 push、不动 main**。
- 主会话审查后走本地漏斗（lint/test → 可选 OCR → review 循环）再开 draft PR。

## 7. Increment 2 实施细则（2026-07-28 追加；Inc1 已合并部署后拆卡）

**目标：语义矛盾检测——只标记可疑段，不改任何姓名。** 覆盖 Inc1 风险信号的盲区：置信度高但实际错了的簇（如生产实证里 S2=大卫 却说「刚才大卫」）。

### 7.1 新模块与调用时机

- 新模块 `src/video_transcript_api/llm/core/contradiction_scanner.py`：导出 `ContradictionScanner`（域名词命名，禁裸 helper/util）。
- prompt 与 JSON schema 按 speaker_mapping 现有模式放 `llm/prompts/` 与 `llm/prompts/schemas/`。
- 调用时机：`speaker_aware_processor.process` 中 segment_id 落定（去重完成）之后；单次 LLM 调用。
- 输入：每条 dialog 的 `segment_id + 展示名 + speaker_id + 文本前 100 字符`，附 speaker_mapping 与 meta。

### 7.2 输出契约（写入 `segment_overrides`）

```json
{"status": "suspect", "assignment_source": "semantic_evidence",
 "reason": "direct_address_conflict",
 "evidence_segment_ids": ["seg_..."]}
```

- **不写 `name` 字段**——渲染层 name 缺失时保持原展示名，只挂「待核实」徽标（机制 Inc1 已就位，渲染层零改动）。
- `reason` 枚举：`direct_address_conflict` | `self_reference_conflict` | `third_person_conflict` | `qa_adjacency_conflict`。不落盘自由推理文本（I2）。
- `evidence_segment_ids` 必须是本集真实存在的 segment_id：schema 约束 + 代码侧过滤幻觉 id（引用不存在 id 的条目整条丢弃并记日志）。

### 7.3 失控保护与状态诚实（v2，2026-07-28 gate 主审后修订）

- **门控（与姓名推断解耦）**：扫描只受两个条件门控——`has_speaker` 与自身开关；**不依赖 `infer_speaker_names`**。姓名未推断时显示名为原始标签，扫描仍可抓「同一 speaker_id 自称两个名字」等簇内矛盾。
- **开关双层**：config 级 `contradiction_scan_enabled`（默认 true）+ **per-task `processing_options` 开关**（沿用校对/总结的现有模式），任务级优先。
- **长内容分窗**（替代 v1 的 >500 段整体跳过）：每窗 ≤400 段、相邻窗重叠 10 段；目标 segment_id 取窗内、`evidence_segment_ids` 允许全集真实 id；逐窗合并（同 id 首见优先）；flags 按全集统计。**任一窗失败 → 整体 `failed` 并丢弃全部标记**（不让半覆盖冒充全覆盖），日志记明失败窗序号。
- 可疑段占比 > 20%（全集口径）→ 判扫描不可靠：丢弃全部逐段标记，仅落 flag `semantic_scan_unreliable`。
- 可疑段 ≥ 3 条或 ≥ 段数 3% → 追加 flag `semantic_contradiction_detected`（横幅复用 Inc1 机制）。
- 状态语义：`completed` 全部窗成功；`failed` LLM/解析/任一窗失败；`disabled` 任一层开关关闭；`skipped` 仅无说话人模式。stats 记 `contradiction_scan_status`。

### 7.4 验收

- 单测（mock LLM）：正常标记路径；幻觉 evidence id 被过滤；>20% 丢弃；失败不阻塞且状态落盘；flag 触发边界。
- fixture 场景：基于生产 slice，mock 返回 S2「刚才大卫」direct_address_conflict，断言 override 与 flag 产出、渲染出「待核实」徽标与横幅。
- 全量 unit + tests/llm 绿；行数预算同 §3。
