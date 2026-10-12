<!-- delegate-outcome: succeeded -->

## Verdict

**FAIL；P2 一条，阻断本卡验收。** 信号断言有效，但候选实际使用新摘要这一前置不变式未被锁住。

failure-visibility: p2-only

## 冻结范围

- Base `c7dc7fcbb1727057ecf2c4d8c3f38e34d3136f72`；H0 `3953154805704284d5436a87a624e0bf1b8991cb`。
- 完整审查 `base..H0`：仅 `tests/deployment/test_pull_and_deploy.py`，69 行增删；H0 文件 498 行。
- 独立检查脚本、fake Docker、调用参数/环境、健康文件、状态文件和事件顺序；审查中未改测试或生产文件。

## OCR

- `ocr-review`：`status=skipped`、`reason=no_reviewable_items`、`coverage=none`；envelope 未提供 report。按 skipped 记录，不视为 clean。

## 验证

- H0 scratch 私有 `.venv`（`uv sync --locked --group dev`）运行 `python -m pytest -q -s --basetemp=... tests/deployment/test_pull_and_deploy.py`：exit 0，19/19 用例通过；`git diff --check base H0` 通过。
- H0 实际模块 `__file__`、cwd 与 `SCRIPT` 均指向同一 H0 scratch；生产脚本 SHA-256 `1d98c3eb9a2f5c6e4e4714b5c54d0915645ff1ae08a834ef7f065eb81d1d5db1`。fake Docker 消费到候选摘要 `a…a` 的 up、健康探测、旧摘要 `b…b` 的回滚 up；健康文件最终为 `healthy`，`.deploy-image` 原始字节为旧摘要加换行。
- 三个要求的 H0 变异均由目标断言转红：删测试 TERM、删脚本初始 TERM trap、初始忽略 TERM；失败点均为 `old digest rollback up did not run`，未出现健康失败 stderr。删除测试 TERM 时健康仍为 `starting`、5 次探测、状态仍旧，测试超时杀进程 rc `-9`；删除 trap 时进程 rc `-15`；忽略 TERM 时测试超时杀进程 rc `-9`。
- Base 上仅删原测试 TERM 的已知否样本独立转红：断言 `process.returncode != 0` 实测为 `0`；仅候选 up，健康为 `healthy`，状态写成候选摘要。

## Finding

- 无 P1 或 P3 finding。
- **P2 — `tests/deployment/test_pull_and_deploy.py:221-258`。** 首轮 up 只按“出现 up 行”认作候选，断言只核对第二轮旧摘要；没有核对首轮实际摘要。将生产脚本首轮 `deploy_digest(CANDIDATE_DIGEST)` 变异为 `deploy_digest(OLD_DIGEST)` 后，目标测试仍 1 passed、脚本 rc 143，且两轮 up 都使用旧摘要。结果是“候选已启动后信号回滚”的测试会在服务从未切到新候选时假绿，违反本卡候选启动不变式。此 P2 阻断本卡验收，因为被审测试没有证明其核心前置条件；不是把严重度直接等同于阻断。

## 未知与现场

- 派发卡注明主干基线查询不可用；继承红未能判定。
- `pickup-brief.sh` 在自身第 187 行报 Python `SyntaxError`；直接 Git 巡检未发现本审查树的遗留改动。OCR skipped 与 CI 基线不可用均单独保留。
