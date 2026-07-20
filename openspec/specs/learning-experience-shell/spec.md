# learning-experience-shell Specification

## Purpose
TBD - created by archiving change rebuild-learning-ui-around-course-flow. Update Purpose after archive.
## Requirements
### Requirement: 产品必须只有课程库与学习现场两个主空间

系统 MUST 将课程发现、创建、导入和生成状态放在课程库，将阅读、记录、正式任务、诊断和 AI 协作放在学习现场。课程蓝图、版本历史和学生块编排 MUST NOT 成为学习者主空间。

#### Scenario: 用户从首页继续课程

- **WHEN** 用户在课程库点击一门已有课程的继续动作
- **THEN** 系统 MUST 进入该课程的学习现场和可恢复位置
- **AND** MUST NOT 先进入课程编辑、蓝图或版本页面

### Requirement: 学习现场必须保持左目录中正文右 AI 的稳定骨架

桌面学习现场 MUST 以课程导航、连续正文和按需 AI 协作表达不同职责，正文 MUST 是唯一长期主舞台。结构化课程块 MUST 提供原位 AI 协作入口；全局 AI 工作区 MAY 作为历史与跨块问题入口按需打开，但 MUST NOT 永久挤压正文或成为块级理解的强制中转站。系统 MUST NOT 使用顶部平级模式替换正文。

#### Scenario: 用户并行理解多个课程块

- **WHEN** 用户在阅读中分别需要解释、例子、简化或提问
- **THEN** 每个动作 MUST 从对应课程块原位发起
- **AND** 系统 MUST NOT 把这些并行理解动作包装成唯一下一步

#### Scenario: 移动端打开块级 AI

- **WHEN** 用户在 390 像素视口打开课程块 AI 菜单或结果
- **THEN** 菜单、回答、操作和输入区 MUST 保持在正文宽度内
- **AND** MUST NOT 被底部导航遮挡或产生横向溢出

### Requirement: 正文必须渲染统一课程流投影

前端 MUST 确定性组合正式课程块、正式任务引用、行内学习记录和运行时临时适配块。该投影 MUST NOT 成为第二份课程排序或学习状态真源；旧 Markdown 课程 MUST 可无损降级进入同一渲染器。

#### Scenario: 旧课程没有持久内容块

- **WHEN** 学习现场加载只有 `node_content` 的旧课程
- **THEN** 兼容适配器 MUST 保留原文和顺序并生成只读渲染块
- **AND** MUST 明确降级能力而不是显示空白正文

### Requirement: 大型工具必须临时介入并准确返回

正式任务、学习记录总览、统计、知识图谱和代码工作台 MUST 通过统一覆盖层临时展开。正式任务在桌面 MUST 从正文预览块或并行工具入口进入居中弹窗，在移动端 MAY 全屏展开；MUST NOT 使用右侧半屏抽屉替代正文任务关系。打开前 MUST 保存来源引用和语义锚点，关闭后 MUST 返回原位置和最新正式状态。

#### Scenario: 用户从正文练习预览块打开正式任务

- **WHEN** 用户点击正文中可见的正式练习预览块
- **THEN** 系统 MUST 将同一正式任务从块态过渡为桌面居中弹窗或移动端全屏任务
- **AND** 预览块与弹窗 MUST 读取同一题目资产与 `PracticeAttempt`
- **AND** 系统 MUST NOT 在正文预览块创建第二份答案或进度状态

#### Scenario: 用户关闭正在进行的任务

- **WHEN** 活动 Attempt 已保存草稿且用户关闭覆盖层
- **THEN** 系统 MUST 返回来源任务块并显示继续状态
- **AND** MUST NOT 重载课程、跳到页面顶部或创建新 Attempt

#### Scenario: 用户偏好减少动态效果

- **WHEN** 系统检测到 `prefers-reduced-motion: reduce`
- **THEN** 正式任务 MUST 仍可正常打开、关闭和返回来源
- **AND** 系统 MUST NOT 依赖位移或缩放动画完成状态切换

### Requirement: 桌面永久入口必须去重

桌面学习现场 MUST NOT 同时存在固定笔记栏、AI 浮球、六按钮 `SmartBar`、导师建议横幅或重复图谱入口。宽屏 AI 老师右栏是唯一 AI 工作区；学习记录、统计与图谱按需展开。

#### Scenario: 宽屏进入普通课程

- **WHEN** 视口宽度不小于 1280 像素
- **THEN** 页面 MUST 默认显示目录、可读正文和一个 AI 老师右栏
- **AND** MUST NOT 显示固定笔记栏或第二个 AI 唤醒入口

### Requirement: 视觉系统必须继承既有产品语义并使用单一 token

新旧组件 MUST 使用同一色彩、圆角、边框、阴影、字号和间距 token。课程创建 MUST 使用纵向难度和可扫读的课程编排偏好建立核心视觉层级，并将教学结构、课程目的和资料边界置于第二层。页面结构主要依靠背景、边框和留白，普通工作区 MUST NOT 使用玻璃光晕、装饰性大渐变、默认超大圆角或卡片套卡片。

#### Scenario: 用户配置课程生成参数

- **WHEN** 用户打开课程创建弹窗
- **THEN** 课程主题、难度和课程编排偏好 MUST 构成清晰的第一阅读路径
- **AND** 每个编排选项 MUST 解释它会增加或组织哪些课程块
- **AND** 教学结构、课程目的和资料边界 MUST 保留但不得与难度形成拥挤的控制台

#### Scenario: 用户确认教学方案

- **WHEN** 课程生成停在教学方案步骤
- **THEN** 页面 MUST 以可扫读形式展示全课角色分布与每节块序列
- **AND** 编排名称、块角色和难度摘要 MUST 使用中英文 locale 文案
- **AND** 页面 MUST NOT 把编排结果退化为一段不可核验的风格说明

#### Scenario: 新任务入口嵌入旧正文

- **WHEN** 任务入口出现在课程块之间
- **THEN** 它 MUST 使用与正文一致的宽度、边框、字号和状态色
- **AND** MUST NOT 看起来像来自另一套产品的独立大卡片

### Requirement: 响应式布局必须优先保证正文和主任务

系统 MUST 在 390、789、1024 和 1440 像素保持正文可读、主要操作可理解且无互相遮挡。目录和 AI 在窄屏 MUST 使用互斥覆盖；移动底部导航只允许目录、正文、记录和 AI 四个空间入口。

#### Scenario: 789 像素视口打开 AI 老师

- **WHEN** 用户在阅读中打开 AI 老师
- **THEN** AI MUST 覆盖而不是永久挤压正文
- **AND** 目录与 AI MUST NOT 同时覆盖正文

### Requirement: 学习入口必须保留并行任务空间并仅恢复确定中断

学习工作区 MUST 保留目录、练习、学习记录、知识图谱与 AI 的并行入口。系统 MAY 根据正式学习快照显示一项最近中断恢复提示，但 MUST NOT 将开始目标、进入下一章、到期复习或 AI 建议包装成唯一下一步。

#### Scenario: 用户存在未完成练习

- **WHEN** 学习快照记录一个状态为进行中的正式练习
- **THEN** 课程库与学习页 MAY 显示“继续未完成练习”
- **AND** 该提示 MUST 指向原课程和原学习节点
- **AND** 用户 MUST 仍可直接使用其他并行工具入口

#### Scenario: 用户没有可恢复状态

- **WHEN** 课程没有学习快照或快照不包含有效节点
- **THEN** 课程卡 MUST NOT 显示“从上次位置继续”
- **AND** 学习页 MUST NOT 显示通用“下一步”主按钮

#### Scenario: continuation 返回普通推进动作

- **WHEN** continuation 返回开始目标、完成阅读、进入下一章或到期复习
- **THEN** 学习页 MUST NOT 将其渲染为唯一主动作
- **AND** 相关能力 MUST 继续通过正文、目录或正式任务入口可达

### Requirement: 移动学习界面必须使用真实窄屏布局

课程库和学习页 MUST 在真实 390 像素布局视口下保持页面级无横向溢出。公式、表格和代码块 MAY 在自身容器内横向滚动，但 MUST NOT 扩大页面宽度或被父级静默裁切。

#### Scenario: 用户使用移动设备学习

- **WHEN** 布局视口宽度为 390 像素
- **THEN** 课程标题和正文 MUST 完整换行
- **AND** 课程库管理操作 MUST 完整显示且可点击
- **AND** 移动底栏与恢复提示 MUST 避开安全区并不得遮挡正文

### Requirement: 学生理解入口与正式课程编辑入口必须分离

结构化课程块的学生 AI 菜单 MUST 固定只提供解释、举例、简化和提问。正式课程正文改进 MUST 使用独立、低权重且受编辑能力控制的入口，进入既有课程候选与确认流程；它 MUST NOT 作为学生菜单的第五项。全局 AI MAY 继续作为历史与跨块入口，但三种表面 MUST 复用同一 AI 协议而不得复制状态。

#### Scenario: 学生打开课程块 AI 菜单

- **WHEN** 用户打开任一结构化课程块的星光入口
- **THEN** 菜单 MUST 只显示解释、举例、简化和提问
- **AND** MUST NOT 显示正式课程改写动作

#### Scenario: 课程编辑者改进正式正文

- **WHEN** 当前用户具备课程块编辑能力且目标是正式 CourseBlock
- **THEN** 来源块附近 MUST 提供与学生 AI 菜单分离的编辑入口
- **AND** 该入口 MUST 进入候选生成、质量检查和确认应用流程

#### Scenario: 行内回答显示来源关系

- **WHEN** 块级 AI 回答在来源块下方完成
- **THEN** 标题区 MUST 标明当前动作和来源块
- **AND** 结果 MUST 保持课程补充的正文层级而不是独立聊天气泡

### Requirement: Shared Markdown rendering must preserve valid mathematics

The frontend MUST render valid inline and display LaTeX through the shared sanitized Markdown renderer. It MUST NOT leak math delimiters, placeholder tokens, or partial KaTeX error output for supported input forms.

#### Scenario: Multiline display formula

- **WHEN** course Markdown contains a valid multiline `$$ ... $$` formula
- **THEN** the renderer MUST produce one display-math region
- **AND** the visible output MUST NOT contain raw `$$` delimiters

#### Scenario: Legacy formula followed by prose

- **WHEN** a legacy course line contains a delimiter-free equation followed by Chinese explanatory prose
- **THEN** the renderer MUST send only the equation portion to KaTeX
- **AND** MUST preserve the explanatory prose as ordinary text

#### Scenario: Sanitized shared rendering

- **WHEN** course content or an inline learning-record summary contains Markdown and mathematics
- **THEN** both surfaces MUST use the shared Markdown/KaTeX renderer
- **AND** HTML sanitization and existing code and Mermaid behavior MUST remain enabled
