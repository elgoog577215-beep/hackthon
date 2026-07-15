## ADDED Requirements

### Requirement: 浏览器学习统计不得成为当前进度证据

localStorage 中的学习时长、连续天数、完成节点、难度偏好和历史分数 MAY 用于离线缓存或一次性低置信迁移，但 MUST NOT 直接改变正式阅读、掌握、学习者模型或 AI 判断。当前学习概况 MUST 从服务端正式投影读取。

#### Scenario: 浏览器缓存声称节点已经完成

- **WHEN** 服务端没有该目标当前修订的正式完成或掌握证据
- **THEN** 学习概况 MUST 以服务端投影为准
- **AND** MUST NOT 因本地缓存显示已学完或已掌握
