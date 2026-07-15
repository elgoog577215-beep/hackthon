# learner-model-state Specification

## Purpose
TBD - created by archiving change converge-learning-evidence-model-ai-teacher. Update Purpose after archive.
## Requirements
### Requirement: 学习者模型必须由正式事实确定性重算

系统 MUST 仅从当前学习者可追溯的正式领域对象、LearningEvent 和同批运行时投影构建 LearnerModel。构建过程 MUST NOT 调用大模型或读取旧 AI 自由画像、Learning OS 判断和浏览器统计真源；相同来源修订 MUST 产生相同 `model_revision_id`。

#### Scenario: 重复读取未变化的学习者模型

- **WHEN** 正式事件、记录、Attempt、快照、诊断和课程修订均未变化
- **THEN** 两次读取 MUST 返回相同模型修订与相同结论
- **AND** 系统 MUST NOT 保存一份可独立漂移的模型副本

### Requirement: 模型结论必须可解释且有时间边界

每个优势、待巩固项、支持需求或风险推断 MUST 返回证据引用、证据类型、置信度、计算时间与有效边界。证据不足或过期时 MUST 明确返回未知或低置信，不得伪造综合分数、学习风格、最佳时间或稳定人格。

#### Scenario: 学习者只有一次页面打开

- **WHEN** 当前只有开始阅读事实且没有正式作答、记录或重复阻塞
- **THEN** 模型 MUST 标记证据不足
- **AND** MUST NOT 推断已经掌握、薄弱、偏好难度或适合某种学习风格

### Requirement: 阅读、掌握、自我报告与推断必须分层

LearnerModel MUST 保留学习进度的正式阅读与掌握结论，不得用模型加权分数覆盖它们。用户显式自我报告 MUST 与系统推断分区表示；旧版本、旧目标修订和受完整提示影响的证据只能作为历史或受限证据。

#### Scenario: 用户自称已经理解但未通过正式检测

- **WHEN** 用户保存理解自评且当前目标没有独立通过证据
- **THEN** 模型 MAY 显示该自我报告
- **AND** 正式掌握 MUST 继续是证据不足或未检查
- **AND** AI MUST NOT 把自我报告表述为系统已验证

### Requirement: 学习者模型必须按身份和课程隔离

系统 MUST 使用稳定学习者身份和课程范围构建模型。其他学习者、其他课程或共享默认用户的数据 MUST NOT 进入当前模型；缺少有效身份时 MUST NOT 返回或写入个体模型。

#### Scenario: 两个学习者使用同一课程

- **WHEN** 学习者 A 已完成正式练习而学习者 B 仅开始阅读
- **THEN** A 的模型 MAY 包含正式掌握证据
- **AND** B 的模型 MUST NOT 读取 A 的 Attempt、记录或事件

### Requirement: AI 和界面不得直接修改模型

LearnerModel MUST 是只读投影。AI 回答、会话摘要、界面筛选和展示排序 MUST NOT 直接修改模型；任何可影响模型的变化 MUST 先通过正式领域命令形成可追溯事实。

#### Scenario: AI 认为学生存在薄弱点

- **WHEN** AI 在回答中提出一个可能的薄弱点
- **THEN** 该文本 MUST 保持为解释或建议
- **AND** MUST NOT 自动写入 LearnerModel、掌握状态或正式学习事实
