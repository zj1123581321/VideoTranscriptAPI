# 阶段进度存档:处理中查看页显示当前处理阶段(vta-stage-progress-261019)

## 里程碑 1:统一阶段入口落在 PerfTracker.track

- **当前阶段**:implementing(入口与入口级测试已落地)
- **本段结论**:`PerfTracker` 新增 `attach_progress_sink` / `report_subprogress`,`track(stage, publish_as=...)` 成为唯一阶段发布点:进入发布 running 文档、退出发布 done/failed 并追加 `stages` 区间;发布失败降级为含 `stage_progress_failed` 字面量的 error 日志,不传播。入口级契约由 `tests/unit/test_task_stage_progress.py::TestStageEntryPublishing`(8 条)锁定,narrow verify 通过。
- **关键决策与已否决方案**:选「PerfTracker 上新增方法/参数」形态而非独立小上下文管理器——第二消费者是 llm_ops worker:`_handle_llm_task` 接手转录 worker 交接的同一个 tracker(notes-only 任务的新 tracker 也在 562 行注入 sink),两个流程共享同一入口才满足「新阶段零额外代码可见」。`publish_as` 参数把观测口径锁死的内部名(`llm_processing`,被 tests/integration/test_task_observability.py 与 scripts/task_observability_report.py 消费)与用户可见阶段名(llm/notes)解耦。否决「业务代码继续直写 update_task_progress」——多写者会互相整份覆盖,回到本卡要根治的散乱状态。
- **下一步唯一动作**:cache_manager.update_task_progress 加终态限定 + stage_progress_sink 绑定工厂,补 TestTerminalStateGuard 测试并做红验②。

## 里程碑 2:progress 写入的终态黏性 + sink 绑定工厂

- **当前阶段**:implementing(持久层契约已落地)
- **本段结论**:`update_task_progress` 的 UPDATE 加 `AND status NOT IN ('success','failed')` 终态限定;新增 `CacheManager.stage_progress_sink(task_id)` 作为入口到持久层的唯一绑定(业务代码不再直写 progress 文档)。notes 运行时任务 status 已核实为 `processing`(tasks.py:1350 INSERT 'processing',notes 路径无 CALIBRATING 写入,终态只在 finalize 时写)——终态限定不破坏 notes done/total 契约(锁定决策 5 的疑问消除)。既有测试 `test_updates_only_progress_without_touching_status_fields` 原本锁死「终态行可写 progress」,按本卡决策 5 改写为新契约并补 `test_terminal_row_rejects_progress_overwrite`。
- **关键决策与已否决方案**:否决「update_task_progress 返回 True 时清空 progress 列」——终态后 progress 保留在行里,/api/task 原样透出是卡面非目标外的既有行为;查看页按生命周期状态过滤(决策 6)即可,不动 API 外形。
- **下一步唯一动作**:i18n 词表 + resolver 阶段展示 + processing.html 渲染。

## 里程碑 3:i18n 词表 + resolver 展示 + 模板渲染

- **当前阶段**:implementing(用户可见面已接通,业务接线未做)
- **本段结论**:两份词表新增 `web.processing.stage.*`/`web.processing.progress.*`/`web.processing.duration.*` 共 13 键;`view_token_resolver` 的 processing 分支把 progress TEXT 解析后经 `build_stage_progress_display` 转成整行展示文本(current_line/notes_line/completed_header/completed_items),views.py 无需改动(`**view_data` 自动透传);processing.html 加 `.stage-progress` 块。瞬时阶段(url_parse/cache_check/metadata)在页面归入「准备」,不单独成步;无词表条目的新阶段以内部名直接上页(零额外代码可见性的展示侧保障),由 test_new_stage_without_catalog_entry_still_renders 锁定。
- **关键决策与已否决方案**:展示文本在 resolver 侧预渲染(而非模板里做 i18n 逻辑)——Jinja 模板与浏览器夹具(tests/browser_server.py 直渲染模板)只面对最终文本,契约最窄。done/total 只在 notes 阶段 running 时发布,阶段退出即清(过期计数不该在完成后显示),transcript.html 前端轮询窗口与 notes 运行窗口重合,契约不破坏(vitest 12 条原样通过)。
- **下一步唯一动作**:transcription.py/llm_ops.py 接线 + 从 process_transcription 生产入口驱动的端到端断言测试 + 红验①。


