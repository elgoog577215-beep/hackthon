## ADDED Requirements

### Requirement: 前端学习工作区必须共享当前目标范围

前端练习、掌握和学习连续性 MUST 使用同一当前目标身份。用户尚未显式选择有效节点时，工作区 MUST 回退到 `LearningRuntime.current_objective`；MUST NOT 因旧 `currentNode` 为空而静默扩大为全课程。

#### Scenario: 刷新课程后打开掌握工作区

- **WHEN** LearningRuntime 已返回当前目标且旧节点 Store 尚未选择节点
- **THEN** 掌握工作区 MUST 展示该目标名称并只过滤该目标资产
- **AND** 练习工作区的 node scope MUST 携带该目标节点 ID

### Requirement: 正式练习必须显式展示作用域

前端 MUST 区分当前目标、全课程和综合检测三种练习作用域，页面标签与接口参数 MUST 一致。

#### Scenario: 用户打开综合检测

- **WHEN** 练习 scope 为 final
- **THEN** 页面 MUST 显示综合检测作用域
- **AND** MUST NOT 把当前阅读节点名称显示成综合检测范围

### Requirement: 窄桌面必须保持课程正文可读

前端在 768 至 1024px MUST 避免课程目录、正文和固定笔记栏同时占位。课程目录 SHOULD 使用覆盖式抽屉，固定笔记栏 SHOULD 默认收起。

#### Scenario: 789px 视口打开课程阅读

- **WHEN** 用户在 789px 宽视口进入课程
- **THEN** 中央正文 MUST 保持正常横排与可读宽度
- **AND** 课程目录或笔记 MUST NOT 把正文压缩成逐字换行

### Requirement: 移动端课程模式必须可理解

前端在移动端 MUST 为阅读、总览、练习、掌握等课程模式保留可见文字或等效的持续可见名称；MUST NOT 仅依赖 hover title 或无文字图标表达主要导航。

#### Scenario: 390px 视口切换课程模式

- **WHEN** 用户查看课程模式导航
- **THEN** 每个主要模式 MUST 有可见名称
- **AND** 导航 MAY 横向滚动但 MUST NOT 遮挡连续性条或正文
