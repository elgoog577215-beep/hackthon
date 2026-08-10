## ADDED Requirements

### Requirement: 正式教案文档必须由结构化教案确定性编译

系统 MUST 将当前 `CourseTeachingPlanV3` 编译为 `FormalLessonPlanDocumentV1`，用于教师阅读、打印和导出。文档 MUST 保存教案修订、知识和来源引用；编辑 MUST 回到结构化教案字段，文档文本 MUST NOT 成为独立真源。

#### Scenario: 结构化教案更新一个小节的课堂活动
- **WHEN** 新教案修订正式应用
- **THEN** 正式教案文档 MUST 从新修订重新编译对应课时
- **AND** 未受影响课时 MUST 保持相同来源绑定
- **AND** 直接修改导出文档 MUST NOT 反向覆盖正式教案
