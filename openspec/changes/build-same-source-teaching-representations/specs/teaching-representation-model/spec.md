## ADDED Requirements

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

### Requirement: 教学表达必须支持替代组合与降级

同一课程语义 MAY 拥有默认、替代、组合、无障碍和降级表达。系统 MUST 按任务、知识形态、正式学习证据、设备、无障碍和成本选择，不得使用固定“视觉型/听觉型学生”标签。

#### Scenario: 动画构建失败

- **WHEN** 当前课程块的结构化动画构建失败
- **THEN** 系统 MUST 保留基础课程可读
- **AND** MUST 使用静态关键帧或文字步骤作为降级表达
