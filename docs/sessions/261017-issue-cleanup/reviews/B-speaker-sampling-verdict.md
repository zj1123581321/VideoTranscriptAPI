<!-- delegate-outcome: succeeded -->

## 后续裁决（[codex]）

**按原卡校准：不阻断交付。** 零配额只停用本轮新采样与新说话人 LLM 调用；不清除与输入指纹匹配的已验证历史姓名，原有 `identity_fallback` 姓名恢复与分层缓存行为保持不变。

下方独审的历史姓名恢复事实与原 P1 判定均保留。阻断来自 review 卡额外加入、原实施卡和设计均未要求的“不从历史缓存恢复名字”，不构成原需求缺陷；原 `p1-found` 由此裁决更正。

- 主脑前置 OCR 意见 1（低）：`infer()` / `_identity_fallback()` docstring 未列零配额来源；接受不修。
- 主脑前置 OCR 意见 2（低）：私有 `_extract_sample_dialogs()` 零配额直调仍可能 top2 采样，但唯一生产调用方 `infer()` 已早退、无生产缺陷；接受不修。
- 两项来自主脑前置 OCR；下方独审自跑 OCR 为 `findings=[]`，来源不同，均如实保留。
- 原实施卡：`docs/sessions/261017-issue-cleanup/tasks/B-issue244-speaker-sampling.md`；PR [#262](https://github.com/zlxlabs/VideoTranscriptAPI/pull/262)。

failure-visibility: clean

## 结论

**P1，阻断交付。** 固定范围内的采样配额计算、top2 稳定排序和内容预算符合卡面要求；但零配额只在 `SpeakerInferencer.infer()` 内生效，真实缓存与落盘调用链仍能把历史推断姓名放回结果，未满足核心不变式 2。

## Findings

### P1 — 零配额仍会恢复历史说话人姓名

- **违反不变式：** 2（任一配额为 0 时须返回 identity fallback、不调用 LLM，且不从历史推断缓存恢复名字）。
- **证据：** 新增分支在 `src/video_transcript_api/llm/core/speaker_inferencer.py:394` 返回 identity fallback；但正常落盘路径的 `src/video_transcript_api/api/services/llm_ops.py:2112` 会在 `speaker_inference_source == "identity_fallback"` 时调用姓名恢复。该恢复函数用同输入指纹验证 `speaker_mapping.json` 后，在 `src/video_transcript_api/api/services/llm_ops.py:1905` 将验证过的缓存姓名写回 dialogs 和 speaker_mapping。现有集成用例也将这条恢复行为作为 identity fallback 的预期结果锁定（`tests/integration/test_llm_ops_identity_fallback_name_restoration.py:244-297`）。另外，分层缓存预检在 `src/video_transcript_api/api/services/transcription.py:1391` 按历史映射决定是否需要说话人推断，并可在所有层命中时于 1520-1528 直接返回缓存结果；此路径也不检查采样配额。
- **复现：** 先用非零配额处理一个媒体，留下与当前转录指纹匹配的 `speaker_mapping.json` 和带姓名的结构化结果；随后将任一配额设为 0，并对同一输入触发校对/补层。若进入推断器，新分支虽不调 LLM，`_save_llm_results` 仍会从匹配的 `speaker_mapping.json` 恢复旧姓名；若全层缓存命中，分层预检会直接返回既有含姓名结果。
- **风险：** 用户显式关闭说话人采样后，输出仍展示历史模型推断出的姓名；核心停用语义无法兑现，因此阻断交付。

## 其余不变式

- **1：通过。** top2 的条数和字符配额分别取配置基准与 8/1200 的最大值，较大的显式基准不会被下调；示例注释表达了基准及加额关系。
- **3：通过。** `_extract_sample_dialogs` 每轮只计算一次 top2；稳定排序保留候选字典顺序；helper 的未使用 `speakers` 参数已移除。
- **4：通过。** 单条 120 字符上限和全局 `max_total_sample_chars` 预算处理未改变。
- **5：通过。** 本次未新增负数校验、抽象或无关修复。

## 验证

- `git diff --check 29f24581a8532605413c0aab22faec028deb5e58..e6814762c0999f87b7c3cb80f0910f925d9c6474`：通过。
- OCR 前置扫描：`status=reviewed`、`coverage=complete`、`findings=[]`；无 finding，因此二次 verifier 状态为 `skipped`。该结果不改变上述直接调用链 finding。
- 未运行测试；本卡指定的验证命令为 `git diff --check`。
