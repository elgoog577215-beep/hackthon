## ADDED Requirements

### Requirement: 教师必须能够按章节范围生成题目

系统 SHALL 在题库生成界面提供整门课程、连续章节和指定章节三种范围。章节范围 SHALL 使用课程中的稳定讲次节点标识，并 SHALL 按课程顺序提交。

#### Scenario: 按连续章节生成

- **WHEN** 教师选择第三讲到第五讲并开始生成
- **THEN** 系统 SHALL 以 `scope=nodes` 提交第三、第四和第五讲的节点标识
- **AND** 不在该范围内的讲次 SHALL 不进入本次生成任务

#### Scenario: 反向选择连续章节

- **WHEN** 教师先选择第五讲、再选择第三讲
- **THEN** 系统 SHALL 仍按课程顺序提交第三讲到第五讲

#### Scenario: 按不连续章节生成

- **WHEN** 教师勾选第一讲和第三讲并开始生成
- **THEN** 系统 SHALL 以 `scope=nodes` 只提交第一讲和第三讲的节点标识

#### Scenario: 指定章节为空

- **WHEN** 教师选择“指定章节”但未勾选任何章节
- **THEN** 开始生成操作 SHALL 保持不可用
- **AND** 系统 SHALL 不得把空选择降级为整门课程生成

### Requirement: 所有题目生成入口必须使用同一范围结果

系统 SHALL 让直接生成和 AI 调整候选共享同一份范围解析结果。

#### Scenario: AI 调整指定章节题目

- **WHEN** 教师勾选第二讲和第四讲后提交 AI 调整要求
- **THEN** AI 候选和接受后的重建请求 SHALL 都携带第二讲和第四讲的节点标识
