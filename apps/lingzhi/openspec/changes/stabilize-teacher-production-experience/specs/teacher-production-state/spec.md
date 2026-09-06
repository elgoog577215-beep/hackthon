## Purpose

建立教师课程生产唯一、确定性、可对账的只读状态投影，让课程库、工作台、教学日历和课程文件对同一课程、资产、讲次与失败恢复始终给出同一答案。

## ADDED Requirements

### Requirement: 课程生产状态必须由服务端唯一投影

系统 MUST 从正式任务、正式资产当前修订、来源新鲜度和质量结果确定性生成 `course_production_state_v1`，MUST NOT 持久化第二份课程或任务状态。课程库、工作台、教学日历和课程文件 MUST 消费同一投影，不得在前端重新组合另一套最终状态。

#### Scenario: 最新重试批次只有一个失败讲次
- **WHEN** 一门 16 讲课程已有 15 讲可用，最新重试批次只包含 1 个失败讲次且进度为 `0/1`
- **THEN** 整课投影 MUST 继续返回 15/16 的资产完成情况
- **AND** `0/1` MUST 只出现在最新 attempt 明细中

#### Scenario: 新旧投影迁移期对账
- **WHEN** 新投影与旧兼容字段同时返回
- **THEN** 服务端 MUST 记录有界差异而不改变活动任务
- **AND** 前端 MUST 优先读取新投影，只在新投影缺失时读取旧字段

#### Scenario: 刷新逐讲 PPT 生成页
- **WHEN** 教师在某讲页面内容稿或 PPT 生成期间刷新页面
- **THEN** 页面 MUST 从教师资产任务仓库恢复同一任务身份、进度和控制状态
- **AND** 暂停、取消与继续 MUST 指向该任务的真实所有者，不得调用不存在的 TaskManager 任务

### Requirement: 兼容状态路径必须通过观察门才能退场

旧状态字段和前端 fallback MAY 在迁移期保留，但 MUST NOT 成为新状态权威。系统 MUST 在删除旧推导前完成至少一个完整生产观察周期，并证明新旧投影差异归零。观察门未通过时 MUST 保留兼容路径、活动任务和最后可用资产。

#### Scenario: 观察周期尚未完成
- **WHEN** 尚未完成一个完整生产观察周期，或新旧投影仍存在差异
- **THEN** 系统 MUST NOT 删除旧状态字段、fallback 或重启活动任务
- **AND** `course_production_state_v1` MUST 继续作为唯一最终状态权威

### Requirement: 课程状态与资产状态必须分层表达

课程级主状态 MUST 只使用“备课中”和“备课完成”。资产级主状态 MUST 只使用“未生成”“生成中”“可使用”“生成失败”。暂停、来源过期、待核对、质量建议和最近一次重生成失败 MUST 作为辅助状态或动作表达，不得形成新的主状态词表。

#### Scenario: 可用旧版之后重新生成失败
- **WHEN** 资产已有最后可用修订但最新一次重新生成失败
- **THEN** 资产主状态 MUST 保持“可使用”
- **AND** 投影 MUST 同时返回最新失败、失败范围和恢复动作

#### Scenario: 没有可用版本且任务失败
- **WHEN** 资产没有最后可用修订且最近任务失败
- **THEN** 资产主状态 MUST 为“生成失败”

#### Scenario: 用户主动取消生成
- **WHEN** 用户取消生成且资产没有最后可用修订
- **THEN** 资产主状态 MUST 回到“未生成”，辅助状态 MUST 为“已取消”
- **AND** 取消 MUST NOT 计入最近生成失败或失败数量

#### Scenario: 历史任务状态必须安全归一
- **WHEN** 正式任务记录使用历史 `canceled`、`error` 或 `conflict` 状态
- **THEN** `canceled` MUST 归一为 `cancelled` 且不得计入失败
- **AND** `error` MUST 归一为 `failed`，只有明确可重试时才提供重新生成
- **AND** `conflict` MUST 归一为不可直接恢复的失败辅助态，只允许查看并处理冲突，不得错误提供“继续”
- **AND** 三种状态 MUST 保留原真实 task ID

### Requirement: 显示状态不得代替动作授权

服务端投影 MUST 保留会改变下一步命令的控制状态，并为每个阶段与资产显式返回允许动作。前端 MUST NOT 从四态显示、本地布尔值、检查点是否存在或压缩后的任务状态反推写操作权限。`waiting_for_input`、`waiting_for_review`、质量阻断和未知状态 MUST 分别处理；未知状态 MUST 默认禁止写操作。

需要已有任务身份的动作 MUST 同时在 `action_targets` 中返回它获得授权的精确 task ID 子集。阶段上的动作并集 MUST NOT 把一个可恢复任务的权限扩大到同批未知、不可恢复或缺身份任务。

#### Scenario: 混合批次中只有一个任务可重试
- **WHEN** 同一批次包含一个明确可重试任务和一个未知或不可恢复任务
- **THEN** `allowed_actions` MAY 包含重试与查看原因
- **AND** `action_targets.retry_generation` MUST 只包含明确可重试任务的 ID

#### Scenario: 未确认大纲草稿请求重新生成
- **WHEN** 正式版本仓库存在未确认 blueprint draft
- **THEN** 投影 MUST 返回该草稿事实，并仅在存在真实已完成 outline task ID 时授权重新生成完整大纲
- **AND** 草稿缺少可继续任务 ID 时 MUST 只允许查看原因

#### Scenario: 大纲等待补充输入
- **WHEN** 正式任务状态为 `waiting_for_input`
- **THEN** 投影 MUST 只允许进入补充输入并调用大纲详情继续命令
- **AND** 页面 MUST NOT 显示或调用通用任务恢复

#### Scenario: 大纲等待审阅
- **WHEN** 正式任务状态为 `waiting_for_review`
- **THEN** 投影 MUST 只允许进入审阅或确认流程
- **AND** 页面 MUST NOT 显示通用继续或重新生成

#### Scenario: 检查点存在但恢复合同拒绝
- **WHEN** 任务带有检查点身份但正式恢复合同返回 `can_resume=false`
- **THEN** 投影 MUST NOT 提供继续或重新生成
- **AND** 页面 MUST 只允许查看并处理原因

#### Scenario: 检查点状态没有正式命令所有者
- **WHEN** PPT checkpoint 或历史记录直接使用 `active`、`queued` 等状态，但没有匹配的正式任务所有者与命令合同
- **THEN** 投影 MAY 保留对应的生成中显示和进度证据，但 MUST 只允许查看原因
- **AND** 页面 MUST NOT 从状态名称推导暂停、取消、继续或重试权限

#### Scenario: 正式任务与检查点使用同一任务 ID
- **WHEN** TaskManager 或教师资产仓库的正式任务与 PPT checkpoint 使用同一个任务 ID
- **THEN** 投影 MUST 以正式任务记录的所有者、类型、状态和恢复合同决定动作
- **AND** checkpoint MUST NOT 覆盖或扩张正式任务的动作权限

#### Scenario: 任务类型与命令所有者不一致
- **WHEN** 一个任务的类型属于教师资产仓库，但记录来自 TaskManager，或反之
- **THEN** 投影 MUST 返回稳定的所有者不匹配问题并只允许查看原因
- **AND** `action_targets` MUST NOT 绑定该任务 ID

#### Scenario: 未发布的带警告完成任务
- **WHEN** 任务状态为 `completed_with_warnings` 且 `publication_allowed=false` 或阶段为 `quality_failed`
- **THEN** 投影 MUST 表达质量阻断而不是已完成
- **AND** 只有正式恢复合同明确允许时才能提供恢复动作

#### Scenario: 遇到未知正式任务状态
- **WHEN** 服务端读到非空且不认识的任务状态
- **THEN** 投影 MUST 返回可观察的未知控制状态与稳定问题码
- **AND** 前端 MUST 禁止生成、继续、重试、暂停和取消等写操作

### Requirement: 状态真源读取失败不得被解释为空状态

投影读取 TaskManager、教师资产仓库或大纲草稿真源失败时，MUST 把受影响阶段标记为可观察的 `unknown`，MUST NOT 把“未知”当成“没有任务”、“没有资产”或“可以新建”。已经能够证明的 last-good 内容 MAY 继续显示“可使用”，但受影响阶段只能返回 `inspect_failure`，不得返回任何写操作或动作目标。

#### Scenario: 任务管理器暂时不可用
- **WHEN** 读取路径没有可用 TaskManager，或无法读取该课程的任务集合
- **THEN** 四个生产阶段 MUST 禁止生成、继续、重试、暂停和取消
- **AND** 投影 MUST 保留已知的 last-good 可用性并返回稳定读取失败问题码

#### Scenario: 教师资产仓库读取失败
- **WHEN** 投影无法读取教案、讲义和 PPT 的正式资产与 job
- **THEN** 教案、讲义和 PPT 阶段 MUST 返回 `unknown` 与 `inspect_failure`
- **AND** 页面 MUST NOT 因为资产集合暂时读不到而显示“生成全部”

### Requirement: 状态迁移必须保留任务身份语义

页面 MUST NOT 直接改写任务状态。每次状态迁移 MUST 通过投影授权的后端命令发生，并由正式任务所有者先持久化、再对外确认。需要继续原任务的动作 MUST 携带 `action_targets[action]` 中的精确 ID；重新生成一个新 attempt 时，MUST 保留旧 ID 为授权和溯源依据，但不得把新旧任务冒充为同一条记录。

#### Scenario: 暂停任务继续执行
- **WHEN** 投影对一个暂停任务授权 `resume_generation`
- **THEN** 页面 MUST 提交该动作绑定的精确 task ID
- **AND** 后端 MUST 从该任务的已保存输入和检查点继续，不得按 course ID 猜测 latest

#### Scenario: 教案或讲义批量重试
- **WHEN** 投影对失败教师资产 job 授权 `retry_generation`
- **THEN** 批量请求 MUST 将旧失败 job ID 作为 `resume_job_ids` 提交并校验
- **AND** 新 job MUST 记录 `resume_from_job_id`，其自身使用新稳定 ID，不覆盖旧失败事实

#### Scenario: 取消后再次生成
- **WHEN** 任务已经进入 `cancelled`
- **THEN** 投影 MUST NOT 授权继续或重试该任务
- **AND** 用户重新发起时 MUST 创建新任务 ID，已取消任务仅保留为历史事实

#### Scenario: 未知状态不得迁移
- **WHEN** 投影的控制状态为 `unknown`
- **THEN** 页面只能导航到原因与恢复说明
- **AND** 后端 MUST NOT 根据检查点、本地缓存或 latest 记录自动迁移任务

### Requirement: 整课状态必须以当前讲次全集为范围

整课大纲、教案、讲义和 PPT 的总数与完成数 MUST 以当前课程全部正式讲次计算。任务批次、重试批次和当前选中讲次只描述 attempt，不得改变整课分母。

#### Scenario: 重试失败范围不改变整课分母
- **WHEN** 系统只重试 2 个失败讲次
- **THEN** 整课状态 MUST 继续以全部正式讲次为分母
- **AND** attempt MUST 明确只包含这 2 个讲次

### Requirement: 失败入口必须精确定位且只读

每个需要处理的问题 MUST 返回稳定的阶段、讲次、任务和可选教学块身份。用户点击“处理问题”后 MUST 进入对应对象、突出显示问题并展开完整错误；导航动作 MUST NOT 自动继续、重试、重新生成或改写任务。

#### Scenario: 从课程库进入失败讲次
- **WHEN** 用户点击一门课程的“处理问题”
- **THEN** 页面 MUST 打开准确阶段和讲次并展示完整错误
- **AND** 网络层 MUST NOT 因导航发出写请求

### Requirement: 可用性必须区分硬失败和审阅建议

系统 MUST 分开返回任务完成、结构可用、来源新鲜度和审阅建议。既有合同中的非阻断大纲审阅问题 MUST 显示为“可使用”并附待修正信息；没有最后可用版本且结构硬校验失败时才显示“生成失败”。

#### Scenario: 大纲学时待修正但结构可用
- **WHEN** 大纲结构有效但存在零学时、学时合计不符或其他非阻断审阅问题
- **THEN** 大纲主状态 MUST 为“可使用”
- **AND** 待修正问题 MUST 可定位查看

### Requirement: 教学日历必须展示完整生产链准备度

教学日历 MUST 从同一生产投影展示大纲、教案、讲义和 PPT 四项准备度，并准确说明阻断下一资产的直接原因。教学日历不得成为课程生成的额外门禁。

#### Scenario: 教案可用但讲义缺失
- **WHEN** 某讲教案可用、讲义未生成且 PPT 因此不可开始
- **THEN** 日历 MUST 显示讲义未生成
- **AND** 下一操作 MUST 指向讲义生成而不是 PPT

### Requirement: 来源待核对不得被隐藏或过度阻断

可选 AI 推荐资料尚未核对时，资产 MAY 保持“可使用”，但投影 MUST 返回待核对数量和定位。必需主来源解析失败、绑定冲突或来源过期时，系统 MUST 返回不可用原因和恢复动作。

#### Scenario: 只有可选推荐资料待确认
- **WHEN** 教案结构可用且只有可选 AI 推荐来源尚未由教师核对
- **THEN** 教案 MUST 保持“可使用”
- **AND** 页面 MUST 显示待核对来源摘要

### Requirement: 课程库只显示课程级准备状态

课程库 MUST 只显示备课中或备课完成；阶段失败、任务批次计数与详细恢复信息 MUST 在工作区对应对象展示，不在课程库重复堆叠。

#### Scenario: 单讲重试失败
- **WHEN** 最新批次为 0/1 且课程未完成
- **THEN** 课程库 MUST 显示备课中，工作区仍保留真实全课分母与失败定位


### Requirement: 内容与生成许可必须使用同一当前大纲

系统 MUST 为大纲内容、课程生产状态与教案生成选择同一份当前可用大纲；MUST 排除其他课程、轻量框架和未完成详情；MUST 保留失败新尝试之前的最后可用结果。来源读取失败时 MUST 禁止新生成，且不得修改已有内容。

#### Scenario: 完成的工作区与空课程记录同时存在
- **WHEN** 同课程工作区保存完整 16 讲大纲，而课程记录尚无节点
- **THEN** 内容和状态 MUST 同时显示大纲可用、16 讲可生成教案
- **AND** 刷新 MUST 不触发模型或改写课程

### Requirement: 讲义必须按当前讲的教案准入

系统 MUST 按本讲当前教案的结构可用性、来源新鲜度和有序小节范围决定讲义生成；整课权限 MUST NOT 扩大其他讲次的许可。不可生成时入口 MUST 保持可见并说明原因。

#### Scenario: 只有第一讲完成教案
- **WHEN** 16 讲课程中只有第一讲具有当前可用教案
- **THEN** 批量讲义入口 MUST 仅计入第一讲
- **AND** 第二讲 MUST 保留不可用原因，第一讲完成讲义后亦然

### Requirement: 审阅必须提供可核对依据且不控制生成

大纲审阅 MUST 展示重复目标原句和资源具体缺项，区分无课程资料与已有资料未关联；缺少来源或核验事实 MUST 使用手动补充。分类学时缺项与其造成的总数偏差 MUST 合并。旧规则报告 MAY 在副本上确定性重算，MUST NOT 自动改写课程或调用模型。

#### Scenario: 目标使用相似句式且没有课程参考资料
- **WHEN** 规则发现相似目标和缺少拓展资源
- **THEN** 报告 MUST 将相似句式表述为可能问题并展示原句，资料提示 MUST 指向教师补充
- **AND** 建议 MUST NOT 改变大纲完成状态或教案生成许可
