## ADDED Requirements

### Requirement: 课程学习能力必须由统一只读契约表达

系统 MUST 以同一份只读投影表达标准、显式纯阅读和旧课兼容模式。纯阅读模式 MUST 由资产计划显式声明；兼容模式 MUST 由旧生成时代结构识别，MUST NOT 因现代标准课程缺少题目而自动启用。

#### Scenario: 现代标准课程缺少正式练习

- **WHEN** 一门具备现代生成契约的标准课程缺少必需正式题目
- **THEN** 课程模式 MUST 仍为 `standard`
- **AND** 正式练习能力 MUST 标记为阻断
- **AND** 系统 MUST NOT 将其解释成纯阅读或旧课兼容

### Requirement: 无题状态必须可解释

正式练习接口和前端 MUST 区分显式纯阅读、旧课兼容、标准课程资产缺失与当前范围无题。用户 MUST 能判断当前状态是产品设计、兼容边界还是需要修复的生成故障。

#### Scenario: 用户打开没有题目的练习页

- **WHEN** 当前范围没有可用正式题目
- **THEN** 接口 MUST 返回稳定原因码
- **AND** 前端 MUST 展示与原因码匹配的标题和说明

### Requirement: 降级不得伪造掌握或破坏确定性学习

纯阅读和旧课兼容课程完成阅读后 MAY 继续下一章节，但 MUST 保持未验证掌握状态。标准课程缺少必需练习时，系统 MUST 阻断空的掌握检查并指向课程资产修复。AI 模型不可用 MUST NOT 改写确定性的学习状态或下一步。

#### Scenario: AI 模型不可用时继续阅读

- **WHEN** AI 老师 provider 返回错误
- **THEN** AI 老师 MUST 返回安全不可用状态
- **AND** LearningRuntime 的阅读、记录和连续性投影 MUST 继续可用
