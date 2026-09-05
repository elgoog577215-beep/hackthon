# 设计

## 1. 整合边界

六个领域继续保持各自真源：

- `LearningSnapshot` 拥有可恢复现场。
- `LearningEvent` 拥有不可改写事实。
- `LearningRecord` 拥有可修改的笔记、问题、复习和书签。
- `PracticeAttempt` 拥有正式任务作答生命周期。
- `DiagnosticCase / RemediationSession` 拥有诊断补救状态机。
- `LearningProgress / LearningContinuation` 是确定性投影。

新增 `LearningRuntime` 只能在一次读取中聚合这些对象，MUST NOT 保存第二份运行时状态，也不得通过复制数据解决一致性问题。

## 2. 共享身份契约

`LearningContextRef` 固定包含课程、课程版本、章节、节点、目标与目标修订；存在正文位置时附带内容块修订。所有跨模块对象使用同名字段表达同一身份。

`LearningTaskRef` 固定包含：

- `kind`：reading、practice、diagnostic、remediation、validation、record、review；问题和复习不得混为同一种任务。
- `object_id`：Attempt、诊断案例、补救会话、记录或目标的稳定 ID。
- `task_revision_id`：当前可执行任务修订。
- `status`：active、waiting、completed、stale、abandoned。
- `context`：共享学习上下文。
- `return_node_id` 与可选内容锚点。

`question_revision_id` 只作为历史题目兼容别名。新事件、Attempt、快照和前端动作均以 `task_revision_id` 为主。

## 3. 学习事件 V6

事件顶层增加 `task_revision_id`、`task_purpose`、`diagnostic_case_id` 和 `remediation_session_id`。正式作答事件不得只把这些字段放入 metadata。旧事件读取时继续支持 `question_revision_id` 和 metadata 回退，不批量改写历史账本。

事件类型仍描述事实，不承担当前任务状态；当前任务由 Attempt、诊断仓库和快照联合投影。

## 4. LearningRuntime 聚合投影

运行时一次读取课程、事件、快照、记录、Attempt 和诊断工作流，再把同一批输入传给进度与连续性投影，避免两个投影在不同时间各自重读文件。

输出至少包含：

- `context`：当前课程、章节、节点和目标。
- `revision_vector`：课程版本、事件末端、快照修订、记录修订、Attempt 修订、诊断修订与连续性修订。
- `snapshot`：当前现场与解析结果摘要。
- `progress`：目标进度完整投影。
- `records`：按类型和状态汇总。
- `practice`：活动 Attempt、待评阅和待巩固汇总。
- `diagnostic`：活动阶段、案例、会话与当前任务摘要。
- `active_task`：按连续性优先级归一化的唯一任务引用。
- `continuation`：唯一章节动作与结果。

聚合投影不返回正文、完整答案历史或全部记录内容，避免替代领域 API。

## 5. 前端刷新协议

前端保留各领域 Store，但跨模块状态只通过 `learningProgress.loadRuntime` 刷新。课程首次进入、节点切换、明确阅读完成、记录生命周期变化、Attempt 创建或提交、诊断阶段变化、版本变化和网络恢复触发刷新；滚动、草稿每次输入、提示展开和计时器不触发。

领域写操作完成后主动调用运行时刷新，课程页不得再监听内部数组拼接字符串来猜测变化。并发刷新使用请求序号，旧响应不能覆盖新响应。

## 6. 快照任务协调

开始或恢复 Attempt 后，前端把统一 `LearningTaskRef` 写入快照并尽快 flush。诊断阶段变化时用当前诊断任务替换；任务完成且没有后续工作流时清理为 reading，并保留返回节点。

快照只记录恢复指针，不复制答案、诊断状态或练习结果。真实活动性仍由 Attempt 和诊断仓库决定，快照中的陈旧任务只能影响排序或产生版本冲突，不能复活已完成任务。

## 7. 动作精确路由

`NextLearningAction` 增加标准 `task_ref`。前端执行练习类动作时必须按 `object_id / task_revision_id` 定位目标 Attempt 或诊断任务；找不到时重新加载运行时并显示不可恢复状态，不能静默打开列表第一题。

阅读、记录、版本和章节动作也通过明确 scope 路由，不再使用 `action_type.includes(...)` 推断业务模块。

## 8. 掌握与版本重算

掌握清单从 `LearningProgress.criterion_states` 投影状态，PracticeAttempt 是正式证据真源；旧 `formal_question_answered` 仅兼容历史。课程版本变化后按当前目标、题目和标准修订重算，旧 Attempt、记录和快照保留但不证明当前掌握。

版本恢复或局部再生成完成后，前端必须先刷新课程版本，再加载快照解析与 LearningRuntime。任一环节失败时显示同步异常，不把旧连续性动作当成当前结果。
