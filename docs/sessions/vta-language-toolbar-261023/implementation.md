# Language toolbar implementation

- 将公开页语言链接、转录页齿轮菜单和主题按钮放入 header 右上 flex 行；站内导航仍在下一行，标题处于工具栏下方。
- 保留语言链接、lang、aria-current、aria-label 和 query；转录页齿轮仍提供原导航与访问令牌动作，主题与语言切换可操作。
- 同步 `result.txt` 中原有主题图标位置，匹配齿轮菜单先于主题按钮的新可见顺序；未改文案或比较器。
- 基线红验：`VTA_BROWSER_PORT=48291 npx playwright test --grep "public share toolbar stays clear"` 在真实 Chromium 中因 `.header-actions` 不存在而断言失败。
- 验证：`npm run test:web` 通过，15 个文件 / 188 个测试；`npm run test:browser` 通过，34 个 Chromium 测试。
- 窄回归：`uv run pytest tests/unit/i18n_web -q` 通过，23 个测试。
- 截图：`data/vta-language-toolbar-261023/{desktop,mobile}-{closed,open}.png`。
- 依赖审计：根 lockfile 安装后 npm 报告依赖树有 6 项安全告警；本次未改依赖。

### 新增测试判据

- e2e/tests/i18n.spec.ts：改坏 src/web/templates/base.html 的工具顺序、标题间距或语言 query 会红；对应卡面「375px/1280px 中英界面无重叠和横向溢出、标题在工具栏下方、齿轮/主题/语言可操作且 query 不丢」。
