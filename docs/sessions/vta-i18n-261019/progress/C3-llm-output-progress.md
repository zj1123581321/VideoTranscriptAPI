# C3 LLM 产出语言 — 进度存档

## 2026-10-19 锁定中文 prompt 快照

- **当前阶段**：implementing
- **本段结论**：先用测试锁死 `llm/prompts/__init__.py` 相对 Base `708352f6` 字节级不变，以及中文 builder 在 `language=zh-CN` 下的产出。生产代码尚未改动。
- **关键决策与已否决方案**：中文 prompt 留在原模块、英文另文件；否决改写 `__init__.py` 正文。英文篇幅系数仍按卡面假设 1.8。
- **下一步唯一动作**：新增 `llm/prompts/en.py` 与按 `get_language()` 取 prompt 的访问函数，再把总结/笔记/章节处理器接到该访问函数。

## 2026-10-19 英文 prompt 与篇幅系数接入处理器

- **当前阶段**：implementing
- **本段结论**：新增原生英文 prompt 模块与 `prompts/localized.py` 访问函数；总结/笔记/章节处理器按 `get_language()` 选 prompt。英文篇幅系数 1.8 作用于 summary budget 与 `min_summary_threshold`。章节标题英文按至多 12 个 word 写进 prompt，本地截断按 48 字符。
- **关键决策与已否决方案**：中文 `__init__.py` 零改动；否决在中文 prompt 后拼接 write in English。`localized.chapters_schema()` 因与 chapters_processor 循环导入已撤，schema 在调用点分支。
- **下一步唯一动作**：说话人兜底占位名按语言生成，并补 speaker_inferencer 测试。

## 2026-10-19 说话人兜底名按语言生成

- **当前阶段**：implementing
- **本段结论**：`_build_fallback_label` 在 zh-CN 仍输出 `说话人N`，en 输出 `Speaker N`。复合推测名自动带上该前缀。
- **关键决策与已否决方案**：复合名中的「标题关联推测」等中文标记保持原样（卡面只锁占位名）；不迁移历史 `speaker_mapping.json`。
- **下一步唯一动作**：provenance 写入 language，缓存复用按语言判定，并打 LANGUAGE-MISMATCH-REGENERATE 日志。

## 2026-10-19 provenance 语言判定与缓存隐藏

- **当前阶段**：implementing
- **本段结论**：生成层 provenance 写入 `language`（缺字段=zh-CN）。`get_cache` 对语言不一致的总结/笔记/章节视为缺失，转录路径会重跑该层。`LANGUAGE-MISMATCH-REGENERATE` 在 llm_ops 打 WARNING。校对层不因 language 重跑。分享卡文案不进 provenance，随总结重生删除旧卡。
- **关键决策与已否决方案**：否决改缓存键；否决改 transcription.py。用 get_cache 隐藏层 + llm_ops 磁盘判定双保险。
- **下一步唯一动作**：红验 LANGUAGE-MISMATCH-REGENERATE 断言，再跑 make test 与 scope check。

## 2026-10-19 验收与红验

- **当前阶段**：implementing
- **本段结论**：改坏日志字面量后 `test_language_mismatch_regenerate_log_locked` 以 AssertionError 转红并已还原。`make test` 退出码 0。`card_scope_check.py` 对 Base..HEAD 绿。本机无 LLM 凭据且出站网络被拦，真实样本补跑留给主脑。
- **关键决策与已否决方案**：红验只改 `log_language_mismatch_regenerate` 那一行日志前缀，未整文件 checkout。
- **下一步唯一动作**：提交本段进度并 push 到 `card/VideoTranscriptAPI-20261019-05`。

## 2026-10-19 撤回 get_cache 语言隐藏

- **当前阶段**：implementing
- **本段结论**：`get_cache` 不再按语言过滤。ViewTokenResolver 在 language=en 时仍返回原中文 summary/notes。复用判定收口为 `language_mismatched_generation_layers`，transcription / llm_ops / generate_notes 共用。HEAD `09da4805` 上该 View 测试以 AssertionError 先红。
- **关键决策与已否决方案**：否决继续用 get_cache 隐藏层。语言不一致的笔记允许重新生成，同语言仍 400。
- **下一步唯一动作**：跑 Narrow-Verify 与 make test，scope check 后 push。

## 2026-10-19 分享卡不再单独做语言判定

- **当前阶段**：implementing
- **本段结论**：从 `_GENERATION_LAYER_FILES` 删除 share_card。en 下 summary 已是 en 且仅有分享卡文件时 mismatch 为空。HEAD `7882798b` 上该测试以 AssertionError 先红（`('share_card', 'zh-CN', 'en')`）。
- **关键决策与已否决方案**：否决给分享卡补 provenance；它随总结重生删除重建。
- **下一步唯一动作**：generate_notes 准入恢复 `_read_fresh_notes_status` 权威读。

## 2026-10-19 generate_notes 准入恢复权威读

- **当前阶段**：implementing
- **本段结论**：准入段改回读 `llm_status.json`。函数返回整份 payload，调用方取 notes_status 并把 payload 交给语言判定。非法 JSON / 非 object 仍抛错。不再在准入段调 get_cache。
- **关键决策与已否决方案**：保留函数名 `_read_fresh_notes_status`，扩大返回值为整份 status 对象而不是另起函数。
- **下一步唯一动作**：跑 Narrow-Verify 与 make test，scope check 后 push。

## 2026-10-19 笔记篇幅阈值按输出语言缩放

- **当前阶段**：implementing
- **本段结论**：笔记生成与重试后的超长判定都按当前输出语言系数缩放；100 字符源、81 字符输出在 en 下单次调用，在 zh-CN 下仍触发原重试。
- **关键决策与已否决方案**：保留中文阈值 0.8，英文阈值只乘既有 `length_budget_coefficient()`，不增设配置。
- **下一步唯一动作**：统一 coordinator 与 SummaryProcessor 的最短总结阈值计算。

## 2026-10-19 总结最短长度预检共用阈值

- **当前阶段**：implementing
- **本段结论**：SummaryProcessor 与 coordinator 都调用 `effective_min_summary_threshold()`；en 下 800 字输入在 500×1.8 阈值前被预检跳过，避免两处门槛不一致。
- **关键决策与已否决方案**：以一个计算函数封装语言系数，否决 coordinator 自行重复计算。
- **下一步唯一动作**：按总结 provenance 语言缩放审计 hard-cap 统计。

## 2026-10-19 审计统计按总结 provenance 语言缩放

- **当前阶段**：implementing
- **本段结论**：summary-ratio 读取每条媒体总结 provenance 的语言并经 `generation_layer_language()` 处理；原文长 10,000、摘要长 7,000 时 en 不超预算而 zh-CN 超预算。
- **关键决策与已否决方案**：不读取当前配置语言；缺失 provenance 语言沿用该函数的 zh-CN 语义，英文系数引用 prompts/en.py 常量。
- **下一步唯一动作**：合并章节标题长度限制的重复定义。

## 2026-10-19 章节标题限制集中到语言 prompt 定义

- **当前阶段**：implementing
- **本段结论**：中文 24/23 字符限制集中在 localized.py，英文 12-word 提示与 48/47 字符截断都由 en.py 常量驱动；章节处理器不再另存中文数值。
- **关键决策与已否决方案**：用英文 prompt 常量插值，JSON 示例转义后渲染文本不变；中文 prompt 模块未改动。
- **下一步唯一动作**：跑指定 LLM/i18n 套件与 make test，再做 scope 与状态核对。
