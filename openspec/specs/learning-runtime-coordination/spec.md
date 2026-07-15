# learning-runtime-coordination Specification

## Purpose
TBD - created by archiving change integrate-learning-runtime-contract. Update Purpose after archive.
## Requirements
### Requirement: 前六步必须共享稳定身份契约

系统 MUST 使用统一课程版本、目标修订、任务修订和内容锚点字段连接学习现场、进度、记录、练习、诊断和章节连续性；新写入 MUST 以 `task_revision_id` 为正式任务修订字段。

#### Scenario: 正式练习形成学习事件

- **WHEN** 当前 Attempt 被创建、提交或评分
- **THEN** 事件顶层 MUST 保存 task_revision_id、task_purpose 和目标修订
- **AND** question_revision_id MUST 只作为兼容别名

### Requirement: 学习运行时必须聚合同一批输入

系统 MUST 在一次运行时读取中加载事件、快照、记录、Attempt 和诊断工作流，并用同一批输入构建进度与章节连续性；MUST NOT 保存第二份运行时状态。

#### Scenario: 作答同时改变掌握与下一步

- **WHEN** 正式 Attempt 完成评分并形成新的诊断阶段
- **THEN** 同一运行时响应中的 progress、diagnostic、active_task 和 continuation MUST 相互一致
- **AND** revision_vector MUST 反映所有发生变化的来源

### Requirement: 掌握清单必须读取正式 Attempt 投影

掌握清单 MUST 从统一学习进度中的标准状态投影，不得只读取旧 `formal_question_answered` 事件。

#### Scenario: 当前标准已有独立通过 Attempt

- **WHEN** 当前题目、目标和标准修订绑定一致的 Attempt 独立通过
- **THEN** 目标进度和掌握清单 MUST 同时显示 system_verified

### Requirement: 写操作后必须确定性刷新运行时

前端 MUST 在明确阅读、学习记录、Attempt、诊断或课程版本发生语义变化后主动刷新 LearningRuntime；MUST NOT 依赖组件监听内部数组猜测变化。

#### Scenario: 用户解决阻塞问题

- **WHEN** issue 状态从 open 更新为 resolved
- **THEN** 前端 MUST 主动刷新运行时
- **AND** 旧的 resolve_blocking_issue 动作 MUST NOT 继续显示

### Requirement: 快照必须保存统一任务引用

学习快照 MUST 使用 LearningTaskRef 保存当前恢复指针，普通练习、诊断、补救和独立复验 MUST 使用同一结构；快照 MUST NOT 复制业务对象状态。

#### Scenario: 用户开始普通正式练习后刷新

- **WHEN** Attempt 已创建且仍为 in_progress
- **THEN** 快照 task_ref MUST 指向该 Attempt 和 task_revision_id
- **AND** 运行时 active_task MUST 与 Attempt 真源一致

### Requirement: 连续性动作必须精确恢复目标任务

前端 MUST 按 NextLearningAction.task_ref 精确定位 Attempt 或诊断任务；MUST NOT 只打开通用练习页并默认选择第一题。

#### Scenario: 第二道题存在未提交草稿

- **WHEN** 主要动作指向第二道题的 active Attempt
- **THEN** 练习工作区 MUST 选中该 Attempt 对应任务并恢复其草稿
- **AND** MUST NOT 自动创建或打开第一道题的新 Attempt

### Requirement: 课程版本变化必须触发六步统一重算

课程版本变化后，系统 MUST 重新解析快照位置、当前目标、正式任务有效性、诊断有效性和章节连续性，并保留旧对象作为历史。

#### Scenario: 恢复历史版本创建新课程版本

- **WHEN** 新课程版本成为 current
- **THEN** 前端 MUST 先刷新课程再加载快照与 LearningRuntime
- **AND** 旧版本活动任务 MUST 显示版本冲突或失效，不得静默继续

### Requirement: 旧字段只能作为读取兼容

历史 question_revision_id、旧快照 task_state 和旧正式作答事件 MUST 可读取；新路径 MUST NOT 再将其作为唯一字段或实时真源。

#### Scenario: 历史 Attempt 只有 question_revision_id

- **WHEN** 系统读取旧 Attempt
- **THEN** 归一化任务引用 MUST 回退到 question_revision_id
- **AND** 后续新事件 MUST 写入正式 task_revision_id

### Requirement: 标准课程主学习链必须可重复验收

系统 MUST 支持使用隔离用户仅通过公开 API 连续完成首次进入、阅读进度、跨设备恢复、学习记录、正式练习、诊断补救、章节连续性和 AI 老师协议验收。验收 MUST 使用同一当前课程版本与稳定对象身份，MUST NOT 直接修改持久文件或临时注入缺失课程资产。

#### Scenario: 隔离用户完成标准课程主链

- **WHEN** 验收用户从一门 strict ready 标准课程首次进入并依次执行主学习链
- **THEN** 每项领域写操作 MUST 由正式 API 持久化并反映到 LearningRuntime
- **AND** 课程版本、内容锚点、任务修订、诊断案例和补救会话 MUST 保持可追踪

### Requirement: 主学习链必须保持唯一连续性动作

主学习链每个稳定阶段 MUST 由 LearningContinuation 产生至多一个 primary action。AI 老师、学习记录、正式练习和诊断模块 MUST NOT 创建与该动作竞争的第二主行动。

#### Scenario: 学习者从阅读进入诊断补救

- **WHEN** 用户先完成阅读，随后产生正式失败、诊断任务和补救会话
- **THEN** primary action MUST 按当前正式状态依次指向掌握检查、诊断任务、补救任务和独立复验
- **AND** 每次动作变化 MUST 能由当前版本的正式证据解释

### Requirement: 掌握检查动作必须指向具体正式任务

系统 MUST 为 `start_mastery_check` 返回与当前目标和节点一致的正式 `mastery_check` 任务修订；尚未创建 Attempt 时 MUST 使用空对象 ID 表示待开始任务，不得把学习目标修订伪装成练习任务修订。

#### Scenario: 阅读完成后进入掌握检查

- **WHEN** 当前目标已经完成阅读且存在正式掌握检查题
- **THEN** primary action 的 task_ref.kind MUST 为 practice
- **AND** task_revision_id MUST 等于该掌握检查题的任务修订
- **AND** 前端 MUST 选中该题但不得在用户确认前自动创建 Attempt

### Requirement: 前端任务型主动作必须按任务引用路由

前端 MUST 使用 `NextLearningAction.task_ref.kind` 区分普通练习、诊断、补救和独立复验；MUST 从正文中的对应任务入口打开统一 `TaskOverlay` 并精确定位任务修订，MUST NOT 维护基于动作 scope 的第二套任务路由真相或切换独立练习模式。

#### Scenario: 连续性动作进入指定任务

- **WHEN** primary action 携带可用的 practice、diagnostic、remediation 或 validation 任务引用
- **THEN** 学习现场 MUST 聚焦对应正文任务入口并打开该任务修订
- **AND** 任务不存在或已失效时 MUST 在原入口显示失效状态，不得退回第一题

### Requirement: 连续性动作展示必须共享同一翻译

连续性条、学习者画像和学习统计 MUST 使用同一套动作标签与原因码翻译；中文和英文界面 MUST NOT 向用户显示原始 action_type 或 reason_code。

#### Scenario: 多个界面展示同一下一步

- **WHEN** LearningRuntime 的 primary action 为 start_mastery_check
- **THEN** 所有可见消费者 MUST 表达相同的“掌握检查”动作和原因
- **AND** 切换英文后 MUST 使用对应英文词条

### Requirement: 浏览器主链验收必须隔离学习者身份

前端 MUST 支持在显式验收配置下发送 `X-User-Id`，浏览器验收 MUST 使用一次性隔离用户；未配置身份覆盖时 MUST 保持现有运行行为。

#### Scenario: 验收课程主链

- **WHEN** 验收服务器配置了 VITE_LEARNER_USER_ID
- **THEN** 前端所有学习领域请求 MUST 携带该用户身份
- **AND** 产生的正式学习对象 MUST NOT 写入 default_user

### Requirement: 版本变化必须提供可执行迁移计划

系统 MUST 根据当前课程版本、旧快照、活动 Attempt、诊断工作流和学习记录投影唯一版本迁移计划；计划 MUST 区分可安全重映射、需显式确认、必须失效和仅保留历史的对象。

#### Scenario: 旧学习现场遇到新课程版本

- **WHEN** LearningSnapshot 或活动任务的课程版本不是当前版本
- **THEN** LearningContinuation MUST 返回 confirm_version_change 主动作
- **AND** 迁移计划 MUST 说明目标版本、锚点解析状态和受影响对象
- **AND** 前端 MUST NOT 仅通过切换版本页面解除阻断

### Requirement: 版本确认必须校验运行时修订并保持幂等

版本确认命令 MUST 校验客户端读取的连续性投影修订；修订过期时 MUST 拒绝写入并返回当前投影。重复确认同一版本变化 MUST NOT 重复失效对象或追加重复事实。

#### Scenario: 用户确认处理版本变化

- **WHEN** 用户提交当前 projection revision 和幂等请求 ID
- **THEN** 服务端 MUST 串行迁移当前学习现场并失效旧活动任务
- **AND** 旧 Attempt、诊断和记录的历史课程版本 MUST 保持不变
- **AND** 完成后运行时 MUST 不再被同一批版本冲突阻断

### Requirement: 无法安全映射的现场不得随机迁移

阅读锚点只有在 exact、updated_block、fingerprint_remap 或用户明确接受 node_fallback 时才能更新到当前版本；course_fallback 和 unavailable MUST 要求显式目标节点。

#### Scenario: 原内容在新版本中已删除

- **WHEN** 旧锚点只能回退到课程任意位置或完全不可解析
- **THEN** 确认命令 MUST 返回需要目标节点的错误
- **AND** 旧快照 MUST 保持原版本和原位置

### Requirement: 旧正式证据不得证明新修订

课程版本变化后，当前掌握投影 MUST 只接受当前目标修订、题目修订和掌握标准修订对应的正式证据；旧版本对象 MUST 作为历史证据保留但不得自动换算。

#### Scenario: cv2 更新正式题目和掌握标准

- **WHEN** cv1 的 graded Attempt 对应题目或标准修订不属于 cv2
- **THEN** cv2 当前掌握状态 MUST NOT 使用该 Attempt
- **AND** 学习进度 MAY 显示存在历史证据但不得显示为新版本已掌握

### Requirement: 课程学习能力必须由统一只读契约表达

系统 MUST 以同一份只读投影表达标准、显式纯阅读和旧课兼容模式。纯阅读模式 MUST 由资产计划显式声明；兼容模式 MUST 由旧生成时代结构识别，MUST NOT 因现代标准课程缺少题目而自动启用。

#### Scenario: 现代标准课程缺少正式练习

- **WHEN** 一门具备现代生成契约的标准课程缺少必需正式题目
- **THEN** 课程模式 MUST 仍为 `standard`
- **AND** 正式练习能力 MUST 标记为阻断
- **AND** 系统 MUST NOT 将其解释成纯阅读或旧课兼容

### Requirement: 无题状态必须可解释

正式练习接口和前端 MUST 区分显式纯阅读、旧课兼容、标准课程资产缺失与当前范围无题。用户 MUST 能判断当前状态是产品设计、兼容边界还是需要修复的生成故障。

#### Scenario: 用户打开没有题目的练习页

- **WHEN** 当前范围没有可用正式题目
- **THEN** 接口 MUST 返回稳定原因码
- **AND** 前端 MUST 展示与原因码匹配的标题和说明

### Requirement: 降级不得伪造掌握或破坏确定性学习

纯阅读和旧课兼容课程完成阅读后 MAY 继续下一章节，但 MUST 保持未验证掌握状态。标准课程缺少必需练习时，系统 MUST 阻断空的掌握检查并指向课程资产修复。AI 模型不可用 MUST NOT 改写确定性的学习状态或下一步。

#### Scenario: AI 模型不可用时继续阅读

- **WHEN** AI 老师 provider 返回错误
- **THEN** AI 老师 MUST 返回安全不可用状态
- **AND** LearningRuntime 的阅读、记录和连续性投影 MUST 继续可用

### Requirement: 前端学习工作区必须共享当前目标范围

前端练习、掌握和学习连续性 MUST 使用同一当前目标身份。用户尚未显式选择有效节点时，工作区 MUST 回退到 `LearningRuntime.current_objective`；MUST NOT 因旧 `currentNode` 为空而静默扩大为全课程。

#### Scenario: 刷新课程后打开掌握工作区

- **WHEN** LearningRuntime 已返回当前目标且旧节点 Store 尚未选择节点
- **THEN** 掌握工作区 MUST 展示该目标名称并只过滤该目标资产
- **AND** 练习工作区的 node scope MUST 携带该目标节点 ID

### Requirement: 正式练习必须显式展示作用域

前端 MUST 区分当前目标、全课程和综合检测三种练习作用域，页面标签与接口参数 MUST 一致。

#### Scenario: 用户打开综合检测

- **WHEN** 练习 scope 为 final
- **THEN** 页面 MUST 显示综合检测作用域
- **AND** MUST NOT 把当前阅读节点名称显示成综合检测范围

### Requirement: 窄桌面必须保持课程正文可读

前端在 768 至 1024px MUST 避免课程目录、正文和固定笔记栏同时占位。课程目录 SHOULD 使用覆盖式抽屉，固定笔记栏 SHOULD 默认收起。

#### Scenario: 789px 视口打开课程阅读

- **WHEN** 用户在 789px 宽视口进入课程
- **THEN** 中央正文 MUST 保持正常横排与可读宽度
- **AND** 课程目录或笔记 MUST NOT 把正文压缩成逐字换行

### Requirement: 移动端课程模式必须可理解

前端在移动端 MUST 为目录、正文、学习记录和 AI 老师保留可见文字或等效的持续可见名称；练习、掌握、蓝图和版本 MUST NOT 作为顶层移动导航。

#### Scenario: 390px 视口切换学习空间

- **WHEN** 用户查看移动端学习导航
- **THEN** 目录、正文、记录和 AI MUST 有可见名称
- **AND** 导航 MUST NOT 遮挡正文、输入区或安全区

### Requirement: 运行时必须提供可追溯的临时适配块

`LearningRuntime` MAY 根据强学习证据返回低风险 `adaptive_blocks`，每个块 MUST 绑定语义锚点、原因码、证据引用、状态和有效期。适配块 MUST NOT 写入正式课程、正式题目或掌握事实。

#### Scenario: 当前概念出现已确认理解缺口

- **WHEN** 运行时存在足以支持最小解释或反例的强证据
- **THEN** 系统 MAY 在相关课程块后返回一个活动适配块
- **AND** 同一锚点 MUST NOT 同时返回多个竞争块

### Requirement: 临时适配块必须可跳过且不阻断确定性学习

用户 MUST 能跳过、收起或反馈适配块；模型失败或块过期 MUST 不改变基础课程顺序、正式 Attempt、学习记录或确定性下一步。

#### Scenario: 适配内容生成失败

- **WHEN** AI provider 无法生成临时解释
- **THEN** 正文、正式任务和连续性动作 MUST 继续可用
- **AND** 系统 MUST NOT 保存半段输出或伪造完成状态

### Requirement: 正式学习写入必须具有稳定身份和幂等关联

所有新学习领域写操作 MUST 使用非共享的稳定学习者身份，并以幂等请求关联领域对象修订与 LearningEvent。缺失身份或 `default_user` MUST NOT 接受生产写入；重复语义请求 MUST NOT 创建第二个对象、第二次状态变化或重复事件。

#### Scenario: 匿名浏览器首次保存学习记录

- **WHEN** 浏览器已经生成安装级匿名学习者 ID 并提交记录
- **THEN** 领域对象与事件 MUST 归属于同一身份、课程和操作 ID
- **AND** 使用相同幂等键重试 MUST 返回原结果

#### Scenario: 客户端未发送学习者身份

- **WHEN** 客户端调用正式学习写接口但没有有效 `X-User-Id`
- **THEN** 服务端 MUST 拒绝写入并返回稳定错误
- **AND** MUST NOT 把事实写入 `default_user`

### Requirement: 运行时必须包含同批学习者模型修订

LearningRuntime MUST 使用构建进度、记录、Attempt、诊断和连续性的同一批来源构建 LearnerModel 摘要，并返回 `model_revision_id`。运行时不得读取旧 AI profile 或独立 Learning OS 聚合结果。

#### Scenario: 正式作答改变当前掌握

- **WHEN** 新 Attempt 使目标的正式掌握投影变化
- **THEN** 同一运行时响应的 progress、continuation 与 learner_model_summary MUST 基于同一证据批次
- **AND** revision_vector MUST 反映新的模型来源修订

### Requirement: 旧学习入口只能迁移或投影正式真源

旧 annotation、Learning OS 和 localStorage 学习统计 MAY 提供一次性幂等迁移或只读兼容展示，但 MUST NOT 继续创建平行正式事实、学习者判断或下一步。迁移完成后新界面 MUST 只读取正式领域接口。

#### Scenario: 历史 annotation 已经迁移

- **WHEN** 同一旧 annotation 再次进入迁移流程
- **THEN** 系统 MUST 返回已有 LearningRecord 关联
- **AND** MUST NOT 重复创建记录或事件
