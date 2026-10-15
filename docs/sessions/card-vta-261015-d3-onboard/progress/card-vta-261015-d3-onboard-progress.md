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
