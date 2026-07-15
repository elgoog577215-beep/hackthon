## ADDED Requirements

### Requirement: 前端必须显性化结构化课程文档体验

前端 MUST 将课程节点内容以可折叠、可操作的结构化 block 呈现。每个 block SHOULD 展示类型、标题、摘要和学习动作入口，并 MUST 保持旧 `node_content` Markdown 兼容。

#### Scenario: 用户操作某个内容 block

- **WHEN** 用户在课程内容区查看一个结构化 block
- **THEN** 前端 SHOULD 显示 block 类型、标题、摘要和折叠状态
- **AND** 用户 SHOULD 能执行简化、扩展、补例子、生成练习、重写或问 AI
- **AND** 这些操作 MUST 复用现有后端课程内容或 AI 助手接口

### Requirement: 前端必须展示可解释学习状态

前端 MUST 在学习者画像区域展示稳定画像和动态学习状态的区别。动态状态 SHOULD 包含薄弱点、最近证据、AI 教学判断和下一步建议，且不得把系统推断伪装成事实。

#### Scenario: 用户查看学习者画像

- **WHEN** 用户展开学习者画像面板
- **THEN** 前端 SHOULD 显示 AI 画像、自评、薄弱点、最近证据和 AI 判断
- **AND** 前端 SHOULD 说明这些状态来自错题、笔记、问答或导师建议等证据

### Requirement: 前端必须提供低打扰 AI 导师行动卡片

前端 MUST 提供低打扰 AI 导师行动入口，把后端导师建议转成可点击学习动作。行动卡片 SHOULD 优先引导测验、复习、换讲法、补例子或继续学习，不得频繁使用阻断式弹窗。

#### Scenario: 系统产生导师建议

- **WHEN** 后端返回导师建议
- **THEN** 前端 SHOULD 展示一张可关闭的 AI 导师行动卡片
- **AND** 行动卡片 SHOULD 提供至少一个可执行动作
- **AND** 用户关闭后 MUST 能继续当前学习流程
