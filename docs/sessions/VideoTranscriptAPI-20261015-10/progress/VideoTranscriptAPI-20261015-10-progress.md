# VideoTranscriptAPI-20261015-10 progress（card/VideoTranscriptAPI-261015-diag）

## 段 1：Tailscale 误判回退 + SSH host key 诊断注入

- **当前阶段**：implementing-done（Accept-Check 三项全过，待 CI）
- **本段结论**：
  - 回退 7e264917 引入的两处「Connect to Tailscale」step（pre-flight 与 verify-busy-lock-inode 各 7 行，共 14 行全部移除，含注释）。根因误判：fleet runner 宿主自带 tailscaled、经宿主路由直达 n305，github-action 在 runner 内找不到本地 tailscaled 必败（run 38840253574 实测 `failed to connect to local tailscaled`）；live-recorder 历次 ship 的同名步骤带 `if: inputs.runner == 'hosted'` 在 self 下被跳过，从未实跑。ship 的 `TS_AUTHKEY` secret 传递保留（ci-templates 的 hosted 分支仍消费）。
  - pre-flight「Pre-flight busy.lock host/container inode」step 注入诊断：SSH_OPTS 追加 `-v`；ssh 调用包进 `if !` 结构，失败路径先输出诊断块（known_hosts 条目数、`ssh-keygen -lf` 本地指纹、`ssh-keyscan -T 10 100.68.21.80 | ssh-keygen -lf -` 远端实际指纹、`ls -la ~/.ssh/`）再 `exit 1`；注释 `# TEMP DIAGNOSTIC (run 38834509231 Host key verification failed)` 标记为临时手段，根因确认后由后续轮次移除。
  - verify job 三个 SSH step（identity 对账 / inode 对账 / rollback）SSH_OPTS 同步追加 `-v`（行尾 diag 注释，不含 TEMP DIAGNOSTIC 关键词以满足 grep 计数=1）；诊断块只放 pre-flight 一处，避免重复噪音。
- **验证**：`grep -c "tailscale" .github/workflows/deploy.yml` = 0；`grep -c "TEMP DIAGNOSTIC"` = 1；`yaml.safe_load` ok；workflow 全部 6 个 run 块 `bash -n` 语法通过。diff 13 insertions / 19 deletions（32 行 < target 40）。零测试耦合（卡面相关测试：无），Accept-Check 为静态判据无需红验。
- **关键决策与已否决方案**：按卡面锁定决策 1-4 执行，无新增自定决策。已否决（卡面给定）：保留 Tailscale 步骤并修 github-action——fleet runner 靠宿主级 tailscale 路由，runner 内无本地 tailscaled 是环境常态。
- **下一步唯一动作**：commit + push + 开 PR，等 CI 与主脑验收。
