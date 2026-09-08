# question-bank-targeted-generation Specification

## Purpose
定义课程 AI 题目的逐题生成、直接发布、字段级定向修复和按题重新生成边界，使局部失败不扩大到同讲其他题目，并在替换失败时保护最后可用修订。

## Requirements

### Requirement: 可用题目必须直接发布

系统 SHALL 在普通课程练习题通过结构、可作答性和答案一致性硬检查后直接将其发布到正式题库，不得要求教师先完成批准操作。难度、措辞、多样性和模型评审置信度 SHALL 作为非阻断质量信息保存。综合考核和要求对真实个体采取医疗等高后果行动的题目 SHALL 继续使用既有教师确认门。

#### Scenario: 题目通过硬检查但模型评审置信度偏低

- **WHEN** 题面、作答契约、标准答案和独立验证均有效，但模型质量评审置信度低于建议阈值
- **THEN** 系统 SHALL 发布该题
- **AND** 系统 MAY 在质量详情中保留改进建议

#### Scenario: 题目存在明确答案矛盾

- **WHEN** 独立验证证明标准答案与公开题面矛盾且定向修复未成功
- **THEN** 系统 SHALL 不发布该修订
- **AND** 当前有效题目 SHALL 保持不变

### Requirement: 生成结果必须按题目槽位独立结算

系统 SHALL 以 `node_id + practice_level` 为普通生成题的最小结算单位。一个槽位失败不得阻止同讲其他成功槽位发布。

#### Scenario: 同讲三道题中一道失败

- **WHEN** 两个槽位通过硬检查而第三个槽位失败
- **THEN** 系统 SHALL 发布两个成功槽位
- **AND** 系统 SHALL 只将失败槽位留给后续重试

### Requirement: 教师按题重新生成必须只执行选中题目

系统 SHALL 从选中修订解析其稳定题目身份、讲次和练习层级，并只为该槽位调用生成器。

#### Scenario: 教师重新生成目标应用题

- **WHEN** 教师对一讲的目标应用题发起重新生成
- **THEN** 生成器 SHALL 只收到该讲的 `objective_practice` 槽位
- **AND** 同讲概念辨析和迁移掌握题 SHALL 不产生模型调用或新修订

### Requirement: 重新生成必须保护最后可用题目

系统 SHALL 在新修订成功发布前保持旧修订有效，并通过题库基线修订执行原子替换。

#### Scenario: 新题生成失败

- **WHEN** 教师重新生成一题且新候选生成或验证失败
- **THEN** 原题 SHALL 继续处于发布状态
- **AND** 学生端可见题目 SHALL 不发生变化

### Requirement: 定向修复必须限制实际变更字段

系统 SHALL 根据稳定问题代码选择修复策略和允许字段，并在采用模型修复结果前恢复或拒绝所有越界字段变化。

#### Scenario: 只修复缺失解析

- **WHEN** 唯一问题为 `WORKED_SOLUTION_INCOMPLETE`
- **THEN** 系统 SHALL 只采用解析和解题步骤字段的修改
- **AND** 题面、选项、考查目标、作答契约和验证器 SHALL 保持不变

#### Scenario: 问题要求改变锁定题型

- **WHEN** 修复问题无法在锁定题型、目标和验证器内解决
- **THEN** 系统 SHALL 重新生成当前题目槽位
- **AND** 系统 SHALL 不扩大到其他槽位或讲次

### Requirement: 排队与模型执行必须独立计时

系统 SHALL 分别记录容量排队时间和 provider 执行时间；生成阶段执行超时 SHALL 在取得容量后开始计算。

#### Scenario: 模型容量繁忙但请求尚未发出

- **WHEN** 任务仍在容量队列中并持续获得有效心跳
- **THEN** 系统 SHALL 不返回 provider 执行超时
- **AND** 取得容量后 SHALL 使用完整的阶段执行时间预算
