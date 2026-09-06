## ADDED Requirements

### Requirement: 教师备课空间与正式学习现场必须共享课程真源

系统 MUST 使教学日历首页、课程文件空间和学习现场共享同一 `course_id` 与当前 `CourseDocument` 修订。备课文件可作为生成输入、可编辑投影或导出物，MUST NOT 成为第二份课程语义真源。正式学习现场 MUST 保留阅读、记录、正式任务、诊断和 AI 协作骨架。

#### Scenario: 教师从文件空间预览课程

- **WHEN** 教师点击预览正式课程
- **THEN** 系统 MUST 进入同一 `course_id` 的学生视角学习现场
- **AND** MUST 使用当前课程修订组装正文与正式练习
- **AND** MUST 显示与学生端一致的正式练习、笔记、错题、学习概况、知识库和学生 AI 老师入口
- **AND** 预演产生的学习事件、快照、笔记、作答与 AI 对话 MUST 只归属当前教师身份，MUST NOT 读取或写入任一学生记录
- **AND** 预演操作 MUST NOT 直接改写正式课程资产

#### Scenario: 学生继续上次学习

- **WHEN** 学生点击带有确定学习快照的继续动作
- **THEN** 系统 MUST 直接进入正式学习现场的可恢复位置
- **AND** MUST NOT 丢失原节点、任务与学习记录上下文
