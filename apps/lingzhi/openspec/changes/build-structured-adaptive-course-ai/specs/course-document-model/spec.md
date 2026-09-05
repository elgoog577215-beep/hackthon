## ADDED Requirements

### Requirement: 课程生长必须进入正式课程命令

正式单块重新生成、教师课程编辑和经确认的学习证据驱动调整 MUST 统一通过课程领域命令修改当前 `CourseDocument`。`CourseEvolutionPlan` MUST 固定当前课程修订、证据、范围和受影响对象，并在接受后形成新的正式课程修订。系统 MUST NOT 建立第二份长期课程正文或 `PersonalCourseOverlay` 真源。

#### Scenario: 当前课程生长方案被确认

- **WHEN** 用户确认当前课程的一组课程生长操作
- **THEN** 系统 MUST 通过统一课程命令写入当前 `CourseDocument`
- **AND** 学习证据、作用范围和原课程修订引用 MUST 保留
- **AND** 不应产生平行课程写入目标

### Requirement: 接受课程生长方案必须产生新课程修订

学习页面 MAY 在当前课程之上预览待确认差异，但接受后的正式内容、目录读取和领域修订 MUST 统一以新的 `CourseDocument` 为准。应用 MUST 返回包含前后修订、受影响块和命令 ID 的持久回执。

#### Scenario: 页面显示多个待确认修改

- **WHEN** 当前课程存在行级、块级和未来章节候选
- **THEN** 页面 MAY 同时投影这些候选
- **AND** 未接受候选 MUST NOT 改变当前课程修订
- **AND** 接受的操作组 MUST 原子产生一个新课程修订

### Requirement: 课程变化后必须重新定位学习锚点并保留历史

课程维护链发生移动、拆分、合并或移除时 MUST 保存稳定 ID、旧新映射或墓碑。学习位置、笔记、问题和书签只有在可唯一映射时才能迁移，歧义必须显式等待确认；历史作答保留发生时引用。

#### Scenario: 被笔记引用的块被拆分

- **WHEN** 用户确认拆分一个含有锚定笔记的块
- **THEN** 系统 MUST 尝试使用文本位置与引用唯一迁移笔记
- **AND** 无法唯一定位的笔记 MUST 保留原引用并标记待确认
- **AND** MUST NOT 静默丢失或挂到错误新块
