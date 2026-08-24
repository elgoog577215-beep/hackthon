## ADDED Requirements

### Requirement: 本讲PPT必须从已确认讲稿启动
系统 MUST 在本讲存在 confirmed script revision 后开放正式 PPT 生成，不得等待其他讲次、题库或学生发布，也不得从未确认教案或学生正文直接生成教师正式 PPT。

#### Scenario: 第二讲讲稿已确认
- **WHEN** 第二讲讲稿确认完成而其他讲次尚未备课
- **THEN** 第二讲显示“PPT可生成”
- **AND** 第一讲、第三讲、题库和学生正文状态不构成阻断

### Requirement: PPT必须绑定精确教案与讲稿修订
每个讲次 PPT 修订 MUST 记录 `lesson_unit_id`、`source_lesson_plan_revision_id` 和 `source_script_revision_id`。来源更新不得覆盖或删除最后可用 PPT，而应标记精确过期原因。

#### Scenario: 讲稿更新后保留旧PPT
- **WHEN** 第二讲 PPT v1 基于教案 v2 和讲稿 v1，教师把讲稿确认到 v2
- **THEN** PPT v1 继续可预览和下载
- **AND** 系统显示“来源讲稿已更新”并允许按需生成新版本

### Requirement: 教师PPT不得建立重复语义来源
系统 MUST 从已确认讲稿块、其教案来源、讲次知识依据与教师选择的视觉资料编译 `SlideDeckV6` 来源。系统 MUST NOT 同时拼接“整段讲稿”和“教案模块”作为两个可互相冲突的内容真源。

#### Scenario: 编译第二讲V6来源
- **WHEN** 教师生成第二讲主课件
- **THEN** 每个教学单元以讲稿块为内容语义来源并保留教案块追溯
- **AND** 学生 CourseDocument 与学习数据保持不变

### Requirement: 视觉模板不得反向改变教学结构
视觉模板 MUST 只控制页面容量、版式、主题和视觉资产。分页和压缩不得更改本讲课型、教学块顺序、知识语义或教师确认的讲稿文字。

#### Scenario: 切换高密度模板
- **WHEN** 教师把第二讲 PPT 从宽松模板切换到高密度模板
- **THEN** 系统可以重新分页和布局
- **AND** 教学块顺序、讲稿语义和来源修订保持不变

### Requirement: PPT必须支持独立版本和AI优化
系统 MUST 默认提供每讲主课件，允许教师对整套、单页或连续页面生成 AI 候选并审阅；候选不得直接覆盖已保存版本，失败必须保留最后可用版本。

#### Scenario: 优化单页
- **WHEN** 教师选择第二讲 PPT 的第5页并请求 AI 优化
- **THEN** 系统只生成该页候选与差异
- **AND** 其他页面、讲稿和教案不发生变化
