## Context

生成器按讲规划 `concept_check`、`objective_practice`、`mastery_check` 三个槽位。编排器已经支持 `practice_levels_by_node`，但题库按题重建入口只传 `node_ids`，因此仍生成整讲。编排器也会返回 `settled_practice_levels`，题库发布回调却在 `event.passed == false` 时直接返回，丢弃已成功槽位。

## Decisions

### 1. 对外只有当前发布修订

普通课程练习题通过结构、可作答性和答案一致性硬检查后直接成为 `approved/published`。任务状态继续使用排队、运行、完成和失败；质量建议不产生题目生命周期状态。综合考核和要求对真实个体采取医疗等高后果行动的题目继续使用既有教师确认门。

### 2. 旧题在替换成功前保持有效

重新生成请求不先写 `rejected`。请求冻结目标题目的稳定 `item_id`、当前 `revision_id`、`node_id`、`practice_level` 和题库基线修订。新题通过后在同一次题库提交中替换；生成、验证或并发检查失败时不改变旧题。

### 3. 最小执行单位是题目槽位

后端从请求的修订解析精确的 `practice_levels_by_node`，并传给现有编排器。整课生成也按 `settled_practice_levels` 逐题合并；章节检查点记录每讲已发布层级，恢复时只请求缺失层级。

### 4. 修复结果必须经过字段白名单

模型仍可返回完整候选以兼容现有 provider，但进入合同编译前必须由服务端生成受控结果：

- 文字或长度问题只能修改 `question_spec.stimulus`、`question_spec.task` 和 `question_spec.constraints`。
- 选项问题只能修改 `question_spec.options` 以及与选项一致的答案字段。
- 解析问题只能修改 `solution.worked_solution` 和 `solution.solution_graph`。
- 答案矛盾允许修改答案、解题步骤，以及报告明确指出的必要题面条件。
- 目标、题型、输入契约和验证器偏离不做局部修复，重新生成当前槽位。

服务端记录 `allowed_paths`、`changed_paths` 和 `restored_paths`。没有允许路径的未知问题默认重新生成当前题，不允许自由覆盖。

### 5. 硬失败与质量建议分开

缺少题面、无法作答、答案缺失、明确答案冲突、输入组件不匹配、损坏 Markdown/代码仍阻断。难度、表达、多样性和模型评审置信度作为发布后的质量信息；它们可以触发一次定向改善，但耗尽改善预算后不阻断基本可用题发布。

### 6. 超时从取得模型容量后开始

容量排队由容量控制器管理并持续发送任务心跳。阶段执行超时只覆盖真实 provider 调用；审计分别记录排队时间和执行时间。

## Failure Handling

- 单题失败：保留旧题或空槽位，并返回稳定错误代码。
- 同讲部分失败：发布成功槽位，失败槽位可独立重试。
- 重生成失败：旧修订和学生可见题目保持不变。
- 并发更新：基线题库修订不一致时拒绝替换并返回冲突，不覆盖较新题库。
- 越界修复：恢复未授权字段；若目标问题仍存在，重新生成当前题。

## Compatibility

历史 `needs_review/rejected` 修订和审阅记录继续读取，不批量改写生产数据。新生成和成功重生成的修订统一写为 `approved/published`。前端不再要求教师批准自动生成题，但仍展示历史状态和质量详情。
