# 部署流程与入口链路

## D3 自动部署（主链路）

push `main` 后自动完成构建与部署：`.github/workflows/deploy.yml` 调用 `zlxlabs/ci-templates` 的 `build-deploy.yml@v2`（self-hosted runner）：构建镜像（`docker/Dockerfile`，构建上下文为仓根）→ 推送 ACR（不可变 12 位短 SHA tag）→ SSH 到 n305 → 健康探针通过后在部署目录 `/opt/media/VideoTranscriptAPI` 按本地 tag `video-transcript-api:latest` 切换容器，探针失败自动回滚上一健康版本。`paths-ignore` 排除 `**.md`、`docs/**`、`.github/**`——只改文档或 CI 不扇出生产部署；workflow 自身修复后用 `workflow_dispatch` 手动补发。

- 健康探针用 `http://localhost:8200/livez`（宿主 8200 → 容器 8000），不用 `/health`：`/livez` 是纯存活探针、恒 200、不依赖下游，专为部署探针设计；`/health` 的深度检查依赖转写后端等下游服务，下游抖动会把健康的新版本误判为不健康并触发无谓回滚。
- 在飞任务保护（忙锁门禁）已在 workflow 启用（`busy_lock_file` 指向部署目录 `.deploy-state/busy.lock`，超时 600s 延期）：服务侧持锁由卡 VideoTranscriptAPI-20261015-02 落地（BusyLock + compose 挂载）；落地前锁文件由部署脚本自动创建（WARN 后继续，门禁空转）——部署窗口仍需人工确认无长转写任务（事故背景：2026-10-15 手动部署打断在飞转写任务）。
- 部署目录的 compose 必须与本仓种子同形态（本地 tag）：ci-templates 部署脚本从 ACR 拉取不可变 SHA 镜像后在本机 retag 成 `video-transcript-api:latest`，镜像对账也认这个本地名；旧的 digest-env 形态（registry digest env 占位）与之不兼容，首次自动部署前需先确认部署目录已换成本仓种子。

## 旧手动链路（已退役）

接入 D3 前的手动部署脚本 `docker/pull_and_deploy.sh` 已于 2026-10-15 删除：它以同目录种子为模板做部署目录自迁移，要求 digest-env 形态，与 D3 的本地 tag 形态种子互斥，D3 上位后失去存在意义（锁旧脚本行为的测试随退）。`docker/push_to_ghcr.sh` 保留，仅作 ghcr 公开镜像构建口：从干净主干构建 `ghcr.io/<owner>/video-transcript-api:<主干12位短SHA>` 并推送，不部署。

自动链路不可用时的灾备兜底（在部署目录手工执行，不再依赖仓内脚本；部署目标见 `docker/deploy_targets.json`）。日常灾备直接重建容器（compose 用宿主已有的本地 tag `video-transcript-api:latest`，该 tag 由每次 D3 部署 retag 维持；**不要用 `docker compose pull`**——本地 tag 形态下它会去 registry 找名为 `video-transcript-api` 的镜像，不存在）：

```bash
docker compose up -d
```

需要钉定版本时，从 ACR 手动拉取指定 SHA 并 retag 到本地 tag（ACR 全路径 = ci-templates 默认 registry/namespace + `image_name`，与本卡 deploy.yml 的实际值一致）：

```bash
docker pull crpi-0vsre5argteykh9m.cn-guangzhou.personal.cr.aliyuncs.com/zlx-personal/video-transcript-api:<git-sha> \
  && docker tag crpi-0vsre5argteykh9m.cn-guangzhou.personal.cr.aliyuncs.com/zlx-personal/video-transcript-api:<git-sha> video-transcript-api:latest \
  && docker compose up -d
```

入口地址、Tailscale 直连信息等基础设施细节维护在私有部署记忆中，不写入本公开仓。

## 入口分层与 Cloudflare 请求体上限

公网入口经 Cloudflare 代理（Tunnel），**单请求 body 受 Cloudflare 套餐上限约束，超限的请求在边缘即被拒绝，不会到达源站**：

| Cloudflare 套餐 | 单请求 body 上限 |
| --- | --- |
| Free / Pro | 100 MB |
| Business | 200 MB |
| Enterprise | 默认 500 MB（可申请调整） |

2026-10-10 在公网入口实测：50 MB POST 正常穿过边缘到达源站（返回鉴权 401 JSON）；110 MB POST 被边缘直接返回 **HTML 413**（响应带 `server: cloudflare` 与 `cf-ray`），源站日志与数据库均无痕迹。

**实际可上传大小 = min(服务端 `upload_limits.max_file_mib`，入口链路上限)。** 需要上传大文件时使用不经 Cloudflare 代理的直连入口（VPN/内网直达源站端口，地址见私有部署记忆）；分块上传在本项目设计中明确排除。

前端表现：边缘 HTML 413 会被期望 JSON 的代码解析为 `Unexpected token '<'`，上传停在"状态待核实"；此时按契约只查询原 idempotency key 的回执、不重发文件体。判别方法：带 `cf-ray` 头的 4xx/5xx HTML 来自 Cloudflare 边缘而非应用。

## 浏览器安全上下文

`crypto.randomUUID()` 等 Web API 仅在安全上下文（HTTPS 或 `localhost`）可用。经纯 HTTP 直连入口打开页面时，上传幂等键生成已回退到 `crypto.getRandomValues` 手工构造 UUID v4（PR #218；`getRandomValues` 在非安全上下文同样可用）。新增入口形态前，先核对 secure-context-only API 清单。

## 上传功能开关与限额

- 开关 `VTA_UPLOADS_ENABLED`：部署域环境变量，经 env_file 注入、位于数据卷之外；缺失或非精确小写 `true` 即整体关闭。恢复数据卷不得覆盖该开关。
- 限额 `storage.upload_limits`（`max_file_mib` / `max_media_hours` / `receive_concurrency` / `upload_temp_budget_mib`）：**四项任一缺失或非法时，上传整体 503 拒绝**（fail-closed），不存在"部分限额"或无上限默认值。
