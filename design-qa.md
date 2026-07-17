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
