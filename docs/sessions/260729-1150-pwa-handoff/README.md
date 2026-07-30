# Session 交接：PWA 化实施（feat/pwa-installable）

> **实施完成记录（2026-07-29 15:30）**：T1-T9 全部落地，worktree `../VideoTranscriptAPI-pwa`
> 分支 `feat/pwa-installable` 共 13 个 commit（3 功能 + 10 轮 Codex review 修复），未 push。
> Codex review 循环共 10 轮：8 个 P1（含 3 个 XSS 链）全修，P2/P3 修 15 条、接受不修 5 条
> （backlog 见 docs/guides/pwa.md）；第 8 轮达上限仍有 P1，经用户授权追加 2 轮，最终轮无 P1。
> 测试：pytest 2664 passed、vitest 47 passed。剩余：docs/guides/pwa.md 手测清单 13 项需真实浏览器验证；
> 图标当前用候选 1（更换：`uv run python scripts/generate_pwa_icons.py --candidate 2|3`）。
> 与 pwa.md 的落地偏差均已回写 pwa.md 实施注记（standalone 不自动跳转、E5 跟踪持久化、T6 Verify 更新）。

生成时间：2026-07-29 11:50（CST）
上游评审：/plan-ceo-review → /plan-eng-review → /plan-design-review（全部 CLEAR，0 未决项）
目标分支：`feat/pwa-installable`（从最新 `main` 切出）+ **独立 git worktree**（强制）

---

## 新 Session 交接 Prompt（直接粘贴使用）

```text
请阅读 docs/designs/pwa.md（已三轮评审定稿的 PWA 设计文档，含 GSTACK REVIEW REPORT），
按其中 "Implementation Tasks" 的 T1-T9 依赖顺序实施 Web 端 PWA 化。

【强制约束】
1. 所有更改必须在独立 worktree 中执行，不得在现有工作区直接改：
   git worktree add ../VideoTranscriptAPI-pwa -b feat/pwa-installable main
   之后所有操作 cd 到 ../VideoTranscriptAPI-pwa 进行。
2. 严格遵守 docs/designs/pwa.md 中的既定决策，不要重新争论已裁决项
   （manifest 关键取值、SW fetch 白名单、E5 契约判定读 body data.status、
   测试文件放 src/web/tests/ 而非 static 下、分 3 阶段 commit）。
3. 分 3 阶段 commit：commit 1 = 最小可安装壳（T1-T5），commit 2 = E4 分享接收（T7），
   commit 3 = E5 通知（T8）。每个 commit 独立可回滚。commit 前先告诉我。
4. 每完成一个任务勾选 pwa.md 里对应的 checkbox。
5. 过程中用中文沟通，console 输出优先英文；遵循 AGENTS.md。

【关键事实（已验证，不要再花时间重新论证）】
- GET /api/task/{id} 对 failed 任务返回 HTTP 200，body 里 code=500、data.status='failed'；
  E5 轮询终态判定必须读 body 的 data.status。
- /add_task_by_web（views.py:742）匿名吐 index.html，是统一入口；
  manifest 的 start_url / share_target.action / shortcuts 一律用它。
- manifest 必须有 display: standalone 和 share_target.action（缺了功能直接不生效）。
- GET /sw.js 根路由必须匿名可访问且显式返回 Cache-Control: no-cache。
- history.html 不加载 app.js、没有 APIManager，E5 只在 index 页激活。
- 图标由 scripts/generate_pwa_icons.py 生成 3 个候选，先给我挑再继续。

【完成定义】
- uv run pytest tests/unit -k sw 绿；npx vitest run 绿；
- 手测清单（docs/designs/pwa.md 评审记录 + ~/.gstack 下 test-plan）逐项过；
- 手测清单里需要真实浏览器的项列出来给我逐项确认。

先跑 uv run pytest tests/unit 确认基线绿，再开工。如有与 pwa.md 冲突的发现，先停下来问我。
```

---

## 背景摘要（给新 session 的补充上下文，可不粘）

- 评审链结论：CEO（选择性扩展，E1-E5 全接受）+ ENG（6 findings 全并入）+
  DESIGN（6/10 → 9/10）三 CLEAR；outside voice 两轮 21 条全部裁决并入。
- 范围：基线 PWA 壳 + E1 安装按钮 + E2 品牌视觉 + E3 shortcuts + E4 分享接收（仅 Android）+ E5 简化版通知。
- 明确不做：离线兜底、认证改造、Web Push 后端（TODOS P2）、vitest 进 CI（TODOS P3）、DESIGN.md（TODOS P3）。
- 相关产物：
  - 设计文档：`docs/designs/pwa.md`（唯一权威，任务 checkbox 在里面）
  - 测试计划：`~/.gstack/projects/zlxlabs-VideoTranscriptAPI/zlx-feat-pwa-installable-eng-review-test-plan-20260729-111011.md`
  - CEO Plan 原件：`~/.gstack/projects/zlxlabs-VideoTranscriptAPI/ceo-plans/2026-07-28-pwa-installable.md`（status: PROMOTED）
- 注意：当前工作区在 `feat/notes-parallel-flash` 分支上，有 notes 相关工作；
  这就是必须用 worktree 物理隔离的原因。
