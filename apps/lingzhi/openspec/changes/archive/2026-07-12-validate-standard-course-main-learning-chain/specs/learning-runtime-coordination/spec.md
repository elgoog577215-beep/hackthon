## ADDED Requirements

### Requirement: 标准课程主学习链必须可重复验收

系统 MUST 支持使用隔离用户仅通过公开 API 连续完成首次进入、阅读进度、跨设备恢复、学习记录、正式练习、诊断补救、章节连续性和 AI 老师协议验收。验收 MUST 使用同一当前课程版本与稳定对象身份，MUST NOT 直接修改持久文件或临时注入缺失课程资产。

#### Scenario: 隔离用户完成标准课程主链

- **WHEN** 验收用户从一门 strict ready 标准课程首次进入并依次执行主学习链
- **THEN** 每项领域写操作 MUST 由正式 API 持久化并反映到 LearningRuntime
- **AND** 课程版本、内容锚点、任务修订、诊断案例和补救会话 MUST 保持可追踪

### Requirement: 主学习链必须保持唯一连续性动作

主学习链每个稳定阶段 MUST 由 LearningContinuation 产生至多一个 primary action。AI 老师、学习记录、正式练习和诊断模块 MUST NOT 创建与该动作竞争的第二主行动。

#### Scenario: 学习者从阅读进入诊断补救

- **WHEN** 用户先完成阅读，随后产生正式失败、诊断任务和补救会话
- **THEN** primary action MUST 按当前正式状态依次指向掌握检查、诊断任务、补救任务和独立复验
- **AND** 每次动作变化 MUST 能由当前版本的正式证据解释
