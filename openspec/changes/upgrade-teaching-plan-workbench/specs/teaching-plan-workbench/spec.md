# Teaching Plan Workbench Specification

## Purpose

将唯一结构化课程教案从只读投影升级为可审阅、可编辑、可版本化、可影响追踪的教师工作台，同时保持 `CourseTeachingPlanV3` 为课程教学设计唯一语义真源。

## ADDED Requirements

### Requirement: 教案必须分离可变草稿和不可变正式修订

系统 MUST 将 `TeachingPlanDraft` 与正式 `TeachingPlanRevision` 分开。草稿可以自动保存和恢复，但 MUST NOT 被正文、知识库、练习、PPT 或其他正式教学表达消费。用户明确应用后 MUST 创建新的不可变教案修订。

#### Scenario: 教师编辑总体目标

- **WHEN** 教师修改总体教学目标并停止输入
- **THEN** 系统 MUST 保存当前草稿和基础教案修订 ID
- **AND** 当前正式教案、正文和教学表达 MUST 保持不变

#### Scenario: 教师确认教案修改

- **WHEN** 教师查看差异和影响后确认应用
- **THEN** 系统 MUST 创建新的 `TeachingPlanRevision`
- **AND** MUST 记录父修订、变更集、课程修订向量和持久回执
- **AND** 下游任务 MUST 只消费新的正式修订

### Requirement: 编辑能力必须由字段语义控制

系统 MUST 为每个教案字段返回 `editable / requires_impact_review / readonly` 状态和原因。稳定 ID、来源修订、质量状态、绑定 ID 和系统编译字段 MUST NOT 允许直接编辑；章节结构变化 MUST 返回目录编辑入口。

#### Scenario: 教师查看只读知识 ID

- **WHEN** 教师打开知识点的稳定 ID
- **THEN** 页面 MUST 显示该字段由课程知识库维护
- **AND** MUST NOT 提供可写输入

#### Scenario: 教师尝试修改章节结构

- **WHEN** 教师从教案工作台请求删除或排序章节
- **THEN** 系统 MUST 拒绝教案写入
- **AND** MUST 返回 `redirect_to_outline_edit` 与当前目录修订信息

### Requirement: 草稿 patch 必须基于修订和稳定路径

所有草稿修改 MUST 携带 `base_plan_revision_id`、稳定对象路径或对象 ID、预期旧值摘要和幂等键。路径不存在、旧值变化、草稿基础版本过期或重复请求时，系统 MUST 返回结构化结果，不得模糊覆盖。

#### Scenario: 两个页面编辑同一字段

- **GIVEN** 两个草稿操作基于同一个字段旧值
- **WHEN** 第一个操作已经保存后第二个操作提交
- **THEN** 第二个操作 MUST 返回冲突
- **AND** 系统 MUST 保留第一个操作并提供最新草稿值

### Requirement: 正式应用前必须返回确定性差异和影响

系统 MUST 根据字段语义、显式知识关系、课程块绑定和教学表达来源修订计算影响报告。报告 MUST 分组展示 `changed`、`needs_regeneration`、`stale`、`unchanged` 和 `blocked`，不得只返回“可能受影响”。

#### Scenario: 修改一个小节目标

- **WHEN** 教师只修改一个小节的学习目标
- **THEN** 影响报告 MUST 包含该小节正文、目标绑定、相关练习和 PPT 教学单元
- **AND** MUST 将未引用该目标的其他小节列为保持不变

#### Scenario: 修改一个描述性字段

- **WHEN** 教师只修改不参与下游语义编译的策略说明文字
- **THEN** 系统 MUST 只标记教案和教师投影变化
- **AND** MUST NOT 让无关正文、知识和练习失效

### Requirement: 高影响教案变更必须通过质量门和明确应用

知识陈述、能力、易错、掌握标准、模块组合、前置关系和跨小节调整 MUST 在应用前通过现有教案结构、知识绑定、课程一致性和相关质量门。质量阻断或影响不完整时 MUST 禁止正式应用。

#### Scenario: 模块删除导致必需课程块缺失

- **WHEN** 教师删除学科模板要求的必需模块
- **THEN** 系统 MUST 返回结构质量阻断
- **AND** 正式教案 MUST 保持原修订

### Requirement: AI 修改必须成为结构化候选

AI MUST 只返回带结构化 patch、理由、输入修订、影响报告、质量状态和过期时间的 `TeachingPlanOperationProposal`。AI 文本 MUST NOT 直接写入正式教案。

#### Scenario: 教师要求当前小节讲得更具体

- **WHEN** AI 根据当前小节和知识闭包生成改写
- **THEN** 系统 MUST 展示候选前后差异和受影响对象
- **AND** 教师确认前 MUST NOT 修改正式教案或下游产物

#### Scenario: AI 候选基于旧修订

- **WHEN** 教案正式修订在候选生成后发生变化
- **THEN** 候选 MUST 标记 `stale`
- **AND** 系统 MUST 要求重新基于当前修订生成或放弃候选

### Requirement: 正式教案变更必须原子更新并保护旧版本

正式应用 MUST 在同一课程命令中校验教案修订、课程修订、锁定状态和幂等键，并原子保存新教案修订、来源向量、操作日志和应用回执。下游重建失败时，当前教案与最后可用教学表达 MUST 继续可读。

#### Scenario: 下游 PPT 重建失败

- **WHEN** 教案修订已经通过质量门但 PPT 重建失败
- **THEN** 新教案修订 MUST 保留为当前正式教案
- **AND** PPT MUST 标记 `stale` 或 `rebuild_required`
- **AND** 旧 PPT MUST 继续可查看，不得被空产物覆盖

### Requirement: 教案必须支持修订历史和恢复

系统 MUST 展示正式教案修订列表、修改摘要、差异和来源。恢复历史修订 MUST 创建新的当前修订，不得删除之后的版本或回退修订编号。

#### Scenario: 恢复历史教案

- **WHEN** 教师选择历史教案 v2 恢复
- **THEN** 系统 MUST 以当前版本为父级创建新的 vN 修订
- **AND** v2 及中间版本 MUST 继续可查看和比较

### Requirement: 工作台必须支持跨刷新草稿和离开保护

前端 MUST 在桌面和移动视口显示草稿保存状态。草稿保存失败时 MUST 保留本地输入并提供重试；存在未同步草稿时离开页面 MUST 提示继续编辑、重试同步或放弃草稿。

#### Scenario: 刷新后恢复草稿

- **WHEN** 教师刷新仍有未应用的教案草稿
- **THEN** 工作台 MUST 恢复同一课程、同一基础修订和草稿内容
- **AND** MUST 明确显示该内容尚未成为正式教案

### Requirement: 工作台必须维护中英文和响应式可用性

所有新增页面文案、状态、错误、按钮、无障碍标签和字段解释 MUST 同步维护中英文 locale。工作台 MUST 在 390、789、1024 和 1440 像素下保持主体可读、操作可达、无横向溢出和无文字重叠。

#### Scenario: 英文模式查看影响审阅

- **WHEN** 用户切换到英文模式并打开差异/影响面板
- **THEN** 页面 MUST 显示英文文案
- **AND** MUST NOT 出现中文残留或原始翻译 key
