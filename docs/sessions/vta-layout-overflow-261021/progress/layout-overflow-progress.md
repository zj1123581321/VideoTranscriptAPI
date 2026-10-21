## 里程碑 1：布局回归测试在基线变红
- 当前阶段：implementing
- 本段结论：新增 Playwright 布局测试并以原始生产代码运行，首页最近任务在 1280×800 下因无断行导致页面 `scrollWidth=2608`、`clientWidth=1280` 断言失败，证明测试能捕获原缺陷。
- 关键决策与已否决方案：先验证未修改生产代码的基线红；保留真正的 document 几何断言，不以截图或元素可见性冒充布局判据。
- 下一步唯一动作：落全局文本断行与动作控件基线，再按盘点结果修正遗留窄屏布局。

## 里程碑 2：布局根因修复并完成验证
- 当前阶段：implementation complete，等待范围核查与提交
- 本段结论：两个样式根已统一应用长文本断行和动作控件防压缩基线，首页去重、history 窄屏动作列和第三方文本截断点已处理。`npm run test:browser` 31 项、`npm run test:web` 188 项、`uv run --frozen pytest -q tests/unit/web` 与 `make test` 全部通过；桌面/手机首页截图已写入 `/tmp`。
- 关键决策与已否决方案：长标题/URL 优先完整换行；确有单行列时以 `min-width:0` 和 `title` 保留完整值。TOC 章节标题保留省略号以兼容既有行高契约，同时 hover/focus 展开完整标题，移动吸顶条完整换行显示；不动视觉配色/字号/间距。
- 下一步唯一动作：对 `<base>..HEAD` 执行 `card_scope_check.py` 并据结果收尾。
