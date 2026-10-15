# card-vta-261015-speaker-evidence 进度存档

## 段1：现场核查与设计定稿

- **当前阶段**：implementing（现场核查完成，开始落码）
- **本段结论**：base 95d21bb5 上建分支 card/vta-261015-speaker-evidence；真实 fixture 已入库 `tests/fixtures/twitter_space_1wxWjlzQVwDJQ/transcript_funasr.json`（sha256 cf6346ae4046e75037e36aee6b2cfaae0c33db6d3785bb7e1db0ab768e0986fc，201407 字节，383 段、11 说话人，与卡面附注一致）。裁决设计定稿：evidence_type 域值 {dialog_address, title_credit, description_roster, author_host}；quote 核对对象为最终组装的 user_prompt 全文（`quote in prompt`，不做任何归一化）；裁决顺序 dialog_address+title_credit 复合 > 仅 dialog_address > 其余一律不 applied；description_roster 不独立 applied（程序无法机械验证「与对话内容对应」，保守处理为仅记录佐证，理由见 report）。
- **关键决策与已否决方案**：缓存命中重放按 meta 形状分叉——v2 条目（含 candidates 键）直接采用缓存 mapping/applied（证据无法离线重核，输入文本不在缓存里）；v1 形状保持旧 confidence-gate 重判（= 完成条件④「走旧降级语义」选项）。这使 test_speaker_inferencer.py 既有缓存命中测试（v1 形状 mock）零改动全绿。已否决：v1 产物强制迁移（会破坏既有缓存重判测试，且无行为收益）。
- **下一步唯一动作**：落 schema v2 与 prompt 分区，跑 Narrow-Verify 相关用例。

## 段2：核心实现全部落地，全量测试除继承红外全绿

- **当前阶段**：implementing → 收尾（验证完成，待写报告）
- **本段结论**：六个 commit 完成 schema v2 + prompt 分区（a5a3b48c）、证据裁决/指纹/top2 加额（a3dacad5）、真实 fixture 验收测试 16 条（54f49a25）、消费点同步 + envelope v2（0feb51c0）、集成 seed 同源修复（058b5478）。红验两项均转红后还原：①引用核对判据去掉 quote 成员检查 → test_forged_quote_rejected_to_placeholder 红（AssertionError: '青柠（对话称:某大V）' != '说话人2'）；②指纹 canonical 的 description 字段置空 → test_metadata_change_changes_fingerprint 红（AssertionError: 两个 sha256 相等）。make test 终态：3778 passed / 1 failed（test_asr_monitor_alert_delivery.py::TestNetworkGuard::test_unix_domain_socket_is_not_blocked，AF_UNIX path too long，已在 base 95d21bb5 复现同为红，继承环境红非本卡责任）。
- **关键决策与已否决方案**：卡面 Accept-Check 第 2 条原命令 `uv run python -c "from video_transcript_api..."` 在 base 上同样 ModuleNotFoundError（包不经 pip 安装，tests/conftest.py 注入 sys.path）——等价形式 `PYTHONPATH=src uv run python -c ...` exit 0 通过，记入报告。description_roster 的「quote 与对话内容直接对应」无法机械验证，落地为永不独立 applied（仅佐证记录），report 说明。
- **下一步唯一动作**：写 report.md 并 push 分支。

## 段3：gate 修复轮（dlg-20261015-070200-ce585c）两条 major 修复完成

- **当前阶段**：implementing → gate 修复完成（两条 major 已修，待主脑复审）
- **本段结论**：按主脑续修指令修复 gate primary 第 1 轮采纳的 2 条 major，均在证据核对路径（commit 7dae793f）。①correctness-whitespace-evidence-quote：`_verify_candidates` 加实质内容判据——quote 去首尾空白后长度 ≥2 且至少含一个字母/数字/汉字（`any(ch.isalnum() ...)`），不满足按 quote_missing 作废；②correctness-speaker-evidence-quote-scope：新增 `build_speaker_quote_sections`（prompts/__init__.py，分区文本唯一实现点），`build_speaker_inference_user_prompt` 改为从它取分区文本组装（同源），infer() 同参构建分区映射传入 `_verify_candidates`，quote 逐字核对对象从整个 user_prompt 收窄到 evidence_type 对应分区（dialog_address→转录片段区、title_credit→标题行、author_host→作者行、description_roster→描述行，分区缺失 fail-closed）。红验：两条端到端新测试对旧实现跑红——test_whitespace_or_punctuation_quote_rejected 红（AssertionError: '某大V' != '说话人2'，quote=全角逗号取自真实采样区）、test_cross_section_quote_rejected 红（同型 AssertionError，quote=望舒 仅存在于描述参会名单、前提已探针断言）。终态：Narrow-Verify 63 passed（59 既有 + 4 新）；全量 3998 collected / 1 failed（AF_UNIX path too long，同段2 继承环境红）/ 0 errors；compileall exit 0。major-3（metadata-fingerprint-order）主脑已驳回不改代码（理由见 PR #245「Gate primary 第 1 轮 findings 处置」节）。裁决规则、schema、指纹均未动——只动核对边界。
- **关键决策与已否决方案**：分区文本由 prompts 层单一函数产出、组装与核对两侧共用（手写分界必然漂移）；端到端形态写红测（直接调 `_verify_candidates` 的测试会受签名迁移影响，端到端红验对旧实现真实转红且不受重构波及）。已否决：`build_speaker_inference_user_prompt` 返回 tuple（破坏既有接口与全部调用点）；在核对侧用正则从 user_prompt 反解分区（脆弱且与组装侧形成两套实现）。
- **下一步唯一动作**：push 分支，写 gate 修复轮 report.md 交主脑复审。

## 段4：gate 修复轮第 2 轮（dlg-20261015-080654-4eb5df）：跨说话人借用收窄 + 指纹 spec 锁定

- **当前阶段**：implementing → gate 修复轮第 2 轮完成（三项指令全部落地，待主脑复审）
- **本段结论**：commit 4666fd2a 完成第 2 轮指令三项。①跨说话人借用（quote-scope 二次收窄）：infer 组装 `dialog_sections_by_speaker`（`_render_speaker_segment` 同源渲染，与拼进 prompt 的片段逐字一致），`_apply_evidence_gate` 新增必传 keyword，逐说话人替换 dialog_address 分区；fixture 探针证实 Speaker1 自身片段含「黄柠姐」字样、Speaker2 出场上下文含「柠姐，我邀请你做共同主持人了」——TDD 红验原文：`AssertionError: '柠姐' != '说话人1'`（旧全分区核对把 Speaker2 的称呼借给 Speaker1，与生产投诉同型）；收窄后同一 quote 对归属说话人核对通过（正例对照锁定「出场上下文属归属说话人」语义）。②联合兜住：新测试锁定三类静态行证据全核对通过、无 dialog_address 永不 applied；红验（改坏 `_decide_display_name` 的 credit 分支为放行）转红：`AssertionError: '青柠' != '说话人2'`。③指纹 spec 锁定：新增端到端测试（指纹敏感 fake cache），同元数据命中（calls=1，排除恒真假绿）、title/author/description 各变一次均重算（calls=4）、四次写侧指纹互异；红验（指纹 canonical 删 description 行）转红：`AssertionError: '75e2b66e…' == '75e2b66e…'`，且既有 `test_metadata_change_changes_fingerprint` 同时变红（双层守护确认）。终态：Narrow-Verify 66 passed；链路抽查 test_speaker_artifact 45 passed、test_layered_cache 35 passed、llm_ops 刷新/身份恢复组合 95 passed；全量唯一失败仍为 AF_UNIX path too long 继承环境红；compileall exit 0。裁决规则结构、schema、指纹算法本身均未动。
- **关键决策与已否决方案**：`dialog_sections_by_speaker` 设为必传 keyword（无默认值）——唯一生产调用方是 infer，None 默认分支没有任何第二消费者，保留即反熵条款禁止的无消费者兼容面；映射缺失 speaker 时空分区 fail-closed 与静态分区缺失语义一致。已否决：None 时退回全分区核对（留下「忘传映射即绕过收窄」的静默口径）。另：卡面 Scope-Globs 预设的 tests/unit/test_speaker_mapping_schema.py 实际不存在，schema 测试前轮落点为 test_speaker_artifact.py，report 偏差节说明。
- **下一步唯一动作**：写第 2 轮 report.md，push 后交主脑复审。

## 段5：gate 修复轮第 3 轮①：复合显示名语义显式化

- **当前阶段**：implementing（第 3 轮指令①完成，②③进行中）
- **本段结论**：commit dfb0d440 落地复合名带标注形态：`说话人N｜标题关联推测:青柠｜对话称:柠姐`（author_host 用「作者关联推测」），三要素缺一不可（原始说话人编号、「推测」字样、两条来源名）；`_decide_display_name` 签名扩为 (verified, speaker, speakers) 以取说话人编号；仅 dialog_address 保持原文不标注。`SPEAKER_EVIDENCE_RULES_VERSION` 2→3（显示格式属裁决规则，旧格式缓存经指纹自然失效）。新增测试 7 条：复合名三要素（title/author 两型）、非数字标签位次编号、裸名反例、错误关联端到端反例（真引用+无关联 title_credit → 必带「推测」标注）、网页 HTML 四要素断言、processor 归一化对话（导出/LLM 后续输入上游）原样携带复合名断言。红验方向①「标注缺失」：把 `_decide_display_name` 复合分支返回值改为裸 `credit['name']` 后转红——`AssertionError: '推测' not found in '青柠'`、`AssertionError: '青柠' == '青柠'`（共 4 条红，均为期望-实际对比型）；只还原该行后回绿（test_speaker_evidence_gate.py 30 passed）。Narrow-Verify 合并跑 73 passed；渲染/产物/分层缓存链路 45 passed；compileall exit 0。
- **关键决策与已否决方案**：mapping 值单一事实源——复合名在裁决层一次成型，渲染层零二次加工（网页测试断言原始复合名四要素直接出现在 HTML）；「待确认」badge 的 `^说话人\d+$` 全串锚定不命中复合名，属预期（复合名自带推测标注，无需 badge）。已否决：在 dialog_renderer 加推测角标二次加工（违反 mapping 单一事实源指令）；marker 统一用「标题关联推测」覆盖 author_host（语义不准，作者署名≠标题）。
- **下一步唯一动作**：fixture 合成化（指令②）：编写合成对话替换真实 fixture，原档移出仓至 ~/private-fixtures/VideoTranscriptAPI/，同步更新全部测试常量。

## 段6：gate 修复轮第 3 轮②：fixture 合成化与真实数据出仓

- **当前阶段**：implementing（②完成，③历史重写待做）
- **本段结论**：commit 8b77998e 完成合成化。仓内 `tests/fixtures/twitter_space_1wxWjlzQVwDJQ/transcript_funasr.json` 换成 34 段人工编写合成对话（6 说话人，虚构名：主持人=作者林晚风/对话称风哥、主讲=标题credits青柠/对话称柠姐、名单含仅名单出现的望舒），保留发言顺序/说话人归属/称呼位置/全部测试逐字断言可用性（称呼句在 Speaker1 段内且位于 Speaker2 首次出场前 2 条上下文窗口内）；JSON 顶层键与原档同形并加 synthetic 标记。真实原档（sha256 cf6346ae…8fc，383 段）移出仓至 ~/private-fixtures/VideoTranscriptAPI/twitter_space_1wxWjlzQVwDJQ_transcript_funasr.json（拷贝后 sha256 复核一致）；fixture 目录新增 README.md 说明来源、归档路径与角色对照表。测试常量全部换合成命名（FIXTURE_TITLE/AUTHOR/DESCRIPTION、柠姐→柠姐、青柠→青柠、风哥→风哥、望舒→望舒、小满→小满等），prompts/__init__.py 注释里的真实 Space ID 泛化。红验方向②「合成 fixture 逐字断言失效」：把称呼句「我邀请你」改为「我请你」（一词注入）后转红——`AssertionError: '柠姐，我邀请你做共同主持人了' not found in '[Speaker2]…柠姐，我请你做共同主持人了…'`（test_dialog_quote_borrowed_from_other_speaker_rejected，1 failed / 9 passed）；git checkout 还原该单文件后回绿（30 passed）。终态：Narrow-Verify 73 passed；分层缓存+产物 80 passed；渲染套件 33 passed。
- **关键决策与已否决方案**：目录名 twitter_space_1wxWjlzQVwDJQ 与测试里的 media_id="1wxWjlzQVwDJQ" 保留——Space ID 是公开 URL 标识符，非卡面点名的「昵称/标题/描述/私密内容」，且保留可追溯合成 fixture 建模的生产案例；README 已注记。已否决：把测试断言改成模糊匹配以容忍措辞漂移（会同时放松对 producer 契约的锁定）；在仓内保留真实原档的截断版（截断产物仍是真实内容，不满足出仓要求）。
- **下一步唯一动作**：分支历史重写（指令③）：临时单分支 clone 内用 git filter-repo blob 替换把全部历史中的真实 fixture blob 换成合成版，force push 仅限 card/VideoTranscriptAPI-261015-fix，记录 SHA 映射与残余风险。

## 段7：gate 修复轮第 3 轮③：历史重写完成，force push 被 public-scan 拦下待主脑裁决

- **当前阶段**：implementing → ③本地重写完成、推送被闸拦下（blocked 上行已发）
- **本段结论**：推送前自查发现段6 进度与 fixture README 含 home 目录形态的本地绝对路径（一字面即命中 username 规则）（会命中 public-scan 的 local_absolute_path + username 规则，且扫描按「新提交新增行」判定、后置删行无效），软重置重建 d675221e/9c6a2e51 两 commit（路径改写为 `~/private-fixtures/...`），本地模拟扫描 clean 后增量推送成功：origin/card/VideoTranscriptAPI-261015-fix = 9c6a2e51（ls-remote 核实）。③临时单分支 clone（/tmp/vta-rewrite）内 git filter-repo blob 替换（bf761ae7→合成 blob a7bcc1e8）完成：全部历史 fixture 路径 blob 唯一为合成版、真实 blob 从对象库消失、逐历史内容 grep 柠姐/青柠/林晚风/风哥/望舒/新潮 = 0、重写后 HEAD 树与 worktree 逐字节一致；1237 commit 中 1192 个改写 SHA（fixture 引入前的 45 个根提交不变）。force push 两道闸均拦下：所有权闸按钩子指示 ACK 后放行，public-scan 以 128 条 findings 拒绝（`pre-push public-scan: public content rejected`）——全部命中**重写前已发布的历史内容**：29 个文件、local_absolute_path×42 / username×42 / private_ip×28 / public_path×16（retro/acceptance-log.jsonl、多张卡 HANDOFF.md、SSRF/url 校验测试的有意内网 IP fixture、graphify-out 等），无一来自本卡改动；同一内容在旧 SHA 下早已公开（扫描器按 base 排除祖父化，重写翻新 SHA 后失去祖父资格）。修复面（29 文件跨卡历史内容手术/豁免/scan-off）全部超出执行器权限，按守卫纪律就此停下保留现场。
- **关键决策与已否决方案**：未使用 CC_PRE_PUSH_PUBLIC_SCAN_OFF=1 绕闸——闸报得对（内容确属不应公开类），绕行裁决权归主脑。现场：/tmp/vta-rewrite 内重写分支已就绪（HEAD=0383de4e，即 9c6a2e51 的重写映像），PUSH_GUARD_FINDINGS.log 存 128 条 findings 原文，sha_before2/sha_after2.txt 存全量 SHA 映射；主脑三选一即可完成推送：①授权本次 push 带 CC_PRE_PUSH_PUBLIC_SCAN_OFF=1（内容零新增暴露）②先对 29 文件做同法 blob 手术再重推（工程量大且动他卡产物/测试语义，不建议）③放弃历史重写、改走 GitHub support 清除（重写现场可弃）。
- **下一步唯一动作**：等主脑对 128 条 grandfathered findings 的裁决；裁决后按①直接推 /tmp/vta-rewrite 分支，或按③弃现场。
