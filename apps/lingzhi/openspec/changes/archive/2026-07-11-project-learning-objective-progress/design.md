# 设计：学习目标与进度投影

## 1. 真源边界

- 课程版本持有 `LearningObjective`、正文、题目、掌握标准和误区等正式资产。
- `LearningEvent` 持有开始学习、明确学完、正式作答和自我确认等不可改写事实。
- `LearningProgressProjection` 是按当前课程目标修订计算的可重建视图，不另存第二份完成状态。
- `LearningSnapshot` 继续只负责恢复“当前在哪里、正在做什么”，不能代替进度事件。

## 2. 稳定学习目标

每个二级学习节点拥有稳定 `objective_id`，由课程与节点身份决定；目标陈述变化时 `objective_revision_id` 变化。目标绑定包括：

- 当前节点与内容块修订。
- 正式 QuestionRevision。
- MasteryCriterionRevision。
- 通用误区修订。
- 返回正文与正式练习的回退入口。

旧课程在读取时确定性投影这些字段，不改写历史课程文件。

## 3. 两套状态

阅读进度固定为：

- `not_started`：当前目标修订没有学习事实。
- `in_progress`：已开始、作答、自我确认或迁入旧接触证据，但未明确学完。
- `learned`：用户对当前目标修订明确确认已完成阅读学习。

掌握状态固定为：

- `not_checked`：没有掌握证据。
- `evidence_insufficient`：已学完或只有自我确认，但没有有效系统检测。
- `partial`：部分标准通过或证据混合。
- `mastered`：当前目标的全部有效标准均被系统验证。
- `needs_review`：当前有效检测或后续复习显示失败。

自我确认永远不能单独产生 `mastered`。阅读状态与掌握状态互不覆盖。

## 4. 事件与版本

`LearningEvent` 增加 `objective_id` 与 `objective_revision_id`。投影优先使用目标修订；旧正式作答仍可通过当前 criterion revision 映射。课程更新后，目标陈述未变则证据继续有效；目标修订变化后旧证据保留但不参与当前状态，并标记存在历史证据。

## 5. 旧状态迁移

前端只读取一次旧 `learning_stats.completedNodes` 并提交迁移。服务端写入幂等 `legacy_node_completion_imported` 事件，投影最多为 `in_progress`。旧课程级 `is_read` 不再用于新统计、学习路径或掌握判断。

## 6. 前端行为

当前阅读节点显示一条紧凑目标状态条：目标陈述、阅读状态、掌握状态和一个主要动作。

- 学习中：明确“标记本节已学完”。
- 已学完但未掌握：进入正式练习。
- 需要复习：重新进入正式练习。
- 已掌握：查看掌握证据。

打开节点只触发幂等 start API；不会自动完成。正式作答或自我确认后同时刷新资产和进度投影。
