## MODIFIED Requirements

### Requirement: 课程正文必须支持结构化内容块

课程小节正文 MUST 以完整 `node_content` Markdown 作为主内容本体。系统 MUST NOT 要求后台生成、保存或展示固定教学块来表达正文结构。`content_blocks` MAY 作为旧数据和旧接口兼容字段保留，但 MUST NOT 覆盖 Markdown 的学科章法、标题结构和阅读形态。

#### Scenario: 新正文生成完成

- **WHEN** 小节正文生成完成
- **THEN** 系统 MUST 保存最终 Markdown 到 `node_content`
- **AND** 系统 MUST NOT 为了生成主链路把正文强制拆成固定 `content_blocks`
- **AND** 前端 MUST 优先按 Markdown 文档渲染正文

#### Scenario: 旧节点包含 content_blocks

- **WHEN** 前端或接口读取旧节点
- **THEN** 系统 MUST 继续兼容 `content_blocks`
- **AND** 前端 SHOULD 不再将 `content_blocks` 作为默认正文阅读形态
- **AND** 后端 MAY 在旧 block 级接口中使用 `content_blocks` 完成兼容操作

## ADDED Requirements

### Requirement: 系统必须支持 Markdown 选区级 AI 修改

系统 MUST 支持用户选中 Markdown 正文中的任意文字后请求 AI 局部修改。选区修改 MUST 基于选中文本、标题路径、前后文、课程/节点上下文和用户要求生成候选替换文本，并 MUST 保持当前学科章法。

#### Scenario: 用户选中文字发起改写

- **WHEN** 客户端提交选中文本、标题路径、前后文、节点正文和用户要求
- **THEN** 后端 MUST 使用 `CourseService` 构造选区修改上下文
- **AND** prompt SHOULD 包含课程账本、节点契约、AI Learning Context 和选区上下文
- **AND** 后端 MUST 返回候选替换文本
- **AND** 后端 MUST NOT 直接保存节点正文

#### Scenario: 用户确认候选修改

- **WHEN** 用户接受 AI 候选替换文本
- **THEN** 前端 MUST 只替换原 Markdown 中对应选区
- **AND** 前端 MUST 保存更新后的完整 `node_content`
- **AND** 若选区无法唯一定位，前端 MUST 避免静默替换错误位置

### Requirement: 前端必须提供文档式标题树和折叠体验

前端 MUST 从 Markdown 标题临时解析父子标题树，并在阅读界面展示类似文档编辑器的层级、缩进和折叠控制。该结构 MUST 只作为 UI 索引，不得改变后端正文存储格式。

#### Scenario: Markdown 包含多级标题

- **WHEN** 节点正文包含 `#`、`##`、`###` 等标题
- **THEN** 前端 SHOULD 构造父子标题树
- **AND** 前端 SHOULD 在正文中提供标题折叠控制
- **AND** 折叠状态 MUST NOT 修改 `node_content`

#### Scenario: 用户选中正文

- **WHEN** 用户在正文中选中一段文字
- **THEN** 前端 SHOULD 显示轻量浮动工具条
- **AND** 工具条 SHOULD 提供改写、简化、补例子、出题、问 AI 等操作
- **AND** 工具条 MUST 不把整篇正文改造成卡片列表

## REMOVED Requirements

### Requirement: 系统必须支持 block 级重新生成

系统 MUST 提供节点内部 block 级重新生成能力，重新生成时只能替换目标 block，不能丢失同节点其他 block。

#### Scenario: 用户要求重写应用部分

- **WHEN** 客户端请求重新生成某个 `block_id`
- **THEN** 后端 MUST 基于课程账本、当前节点契约、目标 block 原文、相邻 block 摘要和用户要求构造上下文
- **AND** 后端 MUST 只更新该 block 的 `content`
- **AND** 后端 MUST 重新生成该节点的 `node_content`
