# 设计

## 1. 实体边界

`LearningRecord` 是可修改的当前对象，不是事实事件：

- `note`：用户确认保留的理解、总结或 AI 回答，状态为 `active / archived`。
- `issue`：仍未解决的问题，状态为 `open / explaining / awaiting_verification / resolved / reopened / archived`。
- `review_task`：以后要复习的内容，状态为 `pending / due / completed / dismissed / archived`。
- `bookmark`：只用于返回原文的位置，状态为 `active / archived`，不进入掌握判断。

错题和作答继续属于 `PracticeAttempt / LearningEvent`，不新增第五种“错题记录”。

## 2. 共同契约

每条记录保存稳定 `record_id`、用户、课程、课程版本、节点、目标修订、内容块锚点、引用文本、内容、来源、优先级、标签、状态、修订号和时间。更新使用期望修订号防止跨设备静默覆盖。

内容锚点读取时使用已有语义解析：精确修订、同块更新、指纹映射、节点回退或不可恢复。历史记录不因课程更新而删除；界面必须说明内容是否变化。

## 3. 事实与状态

记录仓库保存当前状态；`LearningEvent` 追加保存 `learning_record_created / learning_record_updated / learning_record_status_changed / learning_record_archived / legacy_learning_record_imported`。学习者模型和 AI 上下文读取当前有效记录及必要事件摘要，不读取前端本地副本。

## 4. 兼容迁移

旧 annotation 迁移规则：

- `user / user_saved` -> `note`
- `ai` -> `note`，并标记历史上是否缺少用户确认
- `wrong` -> `review_task`，来源和低置信迁移状态可见
- `format` 不进入正式仓库

迁移键按用户、课程和旧 annotation ID 幂等。旧接口保留兼容窗口，但生产前端只读取新记录 API。

## 5. 前端行为

正文选区只显示三个主要动作：问 AI、记笔记、稍后处理。稍后处理使用菜单选择“这里不懂 / 需要复习 / 仅做书签”。笔记面板按四类记录提供视图和状态操作；旧错题视图暂保留到正式练习升级阶段，但不再与笔记合并计数。

AI 回答生成结束时不自动创建笔记。每条回答提供明确“保存为笔记”动作，重复点击幂等。
