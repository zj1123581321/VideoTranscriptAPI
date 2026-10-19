# 阶段进度存档:处理中查看页显示当前处理阶段(vta-stage-progress-261019)

## 里程碑 1:统一阶段入口落在 PerfTracker.track

- **当前阶段**:implementing(入口与入口级测试已落地)
- **本段结论**:`PerfTracker` 新增 `attach_progress_sink` / `report_subprogress`,`track(stage, publish_as=...)` 成为唯一阶段发布点:进入发布 running 文档、退出发布 done/failed 并追加 `stages` 区间;发布失败降级为含 `stage_progress_failed` 字面量的 error 日志,不传播。入口级契约由 `tests/unit/test_task_stage_progress.py::TestStageEntryPublishing`(8 条)锁定,narrow verify 通过。
- **关键决策与已否决方案**:选「PerfTracker 上新增方法/参数」形态而非独立小上下文管理器——第二消费者是 llm_ops worker:`_handle_llm_task` 接手转录 worker 交接的同一个 tracker(notes-only 任务的新 tracker 也在 562 行注入 sink),两个流程共享同一入口才满足「新阶段零额外代码可见」。`publish_as` 参数把观测口径锁死的内部名(`llm_processing`,被 tests/integration/test_task_observability.py 与 scripts/task_observability_report.py 消费)与用户可见阶段名(llm/notes)解耦。否决「业务代码继续直写 update_task_progress」——多写者会互相整份覆盖,回到本卡要根治的散乱状态。
- **下一步唯一动作**:cache_manager.update_task_progress 加终态限定 + stage_progress_sink 绑定工厂,补 TestTerminalStateGuard 测试并做红验②。
