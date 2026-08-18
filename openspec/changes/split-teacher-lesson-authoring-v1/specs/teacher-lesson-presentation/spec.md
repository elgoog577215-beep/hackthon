## ADDED Requirements

### Requirement: 本讲教案可独立启动本讲PPT
系统 MUST 在某讲教案存在可用 working revision 后开放本讲 PPT，不得等待其他讲次、学生课程正文或学生发布。

#### Scenario: 第二讲教案完成
- **WHEN** 第二讲教案草稿生成完成或以警告状态完成
- **THEN** 第二讲显示“PPT可生成”
- **AND** 第一讲、第三讲状态不构成阻断

### Requirement: PPT必须绑定精确教案修订
每个讲次 PPT 修订 MUST 记录 `lesson_unit_id` 和 `source_lesson_plan_revision_id`。教案来源更新不得覆盖或删除最后可用 PPT，而应标记来源过期。

#### Scenario: 教案更新后保留旧PPT
- **WHEN** 第二讲 PPT v1 基于教案 v1，教师将教案更新为 v2
- **THEN** PPT v1 继续可预览和下载
- **AND** 系统显示“来源教案已更新”并允许按需生成新版本

### Requirement: 教师PPT不得依赖学生课程正文
系统 MUST 从讲次教案、讲次知识依据与教师参考资料编译作者态 PPT 来源，并复用现有 PPT 规划、模板、渲染与导出能力；不得为了构建教师 PPT 写入学生 CourseDocument 正文。

#### Scenario: 课程没有学生正文
- **WHEN** 教师课程只存在确认大纲和第二讲教案草稿
- **THEN** 教师仍可生成第二讲 PPT
- **AND** 学生 CourseDocument 与学习数据保持不变

### Requirement: PPT必须支持独立版本和AI优化
系统 MUST 默认提供每讲主课件，数据合同允许补充课件；教师可对整套、单页或连续页面生成 AI 候选并审阅，候选不得直接覆盖已保存版本。

#### Scenario: 优化单页
- **WHEN** 教师选择第二讲 PPT 的第5页并请求 AI 优化
- **THEN** 系统只生成该页候选与差异
- **AND** 其他页面和教案不发生变化
