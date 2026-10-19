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
