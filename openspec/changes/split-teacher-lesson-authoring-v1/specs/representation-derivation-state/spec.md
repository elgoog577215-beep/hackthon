## ADDED Requirements

### Requirement: 教师表达必须形成精确修订图
系统 MUST 记录 `current lesson plan revision → current script revision → slide deck revision` 的精确派生关系，并把作用域限制在一个 `LessonUnit`。上传原件、Markdown 投影和导出文件不得成为平行正式真源。

#### Scenario: 查询第二讲PPT来源
- **WHEN** 系统读取第二讲 PPT 修订
- **THEN** 可以追溯到精确讲稿修订、教案修订及其原文件来源
- **AND** 导出的 PPTX 不被反向登记为新的内容真源

### Requirement: 来源变化必须精确标记下游状态
上游当前修订变化时，系统 MUST 只标记受影响的教案、讲义块、PPT 教学单元或页面为需更新或过期，保留最后可用版本并提供定向重建。系统 MUST NOT 因单块变化清空整门课资产，也 MUST NOT 由监听器自动重生成、自动应用或覆盖任何下游版本。

#### Scenario: 修改第二讲操作示范块
- **WHEN** 教师保存了第二讲教案中“操作示范”教学块的新版本
- **THEN** 系统标记对应讲稿块及其 PPT 页面需要更新
- **AND** 其他教学块、讲次和最后可用 PPT 保持可用

#### Scenario: 修改完整大纲中的一讲
- **WHEN** 教师保存了第三讲大纲的新当前修订
- **THEN** 系统只把第三讲已有教案、讲义与 PPT 标记为需更新并说明来源变化
- **AND** 是否重新生成由教师明确操作决定，最后可用版本继续可读

### Requirement: 视觉修订不得修改语义真源
教师只调整 PPT 布局、主题或视觉资产时，系统 MUST 新建视觉修订，不得修改讲稿、教案、教学块或知识语义。

#### Scenario: 教师移动图片
- **WHEN** 教师只移动第二讲第5页图片并保存
- **THEN** 新 PPT 修订继续引用相同教案和讲稿修订
- **AND** 上游正式资产不产生新修订

### Requirement: 学生表达来源合同必须保持兼容
系统 MUST 保持现有学生 CourseDocument 来源、学习和课程级表达读取兼容；旧教师入口退场不得删除学生仍在使用的共享能力。

#### Scenario: 学生打开历史课程
- **WHEN** 学生课程仍使用现有 CourseDocument 和历史课件
- **THEN** 系统继续按原来源合同展示课程与课件
- **AND** 不要求教师讲次资产已经迁移
