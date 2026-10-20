# 2026-10-17 Issues 收尾设计

基线：origin/main 29f24581a8532605413c0aab22faec028deb5e58
结论来源：Opus 主报告与补充报告、FunASR 空结果 probe、主脑核实的 gate-hub 消费规则。
目标：今天分三批减少真实故障，并关闭没有本仓用户价值或已修复的 backlog。

## 判断原则

本项目由个人维护，面向自托管用户。检查真实 producer 与消费结果，在产生错误状态的最窄边界修复；不为维护者私有部署添产品框架。待办必须对应用户价值或明确触发条件。

## issue 裁决

| Issue / 子项 | 决定 | 依据 |
|---|---|---|
| #243 | 批次 A 修 | 真 FunASR + CacheManager/DB/export probe 证明空 segments 会写缓存、任务进入 calibrating、export 200；LLM 最终 success 由 mock 产生，不算完整链路证据。 |
| #244-1 | 不修，已独立刻画 | 重复排队/coordinator 开销存在，但 inferencer 命中、没有重复外部 LLM 或错名，不值产品改动。 |
| #244-2/#244-7 | 批次 B 修 | top2 固定配额违背停用/大配置；重复计算 top2 可移出说话人循环。 |
| #244-3/#244-4/#244-5/#244-8 | 关闭 not planned | 当前没有受影响结果或数据丢失证据；不宣称 JSON 序列化契约已完整。缓存规则升级后重算可接受。 |
| #244-6 | 关闭已修 | main 已按 evidence_type 对应分区核对 quote。 |
| #259/#199 | 批次 C 修并收尾 | 保留真实 Chromium 阻断门禁，补 GitHub 原生失败 artifact/trace/screenshot，明确长期不接 PWRS 私有服务。 |
| #211/#212 | 关闭不计划做 | 前者是私有 GlitchTip 接收核验且生产收据未知；后者仅外观问题，无收敛设计。 |

## 三批边界

A：FunASR 的 transcribe_sync 格式化后拒绝空/纯空白结果，复用 EmptyTranscriptError；同批检查 YouTube API 平台字幕 parse 后 text 与 segments 都空的路径。FunASR adapter 拦截覆盖两个 ASR 调用点；不要改格式化函数（历史缓存仍读取它）。CapsWriter 契约保持不变；执行者核锁定 SDK 是否保证纯正文非空，若不保证，只在 Transcriber.transcribe 读 txt 后拒绝纯空白。保护跨变体已有缓存。预算目标 200、硬 250 行。
B：普通说话人基准配额；top2 取 max(基准, 8 条/1200 字符)，任一配置为 0 则全员停用，身份 fallback 不调用 LLM；不加负数校验。保留单条 120 字符与全局预算。同步修改示例配置的相关注释。#244-5 关闭不代表 JSON 契约齐全。预算目标/硬上限 200 行。
C：#259/#199 同一 PR。失败时保留 Playwright trace 与 screenshot，并上传 Actions artifact 7 天；同时更新 AGENTS.md 和浏览器测试文档为无期限本仓政策：真实 Chromium 阻断回归、不接 PWRS。只有本地与 CI artifact 证据通过后，文案才承诺 artifact。不开替代待办，不改跨仓 SOP/registry。预算硬上限 100 行。

各批单独 PR，执行者验证并提交 PR；主脑独立 review、ready、完整 gate 后合并并关闭 issue。
