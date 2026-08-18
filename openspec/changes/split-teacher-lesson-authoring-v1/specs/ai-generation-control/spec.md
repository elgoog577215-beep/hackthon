## ADDED Requirements

### Requirement: 教师任务不得进入学生整课生成生命周期
系统 MUST 为教师大纲、讲次教案和讲次 PPT 使用独立任务类型及观察入口。学生 `course_generation`、generation preview 和学习页不得消费教师任务。

#### Scenario: 教师生成第二讲
- **WHEN** 教师启动第二讲教案任务
- **THEN** 学生课程页面不显示该任务进度或草稿内容
- **AND** 学生原整课生成任务行为保持不变

### Requirement: 教师讲次检查点必须稳定复用
系统 MUST 冻结讲次任务的 section scope 和批次身份，恢复时只继续未完成批次。批次 ID 不得因重算并发/容量而重新指向不同小节。

#### Scenario: 模型服务中断后恢复
- **WHEN** 第二讲三个小节中两个已完成且模型调用中断
- **THEN** 恢复任务只处理第二讲剩余小节
- **AND** 已完成结果不重做，其他讲次不启动
