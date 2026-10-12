# A/B/D 交付在新 main（#238 合入后）上的复验

- 派发 dlg-20261012-184341-1ca353，2026-10-13；main=1030776c（#238 已合）。
- 方法：现 accept_precheck.py 按各产品原卡执行，commit-range c7dc7fc..<产品H0>，
  各真实跑一次；verify 由工具把产品分支与 main 合成后执行原卡 Verify-Command。
- 三树 head 相对产品 H0 的差异仅 main(#238 部署测试修复)+各自 imported review verdict，
  无额外 src/e2e/测试变更（git diff 逐一核对）。

## 结果：三项主检查全 green

- A 章节清理（树 vta-261013-chapter-closeout）：H0=ad92f16c，head=f89d3b2c；
  原卡 `TMPDIR=$(mktemp …) make test` 退出码 0（pytest 全套；日志为滚动窗口无计数行，不报数字）。
- B 上传清理（树 vta-261013-upload-closeout）：H0=db60c385，head=4a298983；
  同一 make test 入口退出码 0。
- D 上传临时目录清理（树 vta-261013-upload-tmp-closeout）：H0=c3fbf5d3，head=116dce89；
  原卡 `uv sync --frozen && npm --prefix e2e ci && npm run test:browser` 退出码 0，
  17 passed (13.6s)，17 条 chromium 用例逐条通过（含全链 upload spec）。

## 历史 red 保留与定性

- D 首轮（dlg-20261012-160714-609acc）曾红：`Cannot find module '@playwright/test'`
  （当时 verify 未含 e2e 依赖前置安装）；续修轮 dlg-20261012-175937-903764 保留该首红
  现场、补锁依赖后达成 17 绿（同锁 Playwright 1.62.0 + 缓存 Chromium）。
  该红是当时的环境状态，非现产品缺陷；first-red 的 JSON/log 原样保留、哈希未变。

## 历史与源

- 旧 main（c7dc7fc 时代）三份 green 预检 JSON 与 verify log 已先做 hash 快照保留，避免覆盖丢据。
- 父源 JSON：三个原产品 dispatch 的 state 目录各 accept_precheck.json；本轮三者
  main_sha_at_check 均=1030776c、head_sha 均=对应产品 H0、verify exit 0。
- advisory（仅线索，不参与判定）：A ci=unknown（无匹配 PR，查询分支与范围端点不同源）；
  B/D ci 字段 green 但 gate primary 等为 skip（draft 期假绿机理），不作为完整 CI 结论。
- 未知：无新增。
