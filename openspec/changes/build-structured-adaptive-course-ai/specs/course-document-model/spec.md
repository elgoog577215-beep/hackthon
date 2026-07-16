## ADDED Requirements

### Requirement: 个人适配不得进入正式课程命令

正式单块重新生成和教师课程编辑 MUST 继续归基础课程维护链，并通过 `CourseAuthoringChange` 与课程领域命令修改 `CourseDocument`。`PersonalAdaptationPlan` MUST NOT 调用这些写命令；确认后的个人变化 MUST 写入稀疏 `PersonalCourseOverlay`，且 MUST NOT 复制完整课程正文。

#### Scenario: 旧单块候选分流

- **WHEN** 系统读取一个尚未处理的旧块候选
- **THEN** 正式正文候选 MUST 迁入或保留在基础课程维护链
- **AND** 只有旧个人适配块 MAY 迁入 `PersonalCourseOverlay`
- **AND** 两类对象 MUST NOT 共用写入目标或确认状态

### Requirement: 个人方案与覆盖层不得改变基础课程修订

学习页面 MAY 在基础课程之上叠加待确认个人差异和已确认个人覆盖，但目录基础结构、基础课程读取和领域修订 MUST 继续以 `CourseDocument` 为准。学生确认个人方案 MUST NOT 改变基础课程修订。

#### Scenario: 页面显示多个待确认修改

- **WHEN** 当前课程存在行级、块级和未来章节候选
- **THEN** 页面 MAY 同时投影这些候选
- **AND** 基础课程修订 MUST 与个人方案创建前一致

### Requirement: 基础课程变化后必须重新定位个人锚点并保留历史

基础课程维护链发生移动、拆分、合并或移除时 MUST 保存稳定 ID、旧新映射或墓碑。个人覆盖、学习位置、笔记、问题和书签只有在可唯一映射时才能迁移，歧义必须显式等待确认；历史作答保留发生时引用。

#### Scenario: 被笔记引用的块被拆分

- **WHEN** 用户确认拆分一个含有锚定笔记的块
- **THEN** 系统 MUST 尝试使用文本位置与引用唯一迁移笔记
- **AND** 无法唯一定位的笔记 MUST 保留原引用并标记待确认
- **AND** MUST NOT 静默丢失或挂到错误新块
