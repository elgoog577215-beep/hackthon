# 2026-07-17 当前练习内容密度 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-ed5086ed-f8ca-41c7-a8af-58ecc17efc47.png`
- implementation screenshot path: `C:\Users\Lenovo\AppData\Local\Temp\design-qa-current-practice-expanded.png`
- viewport: `2086 × 1225`
- state: 高级数据结构课程 `1.1 前置知识诊断测试`，第一题待作答
- full-view comparison evidence: `C:\Users\Lenovo\AppData\Local\Temp\design-qa-practice-density-composite.png`
- focused region comparison evidence: 未单独裁切；对照图中的题目、输入框、操作区和底部余量均清晰可读，并用 DOM 几何数据精确核对尺寸

**Findings**

- 无可执行的 P0/P1/P2 差异。桌面作答区由 `920px` 扩大到 `1280px`，当前视口下输入框高度约 `662px`，操作区下方余量约 `82px`。
- 字体与排版：题目层级、字号、字重和行高保持不变；加宽后长题目仍保持清晰阅读层级。
- 间距与布局：练习标签、诊断带、题目、输入框及操作栏统一采用更宽的内容轨道；底部内边距由 `90px` 收紧到 `36px`。
- 色彩与视觉令牌：未改变现有背景、边框、选中态、禁用态和提交按钮颜色。
- 图片与资源：该界面无内容图片或插画，现有图标未替换。
- 文案与内容：题目、占位提示和操作文案均保持不变。
- 响应式：`1024 × 768` 和 `390 × 844` 均无页面级横向溢出；移动端继续使用 `180px` 输入框高度。

**Open Questions**

- 无。

**Implementation Checklist**

- [x] 桌面内容轨道扩大到 `1280px`。
- [x] 作答输入框使用 `clamp(360px, 54vh, 680px)` 自适应高度。
- [x] 收紧题目区底部留白。
- [x] 保留移动端紧凑布局。
- [x] 检查桌面、中等宽度和移动端溢出。

**Comparison History**

- 初始 P2：内容轨道仅 `920px`，输入框最小高度 `220px`，题目区底部预留 `90px`，在大屏形成明显空洞。
- 修复：将主要练习轨道扩大到 `1280px`，输入框按视口增高，底部间距降至 `36px`。
- 修复后视觉证据：`C:\Users\Lenovo\AppData\Local\Temp\design-qa-current-practice-expanded.png`
- 修复后结构证据：当前视口下题目轨道 `1280px`、输入框约 `662px`，页面横向溢出为 `0`。

**Primary Interactions Tested**

- 当前练习待作答状态正常呈现。
- 提示、问老师和提交按钮保持可见。
- 桌面、中等宽度、移动端布局切换正常。
- Console errors checked: `0`。

**Follow-up Polish**

- 无阻断性 P3 建议。

final result: passed

---

# 2026-07-20 题库目标覆盖矩阵精简与分页 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-ddf46fd3-d76a-4ec9-aa98-e47cf05ac02b.png`
- selected design target path: `C:\Users\Lenovo\AppData\Local\Temp\figma-default-state.png`
- implementation screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\objective-matrix-collapsed.png`
- expanded pagination screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\objective-matrix-pagination.png`
- narrow viewport screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\objective-matrix-narrow.png`
- full-view comparison evidence: `D:\lingzhi\hackthon\artifacts\design-qa\original-vs-implementation.png`
- focused design comparison evidence: `D:\lingzhi\hackthon\artifacts\design-qa\design-target-vs-implementation.png`
- desktop viewport: `1280 × 720`
- narrow viewport: `900 × 700`
- state: Python 高级编程课程题库；真实数据为 63/63 已覆盖

**Findings**

- 无可执行的 P0/P1/P2 差异。原先连续渲染全部已覆盖目标的长列表已改成异常优先结构；健康项默认只保留一条汇总入口。
- 默认状态仅渲染异常项和“63 项已覆盖”摘要；真实页面中已覆盖明细与分页均未创建，消除了无意义的初始长滚动。
- 展开后每页严格显示 10 条；第二页范围为 11–20，最后一页范围为 61–63。
- 页码区支持上一页、下一页、离散页码和直接输入页码跳转。
- 窄内容区首次检查发现分页被右侧裁切；修复为三段自适应换行后，页码与跳转控件均保持在容器内。
- 已覆盖行使用紧凑布局，重建操作收进更多菜单；异常行仍保留状态、验证器信息和直接重建按钮。
- 真实课程当前没有异常目标，因此异常置顶视觉由设计目标与组件夹具覆盖；实际浏览器验证了全覆盖分支。

**Comparison History**

1. 初始问题：全部目标逐行常驻，63 个健康项会形成超长滚动，并重复暴露低频重建按钮。
2. 第一版：健康项默认合并为摘要，展开后每页 10 条，并加入底部分页和页码跳转。
3. 窄屏检查：`900 × 700` 下分页三列总宽度超过内容区。
4. 修复：分页改为可换行的弹性布局，范围信息、页码组和跳转表单按可用宽度分行。
5. 最终复查：桌面与窄屏均无分页裁切；默认收起、第二页和末页跳转均通过。

**Primary Interactions Tested**

- 打开 Python 高级编程课程的题库管理。
- 默认收起已覆盖目标；确认已覆盖行数量为 0、分页数量为 0。
- 点击“查看全部已覆盖项”；确认仅渲染 10 条。
- 点击第 2 页；确认显示第 11–20 条。
- 输入页码 7 并跳转；确认显示第 61–63 条，共 3 条。
- 再次收起；确认返回摘要状态。
- `900 × 700` 视口重复展开与翻页；确认分页控件完整可见。
- Console errors checked: `0`。

**Automated Verification**

- 聚焦组件测试：1 个文件，11 个测试通过。
- 前端完整测试：74 个文件，518 个测试通过。
- 前端生产构建与 Vue TypeScript 检查：通过。

**Open Questions**

- 无。

final result: passed

---

# 2026-07-20 题目浏览列表卡片级折叠复验 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-9bc6be6b-333b-4bc7-baf3-db58eccb3a58.png`
- implementation screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-accordion-collapsed.png`
- expanded state screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-accordion-expanded.png`
- narrow viewport screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-accordion-narrow.png`
- full-view comparison evidence: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-accordion-comparison.png`
- focused region comparison evidence: 未额外裁切；并排对照图中的首题卡片、十条摘要和底部分页均可清晰辨认，另用 DOM 几何数据核对卡片高度与分页位置
- desktop viewport: `1221 × 845`
- narrow viewport: `900 × 700`
- state: Python 高级编程课程题库；真实数据为 197 道题，第 1 页

**Findings**

- 无剩余可执行 P0/P1/P2 差异。最新来源截图证明上一版只折叠题干、未折叠审核表单，单题仍占据大面积纵向空间；现在整张题目卡默认收起为摘要行。
- 桌面摘要行实测高度为 `54px`。同一滚动视口内，第 1–10 条与底部分页同时可见：首条顶部 `133px`、第十条底部 `722px`、分页底部 `793px`、滚动容器底部 `825px`。
- 摘要保留题型、单行题干、来源、验证器、发布状态和“展开审核”入口；答案验证、审核意见和返工/批准操作仅在展开后出现。
- 手风琴行为一次只允许展开一道题。展开第二题会自动收起第一题；翻页、搜索和状态筛选都会清除当前展开状态。
- 每页最多 10 条的分页保持不变，支持上一页、下一页、离散页码和直接页码跳转；末页实测为第 191–197 条，共 7 条。
- 字体与排版：沿用现有字族、字重和层级；摘要题干使用单行省略，展开后恢复完整预格式化题干。
- 间距与布局：列表间距收紧为 `5px`，桌面摘要行保持大于 44px 的可点击高度；`900 × 700` 下改为两行信息布局且无页面级横向溢出。
- 色彩与视觉令牌：沿用现有品牌紫、成功绿、中性边框和白色卡片，展开态仅增加现有品牌色边框与轻阴影。
- 图片与资源：该区域无内容图片；继续使用项目现有图标库，没有引入占位资产。
- 文案与内容：题目和审核业务文案保持不变，仅将“展开全文”调整为更准确的“展开审核 / 收起审核”。

**Comparison History**

1. 来源截图 P1：虽然题干被截为 6 行，但答案入口、意见框和返工按钮仍常驻；前两题就占满可视区，滚动长度没有实质改善。
2. 第一轮修复：将整张卡片改为默认摘要、按需展开详情，并限制同一时间只展开一道题。
3. 密度复查 P2：初始摘要行 `73px`，底部分页仍超出同一滚动视口约 `36px`。
4. 第二轮修复：将摘要行压缩到 `54px`、列表间距压缩到 `5px`，在来源截图对应桌面比例下让 10 条摘要与分页同时进入同一滚动视口。
5. 最终复查：桌面折叠态、单题展开态、第二页、末页跳转和窄宽度布局均通过。

**Primary Interactions Tested**

- 打开 Python 高级编程课程题库，确认默认渲染 10 条紧凑摘要且详情数量为 0。
- 展开第一题，确认完整题干、答案验证、意见框和返工操作出现。
- 展开第二题，确认第一题自动收起，页面仍只有 1 个详情区域。
- 切换第 2 页，确认范围为第 11–20 条且详情自动收起。
- 直接跳转第 20 页，确认范围为第 191–197 条，共 7 条。
- `900 × 700` 下确认 10 条摘要无横向溢出。
- Console errors checked: `0`。

**Automated Verification**

- 聚焦组件测试：1 个文件，12 个测试通过。
- 前端完整测试：74 个文件，519 个测试通过。
- 前端生产构建与 Vue TypeScript 检查：通过。

**Open Questions**

- 无。

final result: passed

---

# 2026-07-20 题目浏览列表精简与分页 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-a007eaea-0867-47d9-8929-bb8920c11723.png`
- implementation screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-compact.png`
- pagination screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-pagination.png`
- narrow viewport screenshot path: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-narrow.png`
- full-view comparison evidence: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-original-vs-implementation.png`
- focused region comparison evidence: `D:\lingzhi\hackthon\artifacts\design-qa\question-list-focused-comparison.png`
- desktop viewport: `1280 × 720`
- narrow viewport: `900 × 700`
- state: Python 高级编程课程题库；真实数据为 197 道已发布题目

**Findings**

- 无剩余可执行 P0/P1/P2 差异。题目列表由一次渲染 197 道改为每页最多 10 道，末页显示 191–197，共 7 道。
- 长题干默认压缩为 6 行摘要，并提供“展开全文 / 收起全文”；真实页面首屏从单题占满多屏缩短到同屏可辨认两道题。
- 搜索与状态筛选继续作用于全部 197 道题；条件变化时自动回到第 1 页，结果不足两页时隐藏分页但不误显示空状态。
- 页码区支持上一页、下一页、离散页码和直接输入页码跳转；`900 × 700` 窄内容区会自适应换行，无右侧裁切。
- 字体与排版：沿用现有字族、字号、字重与行高，只对长题干增加 6 行摘要，不改变题目内容本身。
- 间距与布局：保留题目卡片、筛选栏、审核操作的原有层级；分页作为独立底部卡片，不覆盖题目或操作按钮。
- 色彩与令牌：继续使用现有品牌紫、成功绿、中性边框和白色卡片，没有引入新视觉语言。
- 图片与资源：该区域无内容图片；展开/收起使用已有图标库，不存在占位图或低清资源。
- 文案与内容：保留题目、质量、来源、验证器、答案验证、备注和打回重做文案；仅新增分页和全文展开文案。

**Comparison History**

1. 初始 P1：197 道题全部常驻，单个题干还可能包含整段课程材料，滚动长度不可控。
2. 第一版：加入每页 10 道、页码和直接跳转；真实页面验证每页只渲染 10 个题目卡片。
3. 第二次 P1：真实数据中的单题仍可能占满数屏，仅分页不足以解决阅读密度。
4. 修复：超过 420 字或 8 行的题干默认压缩为 6 行，按题独立展开和收起。
5. 第三次 P2：筛选结果不足两页时，分页的 `v-else` 错误显示空状态。
6. 修复：空状态改为仅在筛选结果确实为 0 时出现，并补充组件回归断言。
7. 最终复查：桌面、窄屏、搜索、状态筛选、第二页与末页跳转均通过。

**Primary Interactions Tested**

- 打开 Python 高级编程课程的题库管理。
- 确认第 1 页仅渲染 10 道题，范围为 1–10 / 197。
- 展开并收起第一道长题干；`aria-expanded` 从 false 变为 true，再恢复 false。
- 点击第 2 页；确认范围为 11–20 / 197。
- 输入页码 20 并跳转；确认末页范围为 191–197，渲染 7 道题。
- 搜索“工业级 AI 应用中的 Python 服务部署模式”；确认筛选为 3 道且分页隐藏。
- 切换“已发布”状态；确认列表存在且不显示错误空状态。
- `900 × 700` 视口检查末页分页；控件完整可见并自适应换行。
- Console errors checked: `0`。

**Automated Verification**

- 聚焦组件测试：1 个文件，12 个测试通过。
- 前端完整测试：74 个文件，519 个测试通过。
- 前端生产构建与 Vue TypeScript 检查：通过。

**Open Questions**

- 无。

final result: passed

---

# 2026-07-17 当前练习与学习记录统一 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-b993a736-f715-4cf6-a612-db54568adf65.png`
- implementation screenshot path: `C:\Users\Lenovo\AppData\Local\Temp\design-qa-current-practice-unified.png`
- viewport: `2128 × 1410`
- state: 高级数据结构课程 `1.1 前置知识诊断测试`，当前练习已打开，第一题待作答
- full-view comparison evidence: `C:\Users\Lenovo\AppData\Local\Temp\design-qa-practice-vs-records-composite.png`
- focused region comparison evidence: 未单独裁切；全视图中顶部三级标签、关闭按钮、任务标题、作答区和外层工作区均可清晰辨认，已另外用 DOM 几何数据核对工具层边界

**Findings**

- 无可执行的 P0/P1/P2 差异。当前练习与学习记录使用相同的 `learning-tool-overlay` 外壳，并占用相同工作区矩形：`x=302.67, y=80.67, width=1814.67, height=1318.67`。
- 字体与排版：沿用现有界面字族、字号、字重和层级；任务标题、状态与控件没有新增截断或异常换行。
- 间距与布局：两种工具状态的边界、顶部标签带、关闭按钮位置和内容区留白一致；左侧章节目录继续保留。
- 色彩与视觉令牌：沿用学习记录的白色工具层、淡色分隔线、紫色选中态和青绿色练习状态，不新增独立弹窗阴影或灰色遮罩。
- 图片与资源：该状态无内容图片或插画；现有图标继续复用同一图标体系，没有用临时图形替代。
- 文案与内容：保留当前练习、练习历史、待巩固及题目内容，不改变业务文案。

**Open Questions**

- 无。

**Implementation Checklist**

- [x] 移除居中 `MorphingDialog` 与全局背景遮罩。
- [x] 当前练习复用学习工具全幅页内外壳。
- [x] 当前练习、学习记录、学习概况继续在进入后的顶部标签切换。
- [x] 验证当前练习 → 学习记录 → 当前练习双向切换。
- [x] 验证 Escape/关闭按钮语义、`role="dialog"` 和 `aria-modal="true"`。

**Comparison History**

- 初始问题：当前练习是居中弹窗，尺寸、背景遮罩和空间层级均与学习记录不一致。
- 修复：移除弹窗包装，新增共享 `learning-tool-overlay` 外壳，并让三个学习工具状态复用同一绝对定位与移动端规则。
- 修复后视觉证据：`C:\Users\Lenovo\AppData\Local\Temp\design-qa-current-practice-unified.png`
- 修复后结构证据：当前练习与学习记录边界数据完全一致；旧 `.morphing-dialog` 与遮罩数量均为 `0`。

**Primary Interactions Tested**

- 底部“学习”进入当前练习。
- 顶部“学习记录”切换并返回“当前练习”。
- 当前练习关闭按钮存在且唯一。
- Console errors checked: `0`。

**Follow-up Polish**

- 无阻断性 P3 建议。

final result: passed

---

# 课程块 AI 助手 Design QA

## 结论

`passed`

课程块已经成为 AI 助手的主交互单元：左侧学生入口固定展开解释、举例、简化和提问四项，结果作为来源块的临时补充原位展开；规范课程的“改进正式正文”迁移为块右上角独立编辑入口，不再混入学生菜单。完整回答只增加“已解决 / 还不清楚”效果反馈，全局 AI 继续保留为历史与跨块入口。

## 对照证据

- 参考设计：`/Users/yq/.codex/generated_images/019f5af9-3522-79e2-a1b8-6ec4061c33be/exec-147c8fa0-eeb9-455c-bb5c-d08d462c0290.png`
- 参考与实现并排对照：`/Users/yq/.codex/visualizations/2026/07/13/019f5af9-3522-79e2-a1b8-6ec4061c33be/inline-course-block-ai/comparison.png`
- 桌面端真实页面：`/Users/yq/.codex/visualizations/2026/07/13/019f5af9-3522-79e2-a1b8-6ec4061c33be/inline-course-block-ai/desktop-question.png`
- 移动端动作菜单：`/Users/yq/.codex/visualizations/2026/07/13/019f5af9-3522-79e2-a1b8-6ec4061c33be/inline-course-block-ai/mobile-menu.png`
- 移动端提问输入：`/Users/yq/.codex/visualizations/2026/07/13/019f5af9-3522-79e2-a1b8-6ec4061c33be/inline-course-block-ai/mobile-question.png`
- 2026-07-14 优化前加载状态：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-polish/01-before-desktop.jpeg`
- 2026-07-14 优化后桌面端加载状态：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-polish/02-after-desktop-loading.jpeg`
- 2026-07-14 优化后 390px 提问输入：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-polish/03-after-mobile-question.jpeg`
- 2026-07-14 本轮优化前桌面基线：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/01-current-desktop.png`
- 正式编辑入口独立显示：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/05-implemented-separated-entry-hover.png`
- 四项学生菜单：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/06-implemented-four-action-menu.png`
- 完整回答与效果反馈：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/07-implemented-answer-feedback-desktop.png`
- 390px 完整回答：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/08-implemented-answer-feedback-mobile.png`
- 英文模式完整回答：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/09-implemented-answer-feedback-english.png`
- 四项菜单与正式编辑入口框注：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/10-annotated-four-actions-and-formal-entry.png`
- 回答与效果反馈框注：`/Users/yq/.codex/visualizations/2026/07/14/lingzhi-inline-ai-approved/11-annotated-answer-and-feedback.png`

## 可见差异与处理

| 级别 | 对照发现 | 处理结果 |
| --- | --- | --- |
| P0 | 无阻断主任务的问题 | 通过 |
| P1 | 参考图把块级动作固定在左侧轨道，真实课程块数量更多，若常驻会造成噪音 | 改为低权重星光入口；激活时只显示四项已确认动作 |
| P1 | AI 内容容易与正式课程混淆 | 使用左侧紫色边界、浅色底和“临时个人内容”标签明确分层 |
| P1 | 移动端左侧轨道空间不足 | 入口移到块标题右侧，菜单和结果限制在内容列内，无横向溢出 |
| P1 | 生成中卡片过白，三段骨架列宽合计超过容器，视觉上像空白或卡死 | 改为三行定宽骨架、提高状态文字对比度，并将生成中的动作明确命名为“停止生成” |
| P1 | 菜单打开后焦点仍留在入口，方向键和 Escape 没有完整路径 | 打开时焦点进入第一项，支持上下方向键、Home / End，Escape 关闭后返回入口 |
| P1 | 学生理解与正式课程改写混在同一菜单，权限和结果边界不清 | 学生菜单固定四项；正式正文改进改为受权限控制的独立编辑入口，继续进入候选、质量门与确认链 |
| P1 | 系统只知道回答完成，不知道是否真正解决当前问题 | 完整回答增加“已解决 / 还不清楚”，按会话消息幂等写入 `LearningEvent`；不自动生成下一步或其他对象 |
| P1 | Store 将原始消息对象交给组件后，流式状态变化未稳定触发重渲染，真实页面可能长期停在“正在思考” | 回调改为传递会话数组中的响应式消息代理，并增加 Store 回归断言；真实流复测已从 `streaming` 收束为 `complete` |
| P2 | 行内回答只写“临时个人内容”，与来源块的关系需要回忆 | 标题区同步显示来源块名称，使回答成为课程补充而不是游离聊天气泡 |
| P2 | 未发送的提问和继续追问缺少可见退出方式 | 输入区增加低权重取消按钮；首次提问取消后不留空卡，继续追问取消后保留已有回答 |
| P2 | 父级内容块悬停时，子组件 scoped 选择器无法稳定提升入口可见度 | 改为 `:global(.course-content-block:hover)`，保持默认弱提示、悬停清晰 |

## 响应式与交互核验

- 390px：确认四项菜单完整收在内容列内，提问输入、取消与发送按钮可用，无横向溢出。
- 789px：确认目录可收起，块级入口与四项菜单可用。
- 1024px、1440px：结合断点规则与桌面真实页面检查，入口不占正文布局宽度，结果块保持内容列内伸缩。
- 桌面端：真实页面确认块级入口、原位提问、明确加载与停止状态，正式课程与临时内容层级清楚。
- 键盘：真实 Edge 页面确认菜单打开后焦点落到“解释”，向下键移到“举例”，Escape 关闭菜单并把焦点返回入口。
- 中英文：新增文案全部进入 `zh/en` locale，通过同一组键读取；1024px 英文真实页面无横向溢出，课程数据中的中文标题不属于界面文案残留。

## 保留边界

- 未增加“下一步”、主动建议、自动出题、自动保存、多块比较或学生块编辑器；块级 prompt 明确禁止用“如果你愿意”等话术主动引出后续动作。
- 四项临时 AI 回答不写回正式课程；“已解决 / 还不清楚”只写效果事实，只有用户明确点击“保留为个人内容”才进入个人记录。“改进正式正文”另走候选、质量检查与确认应用链路。
- 模型提供方的实时响应速度属于现有 AI 服务运行条件，不影响本次前端交互与视觉验收。

## 2026-07-14 正文练习块展开 Design QA

### 结论

`passed`

正式练习已经形成“正文扫读态 → 专注作答态 → 原位返回”的完整交互：正文块展示 3 道正式题和首题摘要，桌面展开为居中弹窗，390px 展开为全屏任务；现有 `PracticeWorkspace`、`PracticeAttempt`、自动保存、提示、评阅和 AI 老师事件保持不变。

### 对照证据

- 1440px 正文练习预览：`/Users/yq/.codex/visualizations/2026/07/14/practice-block-morph/desktop-practice-block.png`
- 1440px 居中练习弹窗：`/Users/yq/.codex/visualizations/2026/07/14/practice-block-morph/desktop-practice-dialog.png`
- 390px 正文练习预览：`/Users/yq/.codex/visualizations/2026/07/14/practice-block-morph/mobile-practice-block.png`
- 390px 全屏练习任务：`/Users/yq/.codex/visualizations/2026/07/14/practice-block-morph/mobile-practice-dialog.png`
- 英文模式正文练习预览：`/Users/yq/.codex/visualizations/2026/07/14/practice-block-morph/desktop-practice-block-en.png`

### 可见差异与处理

| 级别 | 对照发现 | 处理结果 |
| --- | --- | --- |
| P0 | 旧入口只有标题和“开始练习”，用户打开前不知道题目在问什么 | 改为题量、首题两行摘要、自动保存说明和明确打开动作 |
| P1 | 旧任务覆盖整个正文主区，切换突兀且不像从正文块进入 | 增加复用型 FLIP 过渡壳；桌面从来源块展开为居中弹窗，关闭反向收回 |
| P1 | 右侧半屏会破坏正文块与任务的来源关系 | 明确不使用右侧抽屉；桌面居中、移动全屏 |
| P1 | 动画期间焦点曾短暂留在正文 | 动画开始时立即把焦点送入模态弹窗；Tab 约束在内部，关闭后归还来源 |
| P1 | 固定最小高度可能在矮屏中越界 | 最小高度同时受 `100vh - 64px` 约束；390、789、1024、1440 均无页面级横向溢出 |
| P2 | 从 Dock 或恢复提示打开时不存在可见来源块 | 不伪造共享来源动画，降级为克制淡入；仍返回实际触发按钮 |
| P2 | 位移缩放可能影响减少动态效果用户 | `prefers-reduced-motion: reduce` 下跳过 FLIP 动画，打开、关闭和回位语义不变 |

### 交互与响应式核验

- 1440px：预览块宽 `834px`；弹窗 `1040 × 780px`，正文仍可作为来源背景被感知。
- 1024px：弹窗 `960 × 738px`；789px：弹窗 `725 × 738px`；两者页面宽度与布局视口一致。
- 390px：预览块在正文列内完整换行，任务占满 `390 × 844px`，底部操作和安全区无横向溢出。
- 关闭：真实 Edge 页面确认 Escape 关闭后 `body` 滚动恢复，焦点回到 `practice-block-L2-1-1`，正文滚动位置保持 `6416`。
- 中英文：新增题量、自动保存与打开动作全部读取同一组 `zh/en` locale；英文模式无新增中文硬编码，课程题目中文属于课程数据。

### 保留边界

- 本轮只接正式练习；错题本和知识图谱没有接入新的弹窗壳，也没有改为全屏或右侧抽屉。
- 正文预览不新增答案框、完成度推断或本地练习状态；所有作答仍进入同一个正式 `PracticeAttempt`。
- 弹窗内部不增加第二个 AI 对话，问老师继续调用已有全局 AI 协作入口。

---

# 2026-07-18 学习工具父子层级 Design QA

final result: passed

---

# 2026-07-19 练习题参考材料折叠 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-51da8b98-91b7-4e10-be2d-841cfb355e6f.png`
- implementation screenshot path: `D:\lingzhi\hackthon\design-qa-practice-collapsed-material.png`
- mobile implementation screenshot path: `D:\lingzhi\hackthon\design-qa-practice-collapsed-material-mobile.png`
- viewport: desktop `2022 × 1042`，mobile `390 × 844`
- state: Python 高级编程课程，1.1 Python 对象模型与类型系统，当前练习第 1 题，参考材料默认收起
- full-view comparison evidence: `D:\lingzhi\hackthon\design-qa-practice-collapsed-material-comparison.png`
- focused region comparison evidence: 全景并排图中的题目主区域已足够清楚，可直接比较原先占满视口的课程材料与修复后的任务卡、折叠入口和作答区

**Findings**

- 无可执行的 P0/P1/P2 差异。进入练习后，真正的作答任务完整出现在首屏，参考材料默认收起，作答输入区紧随其后。
- 字体与排版：沿用现有字体和字号体系；“作答任务”使用 13px 强调标题，任务正文保持 15px 可读字号；参考材料的标题、说明和操作形成清晰的三级信息层级。
- 间距与布局：桌面端任务卡、参考材料和作答区间距稳定；移动端没有水平溢出，任务内容、折叠行和作答框均完整落在 390px 视口内。
- 色彩与视觉令牌：任务卡使用现有绿色强调色和中性白底；参考材料使用已有浅绿色图标底、灰色边框和正文色，不新增视觉体系。
- 图片与资源：该区域没有课程图片资源；继续使用项目已有 Lucide 图标，不存在占位图、CSS 图形或低清资源替代。
- 文案与内容：“作答任务”优先展示；“参考材料 / 课程原文较长，需要时再展开查看 / 展开材料”明确说明内容性质和操作结果。
- 交互：原生 `details/summary` 支持键盘聚焦、展开和收起；切换到另一道题时，题目修订 ID 作为 key，参考材料会恢复默认收起状态。

**Implementation Checklist**

- [x] 将题目拆分为 `task` 与 `material` 两个独立展示字段。
- [x] 作答任务固定显示在参考材料之前。
- [x] 参考材料默认收起，可按需展开与再次收起。
- [x] 展开后保留完整 Markdown、代码块、列表和图表能力。
- [x] 换题时重新创建折叠区域，避免继承上一题的展开状态。
- [x] 完成桌面与 390px 移动端适配。

**Comparison History**

- 初始 P1：课程原文、图表和代码占据几乎整个练习视口，真正的作答任务需要滚动到底部才能看到。
- 修复：从题目契约的 `input_materials` 中分离课程材料，将剩余题干作为作答任务；作答任务提升到首屏，课程原文放入默认关闭的参考材料折叠区。
- 修复后桌面证据：`D:\lingzhi\hackthon\design-qa-practice-collapsed-material.png`
- 修复后移动端证据：`D:\lingzhi\hackthon\design-qa-practice-collapsed-material-mobile.png`

**Primary Interactions Tested**

- 从课程页打开当前练习。
- 确认首屏直接显示作答任务，参考材料默认关闭。
- 点击“展开材料”，真实页面显示 13 个 Markdown 标题和 5 个代码块。
- 点击“收起材料”，参考材料正文再次隐藏。
- 在 390 × 844 视口打开移动端练习，主要内容和底部操作完整可用。
- Console errors/warnings checked: `0`。

**Automated Verification**

- 相关测试：4 个文件、42 个测试通过。
- 最终聚焦测试：2 个文件、9 个测试通过。
- 前端生产构建及 Vue TypeScript 检查：通过。

**Open Questions**

- 无。

**Follow-up Polish**

- 无阻断性 P3 建议。

final result: passed

---

# 2026-07-19 练习题 Markdown 排版 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-1b2266d6-9db0-40f4-b711-f9463528d38f.png`
- implementation screenshot path: `D:\lingzhi\hackthon\design-qa-practice-markdown.png`
- viewport: `2191 × 1015`（与问题截图一致）
- state: Python 高级编程课程，1.1 Python 对象模型与类型系统，当前练习第 1 题
- full-view comparison evidence: `D:\lingzhi\hackthon\design-qa-practice-markdown-comparison.png`
- focused region comparison evidence: 并排图中完整保留题目正文区域，能够直接比较原始单段文本与修复后的标题、段落、列表及代码层级

**Findings**

- 无可执行的 P0/P1/P2 差异。题目不再以一整段原始字符串展示，而是复用产品现有的安全 Markdown 渲染链路。
- 字体与排版：建立 H1/H2/H3 层级、正常正文行高、段落留白和列表缩进；长内容保持左对齐，阅读节奏清晰。
- 间距与布局：题目正文使用独立白色内容卡，分隔线、标题和正文采用一致的垂直节奏；底部作答工具栏不遮挡正文。
- 色彩与视觉令牌：延续现有深色正文、绿色强调色、中性边框和浅色背景，不引入新的品牌色。
- 代码与技术内容：行内代码、围栏代码块、列表、强调文本、表格及 Mermaid 继续使用现有 Markdown 能力；练习页关闭代码运行按钮，仅保留阅读和复制能力。
- 文案与内容：清理 `<!-- BODY_START -->` 等内部注释；课程材料与实际作答要求之间增加分隔线和“作答任务”标题。
- 截断兜底：课程材料被题库截断在未闭合代码围栏中时，前端自动闭合围栏，防止后续作答任务被错误吞入代码块。

**Implementation Checklist**

- [x] 使用现有 `MarkdownRenderer` 渲染正式练习题目。
- [x] 保留 Markdown 原始换行、标题、列表、代码块和强调格式。
- [x] 隐藏内部 HTML 注释标记。
- [x] 将课程材料和作答任务明确分区。
- [x] 对未闭合代码围栏做显示层兜底。
- [x] 长题目在原有独立滚动容器内阅读，滚动条正常可见。
- [x] 小屏样式降低标题字号和内容卡内边距。

**Comparison History**

- 初始 P1：题目通过普通 `<h3>{{ currentQuestion.prompt }}</h3>` 输出，浏览器折叠换行，Markdown 标记和正文全部挤成一坨。
- 修复：改为安全 Markdown 组件，并增加练习题专用格式化函数，分离材料与任务、去除内部注释、闭合截断围栏。
- 修复后视觉证据：`D:\lingzhi\hackthon\design-qa-practice-markdown.png`
- 修复后结构证据：真实页面题目区域包含 14 个标题、29 个段落、5 组列表、5 个代码块；`BODY_START` 可见次数为 0；“作答任务”独立标题为 1。

**Primary Interactions Tested**

- 从课程页点击“练习”打开正式练习弹层。
- 当前练习正确恢复为第 1/3 题。
- 题目正文按 Markdown 层级渲染，列表、行内代码和代码块均可辨识。
- 页面滚动区域正常，固定底部作答操作未遮挡正文。
- Console errors/warnings checked: `0`。

**Automated Verification**

- 相关测试：4 个文件、41 个测试通过。
- 最终聚焦测试：2 个文件、8 个测试通过。
- 前端生产构建：通过。

**Open Questions**

- 无。

**Follow-up Polish**

- 无阻断性 P3 建议。

final result: passed

## Reference and implementation

- Reference concept: `C:\Users\Lenovo\.codex\generated_images\019f75a5-d3f1-7ac1-8ffb-186183c11e21\call_hGVGrTlQ2epqUk3BfYD5mWbV.png`
- Desktop implementation capture: `design-qa-learning-tools-implementation.png`
- Same-input side-by-side comparison: `design-qa-learning-tools-comparison.png`
- Mobile implementation capture: `design-qa-learning-tools-mobile.png`
- Desktop viewport: 1487 × 1058
- Mobile viewport: 390 × 844
- Tested route: `/course/4215dc17-7c34-48ad-91c8-a1b780c0366d/learn/L2-1-1`
- Compared state: “学习任务 · 3” expanded with its three child actions visible.

## Visual comparison

- The bottom dock keeps two explicit parent controls: “学习任务 · 3” and “课程资料 · 2”.
- “智能助教” remains an independent peer action.
- Expanding a parent opens a visually attached floating tray directly above its trigger.
- The learning tray contains “当前练习 / 学习记录 / 学习概况”.
- The resource tray contains “知识库 / 教学资源”.
- Active state, upward chevron, tray pointer, icon treatment, spacing, borders, and shadow match the selected concept and the existing product visual language.
- The implementation adapts the concept to the real application shell; its information architecture and parent-child grouping remain equivalent to the reference.

## Responsive and accessibility checks

- Desktop: tray is fully visible, aligned to its parent, and does not cover the trigger.
- Mobile: the same hierarchy becomes a bottom sheet above the fixed three-part dock without horizontal overflow.
- Parent buttons expose `aria-haspopup`, `aria-expanded`, and `aria-controls`.
- Child actions use menu/menuitem semantics.
- Escape closes the tray and restores focus to the originating parent control.
- Clicking the other parent swaps trays without navigating.
- Clicking outside closes the tray.
- Unavailable practice remains visible and disabled with a reason/status.

## Runtime verification

- Browser console errors/warnings: none.
- Full frontend tests: 59 files, 347 tests passed.
- Production build: passed.
- Vue TypeScript check: passed.
- Focused security scan of changed frontend files: no secrets, debug logging, or unsafe HTML rendering found.
- `npm audit` could not run because the configured `npmmirror.com` registry does not implement the npm audit endpoint; the registry configuration was left unchanged.

## QA history

1. Captured the selected concept and desktop implementation at the same 1487 × 1058 viewport/state.
2. Compared both images side by side in one visual input.
3. Verified learning and resource tray switching.
4. Verified Escape dismissal and focus restoration.
5. Verified the mobile bottom-sheet adaptation at 390 × 844.
6. Re-ran the complete frontend test suite, production build, and TypeScript check.

---

# 2026-07-19 题库审核连续滚动 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-96afe83c-7138-4b80-96d3-313dd1c2bdbc.png`
- implementation screenshot path: `D:\lingzhi\hackthon\design-qa-question-bank-scrollbar-scrolled.png`
- viewport: `1280 × 720`（参考图按实现宽度等比缩放并裁切到同一视口）
- state: Python 高级编程题库审核弹窗，覆盖矩阵滚动至高阶函数/装饰器附近
- full-view comparison evidence: `D:\lingzhi\hackthon\design-qa-question-bank-comparison.png`
- focused region comparison evidence: 未单独裁切；并排图中题目行、状态、重建按钮及右侧滚动条均清晰可辨

**Findings**

- 无可执行的 P0/P1/P2 差异。审核详情区拥有独立、常驻的纵向滚动轨道，真实页面从 `scrollTop=0` 滚动到 `760` 后仍停留在相同弹窗内。
- 字体与排版：未改变既有字族、字号、字重、行高及题目层级；动态题目文案保持原样。
- 间距与布局：保留原有双栏审核中心和题目行密度；滚动条通过稳定 gutter 占位，不挤压题目状态或操作按钮。
- 色彩与视觉令牌：滚动轨道使用现有灰蓝中性色，滑块与背景有清晰对比；原有待审核状态色和卡片底色未变。
- 图片与资源：该界面没有内容图片或插画；现有 Lucide 图标未替换。
- 文案与内容：课程名、审核状态、节点标题和操作文案均未改动。
- 行为：批准/拒绝成功后使用接口返回的题目、版本和审核队列就地更新，不再触发整块题库重新加载，因此不会因加载态收缩而回到顶部。

**Open Questions**

- 无。

**Implementation Checklist**

- [x] 审核详情区始终显示纵向滚动条。
- [x] 使用稳定滚动条占位，避免内容宽度抖动。
- [x] 批准/拒绝后就地更新当前题目和待审核数量。
- [x] 清理已处理题目的备注与已加载答案缓存。
- [x] 保留版本冲突时重新加载的安全兜底。

**Comparison History**

- 初始 P1：批准/拒绝后调用完整 `load()`，组件进入加载态，长内容瞬间收缩并把滚动位置钳制到顶部。
- 修复：移除成功路径的完整重新加载，直接消费审核接口返回的 `bundle_revision_id`、`review_queue` 和 `item`；同时为详情区增加常驻、可见的滚动轨道。
- 修复后视觉证据：`D:\lingzhi\hackthon\design-qa-question-bank-scrollbar-scrolled.png`
- 修复后结构证据：真实页面 `overflow-y: scroll`、`scrollbar-gutter: stable`、`scrollHeight=510235`、`clientHeight=617`，滚动操作后 `scrollTop=760`。

**Primary Interactions Tested**

- 从课程库打开 Python 高级编程的题库审核中心。
- 题库真实数据加载完成，待审核 196 条正常显示。
- 右侧详情区从顶部向下滚动，滚动位置由 0 变为 760。
- 审核成功路径由组件测试验证：仅加载题库一次，批准后题目原位移除且待审核计数更新为 0。
- Console errors checked: `0`。

**Follow-up Polish**

- 无阻断性 P3 建议。

final result: passed

---

# 2026-07-19 课程 / 大纲 / 教案壳层统一 Design QA

- source visual truth path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-9d610842-b879-44bb-bedb-daa6cae0fa02.png`
- undesirable state reference path: `C:\Users\Lenovo\AppData\Local\Temp\codex-clipboard-6316dbec-12fb-484b-ad99-3611d37d0002.png`
- normalized course baseline path: `D:\lingzhi\hackthon\design-qa-course-shell.png`
- implementation screenshot path: `D:\lingzhi\hackthon\design-qa-lesson-plan-final.png`
- desktop viewport: `2048 × 1095`
- mobile viewport: `390 × 844`
- state: Python 高级编程课程，教案标签激活，教学资源为空
- full-view comparison evidence: `D:\lingzhi\hackthon\design-qa-course-vs-lesson-plan.png`
- focused region comparison evidence: `D:\lingzhi\hackthon\design-qa-course-vs-lesson-plan-top.png`

**Findings**

- 无可执行的 P0/P1/P2 差异。大纲和教案不再覆盖整个浏览器窗口，而是稳定地替换课程主面板内容。
- 字体与排版：复用课程页现有字体、字号、字重和导航标签样式；资源标题与空状态文案保持不变。
- 间距与布局节奏：课程与教案状态下，应用顶部栏均为 `2028 × 60`，左侧目录均为 `280 × 1005`，课程主面板均为 `1736 × 1005`；课程栏与资源栏均为 `58px` 高，标签组均为 `333 × 43` 且坐标一致。
- 色彩与视觉令牌：沿用既有品牌紫、灰蓝文字、白色面板、边框和阴影，没有引入新的视觉语言。
- 图片与资源：界面仅使用既有品牌 Logo 和图标库图标，没有以 CSS、字符或占位图替代可见资产。
- 文案与内容：保留“课程大纲”“课程教案”“还没有可用的教学资源”“从当前课程生成”等现有产品文案。
- 响应式：`390 × 844` 下资源栏固定为 `52px`，顶部品牌栏和底部学习工具栏保留，页面无横向溢出。
- 可访问性：大纲 / 教案可见时，被覆盖的课程栏、正文和底栏使用 `inert` 与 `aria-hidden` 隔离，避免键盘焦点或读屏落入背后内容。

**Comparison History**

- 初始 P1：资源工作区使用 `position: fixed; inset: 0` 和 `100vw × 100dvh`，切换后遮住顶部品牌栏与左侧课程目录，形成明显的全屏放大和布局跳变。
- 修复：将教学资源层约束为课程主面板内的绝对定位层，桌面栏高统一为 `58px`，移动端统一为 `52px`，并保留独立知识库原有的全屏工作区行为。
- 修复后证据：`D:\lingzhi\hackthon\design-qa-course-vs-lesson-plan.png` 显示课程与教案两种状态的外层框架、尺寸和坐标保持一致。

**Primary Interactions Tested**

- 课程 → 大纲：主面板尺寸不变，顶部品牌栏和左侧目录保留。
- 大纲 → 教案：仅资源类型和激活标签变化，框架尺寸不变。
- 教案 → 课程：资源层关闭并恢复原课程正文，主面板尺寸不变。
- 课程 → 练习 → 大纲：练习与资源工作区均保持在课程主面板内。
- 移动端练习 → 大纲：资源栏固定为 `52px`，四个标签和操作区可用。
- Console errors checked: 仅存在示例课程尚未迁移而无法编译教学资源的既有数据错误；该错误对应用户参考图中的空状态，不是本次壳层修改产生的布局或交互错误。

**Automated Verification**

- 3 个相关测试文件、13 个测试通过。
- Vue TypeScript 检查与前端生产构建通过。

**Open Questions**

- 无。

**Follow-up Polish**

- 无阻断性 P3 建议。

final result: passed
