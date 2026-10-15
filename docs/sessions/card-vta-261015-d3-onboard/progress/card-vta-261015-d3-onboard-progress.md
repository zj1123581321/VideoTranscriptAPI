# card-vta-261015-d3-onboard 进度

Task-Id: VideoTranscriptAPI-20261015-01 · dispatch: dlg-20261015-151234-61378b · 卡类型: glue-scaffold (M)

## 段1：调研与 deploy.yml 落盘

- 当前阶段：implementing（deploy.yml 已随本段提交）
- 本段结论：ci-templates v2 tag 的 build-deploy.yml inputs 与本地 clone HEAD 一致，参数全部按 live-recorder 先例落盘；pull_and_deploy.sh 对部署目录 compose 的期望确认为「本地 tag 形态」，digest-env 种子必须迁移，方向与卡面一致。deploy.yml：main 分支 + paths-ignore 照抄 live-recorder、`/livez` 探针、warmup 20 / interval 3、显式 `runner: self`、无忙锁开关。
- 关键决策与已否决方案：① 显式写 `runner: self` 而非留默认（否决「留空靠默认」：一行换免疫上游默认漂移，卡面目标 runner=self-hosted 直接可 grep；附带事实：v2 build-deploy.yml 第 223 行 `if: inputs.runner == 'hosted'`，self 形态跳过临时入网步骤）；② 忙锁相关字样在 deploy.yml 注释里只用中文「忙锁」（Accept-Check 要求 `grep -c "busy_lock"` 为 0，注释里也不能出现下划线形态）；③ warmup=20 = 2×生产 startup ~10s，interval 保持默认 3，5 次探针末次 ~35s 覆盖 healthy 上界 25s。
- 证据（v2 tag 原文摘录，2026-10-15，tag 随上游移动、验收时不必然可重取）：
  - `git show v2:.github/workflows/build-deploy.yml`：`busy_lock_file` default `""`（86-88 行）、`healthcheck_warmup` default `"10"`（70-72）、`healthcheck_interval` default `"3"`（66-68）、`runner` default `"self"`（103-114 行）。
  - `ci-templates/scripts/pull_and_deploy.sh`：22 行 `# local tag, e.g. ops-dispatcher`；339 行 `"$DOCKER_BIN" tag "$ref" "${IMAGE_NAME}:latest"`（拉 ACR 的 GIT_SHA tag 后本机 retag）；460 行镜像对账 inspect `"${IMAGE_NAME}:latest"`。
- 下一步唯一动作：更新 docker/DEPLOY.md（D3 主链路 + /livez 理由 + 旧脚本降为手动备用）。

## 段2：compose 种子迁移到本地 tag 形态

- 当前阶段：implementing（docker/docker-compose.deploy.yml 已随本段提交）
- 本段结论：镜像行从 digest env 占位改为 `image: video-transcript-api:latest`，头部注释改写为 D3 本地 tag 形态的来源说明（retag + 对账都认本地名），其余字节不变（env_file/ports/stop_grace_period/volumes 等均保持原样）；`docker compose config -q` 按服务器真实布局（种子拷为项目根 docker-compose.yml + 同目录 .env）验证通过。
- 关键决策与已否决方案：本地验证不用仓内路径直接跑（compose 的 env_file 相对路径按项目目录解析，仓内无 .env 会假红）——用临时目录复刻部署目录布局，跑完即删；否决「顺手给种子加 compose healthcheck 块」：Dockerfile 已有内置 HEALTHCHECK（curl /livez），宿主侧探针由 ci-templates 脚本承担，再加一层是无第二消费者的重复配置。
- 下一步唯一动作：更新 docker/DEPLOY.md。

## 段3：DEPLOY.md 更新与 Narrow-Verify

- 当前阶段：implementing（DEPLOY.md 已随本段提交）
- 本段结论：DEPLOY.md 新增「D3 自动部署（主链路）」节（链路、/livez 选型理由、忙锁属第二阶段、部署目录 compose 形态前置条件），旧两脚本节降为「手动部署（备用）」；Narrow-Verify 全绿：两个 YAML parse ok，`docker compose config -q` 在临时目录复刻服务器布局下通过。
- 关键决策与已否决方案：否决「在 DEPLOY.md 里写死主脑后续迁移步骤/时间点」——文档只写不随时间过期的形态约束（本地 tag 形态前置条件），迁移执行主体留给主脑会话。
- 下一步唯一动作：跑 make test 全量基线验证 + 红验，然后 push 开 PR。

## 段4：基线验证暴露种子双消费者冲突（阻塞上行）

- 当前阶段：implementing（产物已全部落盘；发现卡面未交代的结构性冲突，已如实上报待主脑仲裁）
- 本段结论：make test 出现 13 个非卡面已知清单的失败（tests/deployment/test_pull_and_deploy.py）；单变量 A/B 钉死根因是本卡锁定决策①（种子迁本地 tag）：旧 `docker/pull_and_deploy.sh` 把同目录种子当部署目录自迁移模板（121-135 行），要求模板渲染出候选 digest，只在 digest-env 形态下成立。种子文件被新旧两条链路要求互斥形态，卡面范围内（禁改 tests/、禁改旧脚本）无双绿解。决策：保持锁定决策与 Accept-Check 闸，新红如实上报；DEPLOY.md 手动备用节已补写形态耦合事实。
- 关键决策与已否决方案：否决「回退种子保 make test 绿」——那会让 D3 首次部署在镜像对账处必挂，卡片目标整体落空；否决「顺手改 tests/ 跳过旧脚本测试」——越出禁止边界。
- 证据（单变量 A/B，2026-10-15，仅切换种子文件其余不动）：
  - base 版种子（digest-env）：`uv run pytest -q tests/deployment/test_pull_and_deploy.py -p no:warnings --tb=no` → `...................                                                      [100%]`（19 passed）
  - 本卡种子（本地 tag）：同命令 → `FAILED tests/deployment/test_pull_and_deploy.py::test_legacy_image_without_docker_health_uses_api_probe` 等 13 个 FAILED（完整清单见 report.md）
  - 旧脚本判据原文（docker/pull_and_deploy.sh:121-135）：`rendered_image != CANDIDATE_DIGEST` → 换用 `${SCRIPT_DIR}/docker-compose.deploy.yml` 重写后再验，仍不等则 `[ERROR] Migrated compose file does not render the candidate digest.` exit 1
- 下一步唯一动作：push 分支开 PR，正文单独列出继承红与新红，等主脑验收仲裁。

## 段5：push 被 public-scan 拦截，去掉明文用户名后重推

- 当前阶段：implementing（deploy.yml 去掉部署账号显式项，重推中）
- 本段结论：首次 push 被 pre-push public-scan 闸拦——扫描器在 deploy.yml 第 27 行命中身份类明文模式（命中原文不在本文引用，以免本文件再次触发同一扫描模式，详见 report.md）；处理方式是删掉该行——ci-templates v2 该 input 默认值与被删值相同（v2 build-deploy.yml inputs 21-24 行），行为完全等价，非闸绕过；未使用环境变量旁路开关。
- 关键决策与已否决方案：否决「开扫描旁路环境变量」——闸绕行需主脑批准，本卡无授权；否决「注释里保留该身份值说明」——扫描按模式匹配，注释同样可能命中，净删最稳；本段措辞也刻意避开命中字面量（第一次重推即因此再被拦，同文件第 43 行，已二次改写）。
- 下一步唯一动作：重推并开 PR。

## 段6：主脑仲裁落地——旧手动链路退役（续修卡 dlg-20261015-160700-3a051b）

- 当前阶段：implementing（仲裁结论已落地，验证全绿）
- 本段结论：主脑仲裁接受种子迁本地 tag 形态（锁定决策①维持），旧手动链路退役；解除禁改 docker/pull_and_deploy.sh 与 tests/deployment/**。已执行：删除 docker/pull_and_deploy.sh（285 行）；test_pull_and_deploy.py 改名 test_push_to_ghcr.py，删全部 pull 脚本测试与只为它们服务的 fixture（_fake_docker/_run 等），保留 3 个非 pull 脚本守卫；test_healthcheck_route.py 删 legacy fallback 探测对齐测试（无孤立 import 产生）；README 生产部署节收窄为 push_to_ghcr + D3 指向；DEPLOY.md 旧链路节标注退役并补部署目录灾备兜底（docker compose pull && docker compose up -d）。make test 全量：唯一红为 AF_UNIX 继承红，上卡 13 个新红全部消失。
- 关键决策与已否决方案：①保留测试不止指令点名的 test_build_script_uses_only_git_sha_tag，还保留 test_compose_template_uses_legacy_compatible_env_file_syntax 与 test_compose_template_sets_stop_grace_period——两者测的是种子 compose 文件静态形态（env_file 语法、优雅关闭预算），不测 pull 脚本行为且在新形态下仍绿，属「非 pull 脚本测试」，不在「删除全部 pull 脚本测试」范围内；②文件名采纳指令建议 test_push_to_ghcr.py（docstring 已说明覆盖范围：push 构建脚本守卫 + 种子模板守卫）；③README 除指令点名的 92 行命令外，同步收窄 87 行段落与 95 行大段——脚本删除后该段全是对已删行为的悬空描述，按反熵条款改事实而非留假引用。tests/README.md 无该文件引用，无需同步。
- 证据（2026-10-15，随本段提交 @ 889671d2 后重取）：`make test` FAILED 清单仅 `FAILED tests/unit/test_asr_monitor_alert_delivery.py::TestNetworkGuard::test_unix_domain_socket_is_not_blocked`；`ls docker/pull_and_deploy.sh` → No such file or directory；tests/deployment 套件 4 项全绿；README/DEPLOY/tests 无 pull_and_deploy 活引用（仅 DEPLOY.md 退役声明与测试 docstring 背景两处史实陈述）。
- 下一步唯一动作：push 更新 PR #246，正文「仲裁请求」节改为裁决结果。

## 段7：gate primary 两条 major 裁决落地（续修卡 dlg-20261015-163618-62a47e）

- 当前阶段：implementing（两条 finding 均采纳、就地修复完成，验证全绿）
- 本段结论：①deploy.yml 直接带忙锁参数（busy_lock_file=/opt/media/VideoTranscriptAPI/.deploy-state/busy.lock、timeout 600），顶部注释改为「忙锁已启用，服务侧持锁由卡 VideoTranscriptAPI-20261015-02 落地，落地前锁文件由部署脚本自动创建、门禁空转」；②DEPLOY.md 灾备兜底修正——删去错误命令 docker compose pull（本地 tag 形态下会去 registry 找不存在的同名镜像），改为日常灾备 docker compose up -d（宿主已有本地 tag）+ 钉版命令（ACR 全路径拉 SHA 后 docker tag 到本地 tag）；D3 节忙锁状态句同步为已启用/空转现状。
- 关键决策与已否决方案：裁决依据已独立核实——v2 tag pull_and_deploy.sh 684-689 行：锁文件缺失时 log WARN + mkdir -p + 创建空文件后继续（设计内降级，服务侧持锁上线后自动生效）；ACR 全路径按 build-deploy.yml 组装规则 ACR_REGISTRY/ACR_NAMESPACE/IMAGE_NAME 推出（本卡未覆盖两个默认 input）；否决「DEPLOY.md 只改命令不动 D3 节忙锁句」——原句「自动部署不感知在飞任务」与启用后现实矛盾，属同一事实的文档面。
- 证据（2026-10-15）：yaml parse ok；Accept-Check 新口径 busy_lock_file=1、livez=1、本地 tag=1、digest env=0；DEPLOY.md 无 compose pull && 残留；tests/ 无任何测试读取 deploy.yml/DEPLOY.md（仅引用未改动的 docker-compose.deploy.yml）——make test 不重跑全量的理由：本轮 diff 零测试耦合，上轮全量基线（唯一红 AF_UNIX）输入文件均未动。
- 下一步唯一动作：push 更新 PR #246 正文（差异表忙锁行、验证口径、后续节）。

## 段8：gate primary 第 3 轮裁决（续修卡 dlg-20261015-180253-09c8dc）

- 当前阶段：implementing（deploy.yml post-deploy inode 对账 + README 本地 latest 别名措辞已落盘）
- 本段结论：主脑将 reliability-deploy-during-active-task 拆两半——(a) 挂载/权限异常静默降级采纳修复：ship 成功后 `verify-busy-lock-inode` 对账宿主 `.deploy-state/busy.lock` 与容器 `/app/.deploy-state/busy.lock` 的 `stat -c %i` inode，不一致或缺失则 workflow failure；(b) 首次自动部署空档走答辩不入码（旧容器无持锁代码，任何新代码都无法让旧进程持锁；缓解=首次部署由主脑 workflow_dispatch，触发前确认非终态任务为 0，见 #249）。minor finding design-production-latest-policy-contradiction：README 把 registry 可变 tag 禁令与部署机本地 retag 别名分开写。
- 关键决策与已否决方案：reusable workflow 无法在 caller 插入「同一 TCP 会话、探针之前」的步骤，验证只能做 ship 成功后的 sibling job（同一 host/key/deploy_dir，新会话）。否决改 ci-templates（跨仓）。否决在本公开仓写部署账号字面量（public-scan）；ssh_user 运行时从 ci-templates v2 default 解析。
- 下一步唯一动作：yaml parse + Accept-Check（busy_lock_file≥1、stat -c %i 可 grep），commit 本段，push 并更新 PR 正文。
