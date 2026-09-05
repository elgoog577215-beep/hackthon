## Context

见 [proposal.md](./proposal.md)。当前不是缺少任务与恢复能力，而是同一事实被多处重新解释：课程列表的 `_teacher_current_production()` 取最新一次批次，工作台按全课讲次和本地 Store 计算，日历再按教案/PPT 独立计算；因此单讲重试会把整课状态从 15/16 显示成 0/1。任务索引和正式课程已有原子替换，教师全课修改也已有 partial 回执、失败项重试和撤销；设计必须补缺口而不是重建平行系统。

生产环境当前由单个 systemd/uvicorn 进程运行，但代码没有阻止误配为多个任务消费者。现有活动任务属于用户现场，迁移不得重启、改写或重新入队这些任务。当前工作区另有 PPT V6 未提交改动，实施时必须按文件和补丁精确合并。

## Goals / Non-Goals

**Goals:**

- 让服务端纯投影成为课程生产状态的唯一解释者，并删除完成迁移后的重复推导。
- 用分阶段兼容迁移保护活动任务和旧客户端，而不是长期保留双状态真源。
- 只补原子性、崩溃恢复和跨进程缺口，复用现有任务、仓储、课程命令、定向重建与回执。
- 把稳定性门前移到测试、启动、发布和恢复演练，发生不确定状态时安全停写但继续允许读取最后可用内容。

**Non-Goals:**

- 不改变工作区列宽、双侧栏、右侧资料栏常驻和长大纲导航。
- 不处理前端包体，也不在本轮调整蓝紫视觉、渐变、背景或正常动效；无用装饰样式在实施完成后另行讨论。
- 不删除单讲后端能力，不把可选 AI 推荐资料变成硬阻断，不把大纲审阅建议升级为新的确认门。
- 不新建第二个任务系统、第二份生产状态存储、第二个课程正文或第二套定向重建器。

## Decisions

### 1. 状态采用“正式事实所有者 + 唯一纯投影”，不新增状态表

新增后端 `TeacherCourseProductionProjection` 编译器。它按课程读取：

- 大纲任务：TaskManager；
- 教案和讲义任务、当前修订：TeacherLessonAuthoringRepository；
- PPT 任务和检查点：现有 V6 progress/checkpoint 与 TeachingRepresentationRepository；
- 可用性：后端 teacher asset readiness；
- 讲次全集：当前正式大纲/LessonUnit 投影。

编译器只返回 `course_production_state_v1`，不写回任何仓储。核心结构为：

```text
course_id
preparation_state: preparing | prepared
stages[outline|lesson_plan|script|ppt]
  display_state: not_generated | generating | available | failed
  task_state: idle | queued | running | waiting_for_input | waiting_for_review |
              paused | cancelled | failed | completed | unknown
  allowed_actions: generate | pause_generation | cancel_generation |
                   resume_generation | provide_input | review_generation |
                   retry_generation | inspect_failure | regenerate_from_latest_source
  action_targets[action]: task_id[]
  has_unconfirmed_draft?  # outline only; read from the formal version repository
  availability: missing | usable | stale
  counts: total | available | generating | failed | stale
  latest_attempt
  issues[]: stage | lesson_unit_id | block_id? | task_id? | code | summary | recovery
lessons[]
```

选择纯投影而不是新状态表，是为了保持“任务记录执行、资产记录结果、投影负责解释”的单向关系。`generation.ts` 继续合并任务传输事件，`teacherLessonAuthoring.ts` 继续管理资产编辑，但二者不再决定最终显示状态。

`task_state` 还必须保留会改变命令的 `waiting_for_input / waiting_for_review / unknown`；四态 `display_state` 可以为了阅读而压缩，`allowed_actions` 不得压缩。每个需要已有任务的写动作还必须在 `action_targets` 中绑定它真正允许操作的 task ID，混合批次不得因 `allowed_actions` 的并集把可重试权限扩大到未知或不可恢复任务。动作权限优先读取 TaskManager 已有的 `recovery.state / recovery.can_resume / reason_code`、发布回执与质量门，教师资产 job 只在其正式生命周期和显式 `retryable` 范围内补充授权。未知状态、缺失真实 task ID、幽灵检查点和恢复合同拒绝均默认只允许查看原因。

大纲未确认草稿由正式 CourseVersionRepository 保存，TaskManager 只暴露只读边界给投影。投影只在草稿存在且有真实已完成 outline task ID 时，授权 `regenerate_from_latest_source` 并绑定该 ID；草稿缺任务身份时 fail closed。

教师逐讲 PPT V6 不得再只创建进程内 SSE task ID。它的页面内容稿与最终 PPT attempt 由 `TeacherLessonAuthoringRepository.jobs` 统一持久化，至少保存 `course_id / lesson_unit_id / asset_type / type / status / request_snapshot / resume_from_job_id`；V6 progress/checkpoint 只保存可恢复的执行进度，SSE 只传输事件。列表、刷新恢复、暂停、取消、继续和投影必须全部使用同一教师资产 job ID，不得把它误当成 TaskManager ID。进程中断后由持久 job 进入可恢复失败，不假装仍在运行。

### 2. 资产四态使用 last-good 优先规则

投影顺序固定为：

1. 有最后可用修订时主状态为 `available`；暂停、过期或最新 attempt 失败作为辅助信息。
2. 无可用修订且存在活动/暂停任务时为 `generating`。
3. 无可用修订且最新任务失败时为 `failed`。
4. 其他为 `not_generated`。

这样可以同时表达“当前版本可使用”和“本次重新生成失败”，不会因为新 attempt 失败而隐藏好内容。课程两态只由全课投影确定，不复用资产四态词表。

### 3. 新旧状态通过短期双读对账迁移，最终删除旧推导

迁移分三步：后端先并行返回新投影与旧字段并记录低基数差异；前端改为新投影优先、旧字段只在新字段缺失时兜底；连续一个完整发布观察周期差异归零后，删除课程库、工作台、日历和课程文件的独立聚合，以及后端重复计算函数。活动任务始终由原任务所有者继续到终态，不做状态搬迁。

替代方案“直接切换所有页面”风险过高；替代方案“永久保留 fallback”会形成新的脏分支，因此只允许有明确删除门的短期兼容。

### 4. 生成入口收成批量按钮，恢复范围仍是最小单元

教案和讲义正文上方各保留一个主按钮：未生成/部分缺失时显示“生成全部…”，失败时原位显示“重新生成”。按钮始终调用现有批量入口：普通缺失不携带恢复 ID，服务端跳过全部可用讲次；失败恢复必须携带投影 `action_targets.retry_generation` 明确授权的 `resume_job_ids`，后端在创建任何子任务前一次性校验这些 ID 的课程、类型、讲次、来源修订和恢复资格，并且只恢复它们。空 `resume_job_ids` 不得再猜 latest，`cancelled` 不得隐式恢复。恢复路径从原任务检查点续办，不覆盖其他可用内容。右栏保留状态和完整错误，但不再重复提供教案/讲义重试按钮。

状态、显示、动作和命令固定为同一张表；页面不得再从本地 jobs 或 `can_generate` 重写有投影时的结论：

| 正式事实 | 投影 | 页面主显示 | 主动作 | 后端链路 |
| --- | --- | --- | --- | --- |
| 无可用资产、无活动任务 | `not_generated / idle` | 未生成 | 生成全部 | 批量生成，服务端只选择当前可生成的缺失讲次 |
| 无可用资产、正式所有者记录任务排队或运行 | `generating / queued|running` | 生成中 | 暂停或取消 | 只有任务类型、正式所有者和命令能力一致时，才使用投影中的真实 task ID |
| 历史记录或检查点直接使用 `active / queued` | `generating / running|queued` + `inspect_failure` | 生成中 + 状态待处理 | 查看原因 | 原始状态没有对应的正式后端命令时 fail closed，不把状态名称直接换算成写权限 |
| 正式任务与 PPT checkpoint 使用同一 ID | 以正式任务记录为准 | 按正式任务状态显示 | 按正式所有者授权 | checkpoint 只提供进度证据，不能覆盖 TaskManager 或教师资产 job 的命令语义 |
| 大纲任务等待补充输入 | `generating / waiting_for_input` + `provide_input` | 生成中 + 待补充 | 补充并继续 | 只调用大纲详情继续命令，不调用通用 resume |
| 大纲任务等待审阅 | `generating / waiting_for_review` + `review_generation` | 生成中 + 待审阅 | 查看并确认 | 进入正式审阅/确认流程，不调用通用 resume |
| 无可用资产、任务暂停 | `generating / paused` | 生成中 + 已暂停 | 继续 | 批量恢复并复用暂停任务的输入与检查点 |
| 无可用资产、任务已取消 | `not_generated / cancelled` | 未生成 + 已取消 | 生成全部 | 创建新的批量任务，不把用户取消伪装成失败 |
| 历史任务使用 `canceled` 拼写 | `not_generated / cancelled` | 未生成 + 已取消 | 生成全部 | 只做兼容归一，不计入失败，也不恢复旧任务 |
| 无可用资产、最新失败且可重试 | `failed / failed` + `retry_generation` | 生成失败 | 重新生成 | 批量恢复，只重试失败或缺失单元 |
| 历史任务使用 `error` 且明确可重试 | `failed / failed` + `retry_generation` | 生成失败 | 重新生成 | 复用真实 task ID 和检查点；未明确可重试时只查看原因 |
| 任务因修订冲突进入 `conflict` | `failed / failed` + `inspect_failure` | 生成失败 + 内容已变化 | 处理冲突 | 不显示继续或重新生成，不向失败任务发送恢复命令 |
| 有 last-good、最新重生成失败且可重试 | `available / failed` + `latest_attempt_failed` + `retry_generation` | 可使用 + 最近失败 | 重新生成 | `regenerate_ready=true`，只纳入带失败 attempt 的可用讲次 |
| 最新失败明确不可重试 | `failed|available / failed` + `inspect_failure` | 生成失败或可使用 + 失败说明 | 查看并处理原因 | 不显示重新生成，不发生成请求 |
| `completed_with_warnings` 且已发布 | `available / completed` + review issue | 可使用 + 待修正 | 查看建议 | 发布回执为真源，不重复生成 |
| `completed_with_warnings` 但质量门阻断 | `failed|available / failed` + 显式恢复合同 | 生成失败或可使用 + 质量阻断 | 重新生成或查看原因 | 仅 `recovery.can_resume=true` 时开放恢复 |
| 非空未知任务状态 | `failed|available / unknown` + `inspect_failure` | 生成失败或可使用 + 状态待处理 | 查看原因 | 所有写操作 fail closed，并记录稳定问题码 |
| 任务或资产真源读取失败 | `failed|available / unknown` + 读取失败 issue | 生成状态暂时无法确认 | 查看原因 | “未知”不得当成“空”；last-good 可读，任何写动作关闭 |
| 全部当前资产可用、无失败 attempt | `available / completed|idle` | 可使用 | 无恢复动作 | 不创建任务；主动重生成继续走独立确认流程 |

前端共享适配器直接消费投影的 `allowed_actions` 并选择页面主动作；业务组件只负责显示已获授权的按钮并路由到既有命令。旧 jobs 仅在整份新投影缺失时做 fail-closed 兜底，不能与新投影共同投票，也不能仅凭状态名或检查点存在猜测恢复能力。

动作授权是 `任务状态 × 正式所有者 × 任务类型 × 恢复合同 × 精确任务 ID` 的联合结果。任何一项缺失或不一致时只能查看原因；显示层可以继续表达“生成中”或 last-good“可使用”，但不得因此开放暂停、取消、继续或重试。

状态迁移只由正式任务所有者执行，投影与页面都不直接写状态：

| 当前控制态 | 合法命令 | 身份处理 | 非法捷径 |
| --- | --- | --- | --- |
| `idle / cancelled` | 新建生成 | 创建新 task/job ID | 不恢复已取消 ID，不猜 latest |
| `queued / running` | 暂停或取消 | 使用对应 action target 中的原 ID | 不用阶段任务 ID 并集扩大范围 |
| `waiting_for_input` | 补充输入 | 沿用原大纲 task ID 进入专用继续命令 | 不调通用 resume、cancel 或 retry |
| `waiting_for_review` | 进入正式审阅/确认 | 沿用原 task ID | 不调通用 resume、cancel 或 retry |
| `paused` | 继续 | TaskManager 沿用原 ID；教师资产批量恢复以原 job ID 授权并创建可溯源新 job | 不用 course ID 或选中讲次猜测 |
| `failed` 且明确可恢复 | 重试 | TaskManager 使用原 ID；教师资产新 job 记录 `resume_from_job_id` | 不重放其他已成功单元 |
| `completed` | 无恢复命令 | 原 ID 终态保留；主动重生成另走确认并新建 | 不把完成任务改回运行态 |
| `unknown` 或真源不可读 | 仅查看原因 | 不产生新 ID，不改原记录 | 不根据缓存、检查点或页面布尔值迁移 |

动作路由也固定到正式所有者，不能只在页面层统一按钮名称：

| 阶段与动作 | 前端命令 | 后端正式所有者与校验 | 任务身份结果 |
| --- | --- | --- | --- |
| 大纲新建 | 提交课程信息并创建大纲任务 | `TaskManager.create_task` 校验课程与活动任务冲突 | 创建新 task ID |
| 大纲暂停、取消 | `/tasks/{task_id}/pause`、`DELETE /tasks/{task_id}` | `TaskManager` 按投影目标 ID 校验当前状态并严格持久化 | 沿用原 ID 进入 `paused/cancelled` |
| 大纲等待补充 | `/generation/outline-details/continue` 携带 `task_id` | `continue_teacher_outline_details(course_id, task_id)` 同时校验课程、类型和 `waiting_for_input` | 沿用原 ID，不调用通用 resume |
| 大纲失败重试或暂停继续 | `/tasks/{task_id}/resume` | `TaskManager.resume_task(task_id)` 复核 recovery、来源和检查点 | 沿用原 ID |
| 教案、讲义新建 | `lesson-plans/generate-all`、`lesson-scripts/generate-all` | 教师资产仓库只选择当前缺失且满足上游条件的讲次 | 每讲创建新 job ID |
| 教案、讲义暂停、取消 | `lesson-jobs/{job_id}/pause`、`DELETE lesson-jobs/{job_id}` | 教师资产仓库按精确 job ID 校验课程、类型和当前状态 | 原 job 进入 `paused/cancelled` |
| 教案、讲义继续或重试 | 同一批量入口携带 `resume_job_ids` | 在创建任务前一次性校验课程、资产类型、讲次、来源修订和恢复资格 | 每讲创建新 job ID，并保存 `resume_from_job_id` |
| PPT 新建或主动重生成 | 进入 PPT 工作区后调用 V6 build stream | 教师 PPT job 所有者校验课程、讲次、来源与页面内容稿 | 创建新 job ID |
| PPT 暂停、取消 | 教师 `lesson-jobs` 的 pause/delete | 教师资产仓库按投影目标 ID 校验当前状态 | 原 job 进入 `paused/cancelled` |
| PPT 暂停继续或失败重试 | V6 build stream 携带 `resume_task_id` | 只接受同课程、同讲次、同 PPT 类型且正式可恢复的教师资产 job | 创建新 job ID，并保存 `resume_from_job_id` |
| 查看原因、处理问题 | 只导航 stage、lesson、block、task、issue | 不进入任务所有者，不执行写命令 | 不创建或修改任何 ID |

服务端投影、前端解析器和后端命令入口共同遵守以下不变量：任务型写动作没有 `action_targets[action]` 就不得显示或执行；`waiting_for_input / waiting_for_review / unknown` 不得被通用继续或重试吸收；`cancelled` 只能新建；恢复新 attempt 必须保留旧 ID 作为授权与溯源，不能覆盖旧失败或取消事实。

全局 `CourseTaskCenter` 是 TaskManager 的管理面，不是课程生产状态的第二权威。它可以依据所选任务详情和 `recovery` 对导入、旧整课生成等任务执行暂停、恢复、审阅或确认删除，但每次都必须使用当前 `selectedTask.id`，不得按 course ID 猜任务；课程库、工作台、日历和文件空间仍只以 `course_production_state_v1` 决定生产状态与主操作。

底层单讲端点暂不删除，因为它仍可作为批量执行器内部能力和旧客户端兼容。加入调用观测，确认无外部调用并完成合同迁移后再单独决定退场。

教案知识关系仍校验端点、身份和字段完整性，但不再比较 `prerequisite` 端点与知识注册表或课程小节的相对顺序。现有骨架 `future_prerequisite` 与批次 `reversed_prerequisite` 阻断退出生成链，避免知识关系的解释差异使可用教案整体失败。

### 5. UI 改动只处理已确认的状态与操作语义

- 所有状态词由共享映射渲染，中文与英文同时维护。
- 经其余实施完成后的截图讨论，失败信息采用三级职责：顶部只提示课程级失败数量，正文对象旁只保留局部失败状态和原位恢复，右栏保留完整原因、恢复说明和必要技术细节；具体错误不在三处重复。
- 大纲完整度字号和紧凑图标尺寸保持不变，不借本项调整三栏、密度或现有蓝紫视觉。

### 6. 生命周期严格写盘，高频进度保持 best-effort

TaskManager 的创建、暂停、恢复、取消、确认、失败和完成使用 copy-on-write 状态更新：先构造下一状态并严格保存，成功后再发布内存状态和事件；失败时保留上一状态并返回稳定错误。心跳、流式字符和高频百分比继续有界 best-effort，避免短暂磁盘抖动中断用户生成。

这比把所有 `save_tasks()` 一律改成 strict 更安全，也避免每个 token/进度事件都成为同步磁盘门。

### 7. 任务索引使用 last-good 和 degraded 模式

成功替换主索引后更新可校验的 last-good 副本。启动时先取得数据目录 leader lock，再加载主索引；主索引损坏或超限时隔离原文件并读取 last-good。两份都不可用时保留课程读取能力，但任务创建、恢复和重新生成返回稳定 degraded 错误，禁止把任务集合静默当成空集合。

任务 consumer 只能在索引加载和恢复对账完成后启动，避免当前“先启动 consumer、再逐任务恢复”的竞态。

### 8. 单领导者使用数据目录进程锁，不立即迁移数据库队列

生产目标是 Linux systemd 单实例，因此先使用标准库文件锁持有数据目录领导者身份，并在启动日志与 readiness 中公开结果。第二实例在读取和改写任务前失败退出；只读维护工具使用显式只读模式。

立即迁入数据库队列会同时改变部署、任务语义和恢复路径，风险高于本轮目标。文件锁只是当前单机部署的安全约束；未来横向扩容时再用外部 lease/队列替换。

### 9. 通用 JSON 只通过一个原子 update_data 入口读改写

`Storage.save_data()` 改为同目录临时文件、flush、fsync、replace，替换成功后才更新深拷贝缓存。新增 `update_data(filename, updater)`：取得跨进程锁后重新读盘、执行纯 updater、原子保存并刷新缓存。使用事件、学习事件和删除回执等读改写账本按风险排序迁入该入口。

不只给现有写方法加文件锁，因为永久 `_data_cache` 仍会把旧快照覆盖回磁盘。

### 10. 跨资产变更只补逐操作 journal

沿用现有 CourseEvolutionPlan、课程 command group、partial 回执、失败项重试和 CAS 撤销。新增每个 operation 的 `pending → applying → applied|failed` journal；资产提交后立即保存结果修订。恢复时对账正式仓储：匹配目标修订则补记 applied，不匹配才进入重试或冲突，绝不盲目重放。

定向重建继续使用现有 dependency graph 和共享 executor，按教案/讲义块、V6 page ID、题库最小合法单元逐步补齐。跨讲结构操作在部分接受后重新编译操作 DAG，并通过现有原子课程命令提交。

结构引用迁移按稳定讲次身份处理：移动和换序不改 lesson ID；合并保留 primary target ID，其他 source ID 写墓碑，显式依赖迁到 primary；拆分只有一个 primary 继承 source ID，其他 target 使用稳定新 ID。合并和拆分不拼接、复制正式教案、讲义、PPT 或题库内容；这些资产保留 last-good，同时写入 `stale/rebuild_required` 和引用迁移回执，后续由已有共享 executor 定向重建。重绑和失效标记作为现有 domain candidate operation 执行，每个正式仓储使用稳定 operation ID、逐操作 journal、partial 失败续办和 CAS 撤销，不另建状态机或执行器。

### 11. 健康、发布、备份和指标各自承担不同证据

- `/health` 只证明进程存活。
- `/api/health` 快速证明版本、leader、任务索引和数据目录可用；只检查文本模型配置，不发真实模型请求。
- 发布探测继续承担指定模型真实请求和生产进程角色验证。
- 发布脚本在停止服务前检查活动任务；有不可安全中断任务时退出并保留当前版本。
- 备份增加 manifest、checksum 和隔离临时目录恢复验证。
- 指标只使用状态、错误码和耗时等低基数字段，不记录课程正文、提示词或用户材料。

### 12. 历史课程只做复制升级

升级读取旧课程当前可见内容，在隔离工作区编译新 LessonUnit 和 CourseDocument；完整校验通过后才发布为新 course ID。旧课程 checksum 不变，旧教案历史不进入新课程。失败只清理未发布工作区并保留迁移报告。这与“历史课程兼容读取、不执行原地迁移”的既有边界一致。

## Risks / Trade-offs

- [新旧投影短期并存可能增加复杂度] → 兼容代码必须带差异指标、截止条件和删除任务；不得成为永久 fallback。
- [四种主状态可能隐藏暂停或旧版可用] → 保留独立 `task_state`、`availability` 和 issues，不把所有语义压进 `display_state`。
- [严格写盘可能让生命周期操作暂时失败] → 仅收紧低频边界，高频进度不受影响；失败时保留上一可恢复状态并明确提示。
- [leader lock 误判可能阻止服务启动] → 锁在读取任务前取得，提供持有者诊断信息和离线只读模式；不自动删除未知锁。
- [通用账本迁移触发历史缓存行为差异] → 逐账本迁移并加入并发、replace 失败和缓存不变测试，不进行一次性全仓替换。
- [跨资产 journal 与现有回执重复] → journal 只记录执行边界，总回执继续承担用户可见结果；恢复完成后由 journal 汇编而非另建业务状态。
- [发布等待活动任务可能延迟上线] → 这是保护用户现场的显式取舍；提供可观察的等待原因，不自动取消任务。
- [历史复制升级可能扩大数据量] → 只在教师明确确认后创建新课程，失败不发布，旧课程不复制历史修订。

## Migration Plan

1. 修复测试收集、Ruff 开发依赖和发布前验证，但不触碰运行任务。
2. 上线只读 `course_production_state_v1`、冲突样本测试和新旧投影差异指标；保持所有旧消费者。
3. 课程库、工作台、教学日历、课程文件依次切换为新投影优先；完成按钮、错误全文、字号和真实按钮热区改动。
4. 验证刷新、SSE、失败恢复、旧版可用、0/1 attempt 与 15/16 整课状态；观察一个发布周期。
5. 删除前端独立推导和后端重复聚合，保留旧响应字段一个兼容周期后停止写入。
6. 依次上线原子通用存储、last-good/degraded、leader lock 和生命周期严格保存，每步均先做故障注入测试。
7. 上线逐操作 journal，并复跑现有 partial、撤销和崩溃恢复测试；随后补定向重建和跨讲结构操作。
8. 上线 readiness、活动任务发布保护、备份校验和低基数指标；生产只做只读或隔离恢复演练。
9. 最后开放历史课程复制升级，并以旧课程 checksum、新课程映射和失败清理作为发布门。

回滚时前端恢复读取旧兼容字段；后端新投影是只读能力，可独立关闭。任何存储格式变化必须保持旧读路径或在写入前备份，回滚不得删除 journal、last-good 或教师正式资产。

## 2026-09-05 全局修改与失败恢复补充设计

- 学生视角预览保持现有入口与功能。PPT 不改写；公共结构引用仍按已有合同标记来源过期并保留 last-good。
- 精确替换读取完整可编辑字段，摘要仅用于召回与展示。讲次删除/移动以稳定 ID 编译结构候选，教师确认后才应用；语义扫描保存覆盖清单。
- 请求、方案、候选尝试分别有稳定身份；候选任务复用现有持久 job，逐对象保存成功操作与错误，刷新/断流不取消。保存使用方案修订与尝试身份校验，拒绝迟到结果覆盖放弃或修订。
- 同讲教案和讲义候选按依赖生成，讲义承接本轮教案候选内容与身份；应用解析为实际修订并保持来源校验，不直接更改来源 ID 冒充一致。
- 前端单一适配逻辑区分候选失败、部分应用、已放弃、已撤销、部分撤销；所有异步响应核对课程和请求归属。新要求打开对应新方案，历史展示完整回执与差异。
- 生成失败保留错误类别、质量报告和具体恢复范围；原输入恢复继续使用冻结快照，补充输入显式创建关联新尝试并重新校验可复用块。非阻断教学建议不升级为生成硬门。
- 全局修改直接进入现有中心。默认教师只处理要求、范围、正文差异与应用，技术枚举收进详情；课程库只保留备课中/备课完成。

### 本轮实现与验收边界

`teacher_script_quality_v9` 将直接讲授措辞、缺少过渡、罐头表达和重复过渡四项语言启发式降为建议；不降低空正文、结构/来源、占位、内容不全、正文重复和深度检查。仅已知 v8 报告随当前代码重算，未知版本不自动升级。正文未改动的报告升级不调用模型。

本轮只完成第 10 节修复。第 9.1、9.2 节生产观察与兼容退场继续未完成，不随本轮归档。运行验收使用独立目录中的合成课程和故障样本；未操作现有用户任务，未部署生产。完整结果见 `docs/事实.md` 的同日全局修改与失败恢复记录。


轻量讲次方案本身可以满足 `has_unconfirmed_draft=true`，但只要服务端仍处于 `waiting_for_input`，继续按钮 MUST 读取 `provide_input` 与其对应 task ID；只有完成后的草稿修改才进入 `regenerate_from_latest_source`。按钮是否可见和执行目标必须复用同一动作判定，不能各自按草稿状态猜测。

本轮验收：后端 `3998 passed`（另 3 skipped、2 xfailed、1 xpassed）、根目录后端 `112 passed`；前端相关 8 文件 `178 passed`（包括新增大纲等待态与草稿组合回归），构建、运行级 Ruff 和 strict change 校验通过。独立数据中的真实指定模型完成影响分析与同讲两资产候选/应用，桌面验证关闭页面后同一 job 恢复观察、精确替换/结构删除的应用撤销以及两种失败恢复。用户新增反馈对应的原课程只读核验了继续按钮恢复，没有启动用户下一步生成。PPT 和生产发布未纳入本轮。

### 完整大纲步骤稳定性补充（2026-09-05）

大纲第三步不是内部 phase 名称的映射。已有 TaskManager 在教师继续命令中持久化 `outline_detail_requested`；沿原任务回执、WebSocket 和轮询把它传到同一 generation Store。页面只读该事实决定步骤，子阶段仍负责具体进度与文案；缓存只保存最近服务端现场，联网后按相同 task ID 对账。不得为步骤维护平行状态表，也不得依据该布尔值开放写权限。

### 完整大纲交付前自动优化（2026-09-05）

只在本次完整大纲生成内运行，轻量方案、打开页面、读取报告和保存教师修改均不触发。先按字段语义合并详情：全零学时属于未填写，不能覆盖有效详情；已填写学时和其他教师字段保持原值。对新生成部分先按已确认总学时、授课模式和现有比例确定性校正，再将目标、达成检验、学习任务等建议合并交给既有 `propose_outline_adjustment`，使用同一 `apply_outline_operations` 与大纲审阅校验。禁止模型更改讲次身份、标题、顺序、来源清单、教师非空字段或无关内容。

最多两轮模型优化，每轮只采用通过结构校验、未增加其他自动问题且实际减少目标问题的结果。来源只可选择已有来源，新增书籍版次与定位不得自行宣布核验；资料不足保留待补充。结果、轮次、输入身份和安全失败码保存在现有 outline 阶段检查点；调用前记账，恢复不重置额度，已接受结果保留。优化失败不抹去已完成大纲，也不将剩余建议伪装成全部解决；暂停/取消继续沿原 task ID。

### 教案与讲义的同源收尾

教案在正式保存前复用 `optimize_teacher_lesson_plan`，最多两轮处理最终质量报告；保持小节与教学块身份、顺序、知识、来源和时间，只有复审改善才采用。原始模型失败/本地保底、来源过期和知识冲突仍按原失败合同处理，不能通过润色绕过。优化过程与最后候选保存在同一个教师 job，校验失败不写正式修订。

讲义单块生成把语言与衔接建议一并送回现有修复循环，保留最好且通过硬校验的结果；可修复结构失败仍沿原两次检查和压缩路径。整讲汇编再复用原 block repair generator 定点处理跨块重复、深度与连接问题，成功块及原教案合同保留，最多两轮后按同一正式质量规则决定能否保存。生成、修复、复验始终属于原 job，教师编辑/候选确认路径不自动改文。启发式措辞建议不是绝对正确性的证明，不能通过伪造内容或降低既有硬校验取得完成状态。
