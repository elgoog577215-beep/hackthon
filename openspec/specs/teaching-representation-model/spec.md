# teaching-representation-model Specification

## Purpose
TBD - created by archiving change build-same-source-teaching-representations. Update Purpose after archive.
## Requirements
### Requirement: 所有教学表达必须引用同一课程语义

系统 MUST 将大纲视为 `CourseDocument` 的确定性投影，并 MUST 将教案、PPT、讲义、图解、动画和题目导出保存为带来源绑定的教学表达。任何教学表达 MUST NOT 成为第二课程语义真源。

#### Scenario: 为课程块生成 PPT 页面

- **WHEN** 系统为一个课程块编译 PPT 页面
- **THEN** 页面 MUST 保存课程、块、知识、目标、题目和源修订引用
- **AND** 页面文本 MUST NOT 成为独立课程正文

#### Scenario: 投影课程大纲

- **WHEN** 用户查看课程大纲
- **THEN** 系统 MUST 从当前 `CourseDocument` 投影章节和目标
- **AND** MUST NOT 读取或维护第二棵章节树

### Requirement: 演示文稿必须是结构化教学编译结果

系统 MUST 将课程目标、知识、能力、易错、掌握标准、正式题目和课程块编译为页面级结构，不得将课程正文按长度直接复制到幻灯片。浏览器预览与 `.pptx` 导出 MUST 读取同一 `SlideDeckSpec`。

#### Scenario: 课程正文包含代码、表格和正式题目

- **WHEN** 系统编译该小节的演示文稿
- **THEN** 代码、表格和正式题目 MUST 分别进入对应的结构化页面块
- **AND** 页面 MUST 保存对应课程块、知识和题目引用
- **AND** 页面可见文本 MUST NOT 泄漏 Markdown 语法或接近正文长度的段落

#### Scenario: 课件未通过质量门

- **WHEN** 页面缺少来源、超过版式容量或仍是正文复制
- **THEN** 系统 MUST 阻止该课件成为当前正式版本
- **AND** `.pptx` 导出 MUST 拒绝该版本

### Requirement: 页级生成可见但正式发布必须原子完成

系统 MUST 在编译过程中逐页发送临时页面事件，使用户可以看见已完成页面；临时页面 MUST NOT 提前替换注册表中的最后可用版本。

#### Scenario: 用户在课件生成过程中查看结果

- **WHEN** 编译器完成一张结构化页面
- **THEN** 前端 MUST 立即使用该页的正式结构预览
- **AND** 完整课件通过质量门后注册表 MUST 一次性切换到新版本
- **AND** 中途失败时系统 MUST 继续提供旧版本

### Requirement: PPT 必须使用独立全屏工作台

系统 MUST 在课程顶栏提供明确的 PPT 一级入口，并 MUST 使用课程级独立全屏工作台承载整套页序、预览、编辑、演示和导出。PPT MUST NOT 继续作为通用教学资源覆盖层中的一个页签，但其数据 MUST 继续属于同一 `TeachingRepresentation` 注册表和 `SlideDeckSpec`。

#### Scenario: 教师从课程进入 PPT

- **WHEN** 教师点击课程顶栏右上角的 PPT 入口
- **THEN** 系统 MUST 进入当前课程的独立 PPT 工作台
- **AND** 工作台 MUST 展示完整页序、当前页、同源依据、质量状态和页级编辑
- **AND** 顶部最右侧 MUST 提供可直接下载的 `.pptx` 导出

#### Scenario: 教师进入课堂演示

- **WHEN** 教师从工作台启动全屏演示
- **THEN** 系统 MUST 使用当前 `SlideDeckSpec` 渲染课堂页面
- **AND** MUST 支持前后翻页、退出和讲者备注
- **AND** MUST NOT 复制一份独立演示内容

### Requirement: 每个教学单元必须形成可讲授闭环

系统 MUST 先规划整套页序再填充页面。每个包含正式课程块的教学单元 MUST 至少包含学习目标、核心讲解和理解检查；理解检查 MUST 优先引用正式题目，没有正式题目时 MAY 基于本节目标和原课程块生成解释任务与自检标准。

#### Scenario: 教案没有现成练习题

- **WHEN** 一个教学单元有学习目标和课程正文但没有正式题目
- **THEN** 课件 MUST 仍包含该单元的理解检查页
- **AND** 检查任务 MUST 绑定本节目标和原课程块
- **AND** MUST NOT 编造课程中不存在的知识结论或数据

### Requirement: 教学目标变化必须产生可核验的精准影响证据

系统 MUST 将 PPT 学习目标的语义变化解释为教学维度变化，并 MUST 从真实来源绑定计算受影响和保持不变的单元。教师确认前 MUST NOT 修改课程真源；同步后 MUST 展示逐单元真实差异，并区分内容实际改写与仅完成来源校验。

#### Scenario: 学习目标从计算技能升级为概念理解

- **WHEN** 教师把 PPT 学习目标从掌握计算规则改为解释概念关系与运算顺序
- **THEN** 系统 MUST 说明教学证据从计算技能转向概念理解
- **AND** MUST 将教案重点、讲义引导、相关核心讲解或例题、理解检查列为真实影响对象
- **AND** MUST 将没有共同来源依赖的其他章节明确列为保持不变
- **AND** 教师确认后 MUST 返回每个重建单元的修改前后摘要或来源校验结果

#### Scenario: 教师暂不确认语义变化

- **WHEN** 教师查看影响图后选择暂不应用
- **THEN** 当前 `CourseDocument` 与所有正式教学表达 MUST 保持不变
- **AND** 系统 MUST NOT 在后台静默执行全量重生成

### Requirement: 中文与数学公式 PPTX 必须经过原生软件验收

系统 MUST 输出可编辑的标准 `.pptx`，保存中文字体声明与讲者备注，并 MUST 在导出前把课程中的 LaTeX 数学表达转译为 PowerPoint 可直接显示的数学符号、Unicode 上下标、矩阵/方程组括号和运算箭头。质量验收 MUST 同时覆盖文件解析、页数、中文文本、East Asian 字体声明、原始 LaTeX 泄漏、替换字符和原生 PowerPoint 实际打开。

#### Scenario: 教师导出中文课件

- **WHEN** 教师点击工作台右上角的 `.pptx` 导出
- **THEN** 下载文件 MUST 使用课程标题作为安全文件名
- **AND** 原生 PowerPoint MUST 正常显示中文、页面对象、讲者备注、数学符号、上下标、矩阵与运算箭头
- **AND** 关键质量问题存在时系统 MUST 拒绝导出

#### Scenario: 课程正文包含 LaTeX 或错误解码字符

- **WHEN** 课件编译器读取包含矩阵、方程组、上下标或常见 LaTeX 命令的课程块
- **THEN** 页面可见文本 MUST NOT 包含 `$`、反斜杠命令、环境标记或 Unicode 替换字符
- **AND** 系统 MUST 将可安全转译的表达转换为课堂可读数学文本
- **AND** 仍有原始 LaTeX 或错误解码片段时 MUST 阻止正式发布与导出

#### Scenario: 公式转译规则升级

- **WHEN** 课件编译器版本高于当前正式课件记录的编译器版本
- **THEN** 系统 MUST 重建该课件而不是复用旧页面载荷
- **AND** 新课件通过当前质量门后才可替换最后可用版本

### Requirement: 教学表达必须支持替代组合与降级

同一课程语义 MAY 拥有默认、替代、组合、无障碍和降级表达。系统 MUST 按任务、知识形态、正式学习证据、设备、无障碍和成本选择，不得使用固定“视觉型/听觉型学生”标签。

#### Scenario: 动画构建失败

- **WHEN** 当前课程块的结构化动画构建失败
- **THEN** 系统 MUST 保留基础课程可读
- **AND** MUST 使用静态关键帧或文字步骤作为降级表达
