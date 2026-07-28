# 说话人归属工程化纠错 —— 交接 Session

> Session ID：`260728-1050-q7m2`
> 创建时间：2026-07-28 10:50 CST
> 状态：**调研完成，待方案设计/实现**
> 类型：**生产问题诊断 + 工程方案设计**
> 基线：`main`
> 代码改动：无；commit：无；部署：无

## 新 Session 直接粘贴的 Prompt

```text
你要在 VideoTranscriptAPI 仓库继续「说话人归属工程化纠错」工作。第一步先阅读本 HANDOFF、仓库根 AGENTS.md 和 README；不要重新做已经完成的生产调查。全过程用中文沟通，console 输出优先英文。

已确认约束：底层 diarization 引擎短期不能提升。先把方案收敛成可实施 spec，未获用户确认不要直接实现；所有代码写入交给 implementer。重点是把 raw Speaker ID 从真相降级为一个特征，按 segment 决定最终姓名，并允许 abstain。

生产证据、当前机制、分阶段方案、数据结构、指标和待裁决点均在本 HANDOFF。下一轮先写 spec 和生产 fixture，不直接改代码；定义 segment override contract、异常规则、abstain 策略、指标与验收，再拆第一个 TDD 增量。
```

## 问题背景

用户提供生产页：<https://sum.lexgogo.site/view/view__DTwz9vmzJQ8f9Dysm6SYvlOzKevtZuizxAUxYdDvzU>。节目标题为“V92.我用AI重活一遍！AI提升幸福感的9种姿势？”，来源小宇宙，约 70 分钟；用户感知“大卫/李自然全文混了”。当前流程先由 diarization 产生少量 `SpeakerN` 簇，再由 LLM 按 speaker 全局采样给每簇贴姓名，最后逐段套用。只要某个簇局部底层错分或 ID 错配，全局映射就会把这一处错误批量传播到该簇的全部段落，于是局部错误在页面上呈现为“全文都错”，而不是一个可见的局部异常。

## 生产实证（task fixture）

- `task_id`：`task_d4870757c96f4315947c342d373c51b1`
- 创建 `09:30:47`，完成 `09:41:40`
- 缓存目录：`data/cache/xiaoyuzhou/2026/202607/6a66e136a3fec224d5a3f00f/`
- 全局映射：`Speaker1→小丹尼 .7`、`Speaker2→大卫 .6`、`Speaker3→电动Emma .6`、`Speaker4→说话人4 .4`（未采用）、`Speaker5→李自然 .9`
- `117` segments；`raw/processed/view` 映射 `mismatch=0`
- 推断模型：`deepseek-v4-flash`；tokens `2663/3974/6637`；耗时约 `48.5s`

全局映射、应用和展示没有发现整体互换；更像局部 FunASR diarization 的 cluster impurity 或 ID 错配。关键矛盾：

- `00:10:31`，S5 文本称“大卫”；
- `00:10:52`，S2 说“刚才大卫”；
- `01:01:19`，S5 说“我很同意自然说的”；
- `01:07:37`，S2 邀请自然，紧随 `01:07:58` 起 S1 内容却像李自然。

名字本身也可能是 ASR 抄错；生产缓存音频已经清理，所以以上只能证明文本与簇标签存在局部矛盾，不能把名字或声纹当作已核实事实。证据边界必须在后续 spec 中写清。

## 当前代码机制与关键文件

- `src/video_transcript_api/transcriber/funasr_client.py:498`：底层 diarization。
- `src/video_transcript_api/llm/core/speaker_inferencer.py:218`：按 speaker 全局采样并建立映射；`:371` 前 K 段采样；`:722` confidence gate。
- `src/video_transcript_api/llm/processors/speaker_aware_processor.py:388`：逐段把 raw ID 套成全局姓名，同时保留 `speaker_id`。
- `src/video_transcript_api/llm/prompts/__init__.py:758` 和 `src/video_transcript_api/llm/prompts/schemas/speaker_mapping.py:1`：映射提示与 schema。
- `src/web/templates/transcript.html:249`：仅显示“包含说话人识别”，没有不确定性解释。

当前 confidence 是 LLM 对“这个簇叫什么”的自评，不是簇纯度，也不是每段归属概率；不能直接当作“本段姓名 90% 准确”。

## 第一性原理与架构方向

底层信息缺失无法凭空恢复；剩下的杠杆只有四条：增加独立信息、允许放弃判断、矛盾后二次修正、少量人工锚点。关键架构转变是：raw Speaker ID 从“真相”降级为“一个特征”，最终姓名按 segment 决定。

### 推荐分阶段方案

**P0：防止自信地错**

- 做语义矛盾检测，落 `segment_overrides`；
- 低确定性时降级为“说话人待确认”；
- 总结/章节只引用已确认姓名；
- 页面明确这是 AI 推断，不暗示确定事实。

**P1：自动纠错**

- 从全文构建人物档案；
- 对可疑段取前后 2–3 轮上下文；
- 综合直接称呼、自述经历、第三人称矛盾、问答关系；
- 至少两个独立信号才自动改；
- LLM 输出候选和 `evidence_segment_ids`，不保存自由推理；
- 只改可疑段，不重写全文。

**P2：人机协作**

- 每人保留 1–2 个代表音频身份锚点；
- 支持“只改本段”“从此处开始”“同类可疑段”；
- 用户修正进入评测集。

**P3：可选增强**

- 多次独立判断；模型分歧即降级；
- 经授权的常驻主持人 voiceprint（必须注明隐私与授权边界）。

## 建议数据结构

示例（字段名可在 spec 阶段最终定稿）：

```json
{
  "global_mapping": {
    "Speaker1": {"name": "小丹尼", "confidence": 0.70},
    "Speaker2": {"name": "大卫", "confidence": 0.60},
    "Speaker5": {"name": "李自然", "confidence": 0.90}
  },
  "segment_overrides": {
    "seg_0107_0058": {
      "name": "李自然",
      "status": "confirmed",
      "assignment_source": "semantic_evidence",
      "assignment_confidence_kind": "segment",
      "evidence_segment_ids": ["seg_0107_0037", "seg_0107_0058"]
    }
  }
}
```

`llm_processed`/`dialog` 最终应带 `assignment_source`、`assignment_confidence_kind`、`evidence_segment_ids`。必须区分 mapping confidence（簇叫什么）和 segment confidence（当前段归谁）；两者不能共用一个未校准数字。

## 量化与验收

建立人工标注的中文播客集，先测 baseline，再设绝对阈值。底层指标：DER、JER、ID-switch、cluster purity；映射指标：per-speaker name accuracy、swap rate；端到端指标：姓名归属准确率、关键引用错归率；可信度指标：ECE、Brier、coverage-accuracy、高置信静默错误率。产品目标是高 precision、可 abstain，不追求 100% 覆盖；阈值应由数据和代价曲线决定，而非拍脑袋。

## UI 建议

未校准前不要显示“90% 准确”。只显示“AI 推断”“较可靠”“待确认”等等级；tooltip 分开说明姓名映射可信度与当前段归属可信度；页面全局提示：关键引用请核对原音频。

## 待裁决问题（按爆炸半径排序）

1. 是否允许保留/处理短音频片段，还是只能纯文本？这决定 P2 身份锚点和数据留存边界。
2. 自动纠错精度与覆盖如何取舍？高 precision + abstain，还是更高覆盖接受更多人工复核？
3. 人工确认入口是什么、作用范围是本段、从此处开始，还是同类可疑段？
4. 是否允许 voiceprint；如允许，授权、隐私和删除机制是什么？
5. LLM 成本/延迟预算是多少？这决定 P1 上下文范围和多次判断策略。

## 下一轮执行建议

先写 spec 和生产 fixture，不直接改代码：定义 segment override contract、异常规则、abstain 策略、指标与验收；随后拆第一个 TDD 增量：

1. **Increment 1**：可观测性 + 数据结构 + UI 免责声明（不自动改）。
2. **Increment 2**：只检测矛盾并标记。
3. **Increment 3**：有证据的局部纠正。
4. **Increment 4**：人工锚点。

## 证据限制与已尝试

- `video-understand` 对 70 分钟音频做过两次辅助审计（成本 `0.3699 + 0.403` 元）。方向支持 diarization/mapping 层问题，但长音频时间戳漂移，不能作为主证据。
- `graphify` 本轮仅得到 partial graph：`8791 nodes / 16818 edges`，10 docs 缺失；健康检查有 `1185 dangling`、`1 self-loop`、`collapsed directed 803 / undirected 809`，不作为根因证据，只用于定位调用链。
- 仓库 `graphify-out` 可能已有临时产物且通常 ignored。

## 工作区状态与交接清单

- 当前分支：`main`。
- 用户已有未跟踪目录 `docs/sessions/260715-0635-pr3x/`，不要触碰。
- 本 session 创建后，`git status` 会新增本目录；除此之外无其他 diff。
- 本文档无代码改动、无 commit、无部署。

完成判据：

- [ ] spec 明确四类杠杆、segment override contract、异常规则和 abstain 策略；
- [ ] 生产 fixture 可复现映射/矛盾证据，且明确音频已清理的边界；
- [ ] baseline 与验收指标锁定，区分 mapping/segment confidence；
- [ ] UI 文案不再把未校准 confidence 说成准确率；
- [ ] 每个增量由 implementer 负责代码写入，TDD 与验证证据齐全；
- [ ] 关键引用可追溯到 `evidence_segment_ids`，不保存自由推理。

### 一句话结论

底层 ID 不可靠时，不再整簇强制贴名；改为“全局先验 + 逐段证据 + 可放弃判断 + 局部覆盖 + 少量人工锚点”。
