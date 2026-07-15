# ai-teacher-action-protocol Specification

## Purpose
TBD - created by archiving change unify-ai-teacher-action-protocol. Update Purpose after archive.
## Requirements
### Requirement: AI 老师必须读取统一运行时且不得拥有平行状态

AI 老师 MUST 以 `LearningRuntime` 作为当前学习现场、活动任务和唯一下一步的统一来源；MUST NOT 维护课程、学习记录、Attempt、诊断、掌握、画像或任务优先级的隐藏副本。

#### Scenario: 用户询问下一步

- **WHEN** 用户在课程中询问接下来应该做什么
- **THEN** AI MUST 解释 LearningRuntime 的 primary action
- **AND** MUST NOT 根据旧导师记忆或聊天历史生成竞争动作

### Requirement: AI 上下文必须按意图最小装配

后端 MUST 为每次请求构建不可变 `AIContextPackage`，包含当前请求、版本化现场、LearningRuntime、必要任务信息、相关课程片段、必要学习证据、会话摘要和权限；MUST NOT 默认注入课程全文、全部笔记、全部历史或无关画像。

#### Scenario: 用户选中正文请求解释

- **WHEN** 用户从当前内容块选中一段文字并提问
- **THEN** 上下文 MUST 包含选区、内容锚点、当前目标和少量相关课程片段
- **AND** MUST NOT 因该请求加载整门课程和全部学习记录

#### Scenario: 运行时在生成过程中变化

- **WHEN** 回答绑定的 runtime_revision_id 已不再是当前修订
- **THEN** 回答 MAY 继续显示并标记原始上下文
- **AND** 任何动作提案 MUST 在确认前重新校验

### Requirement: 正式任务必须执行答案披露隔离

AI 老师 MUST 根据正式任务状态和支持等级决定可见信息。提交前 MUST NOT 向模型提供被禁止的完整标准答案；完整解析披露 MUST 形成正式支持事实并使该 Attempt 不能证明独立掌握。

#### Scenario: 掌握检查提交前请求帮助

- **WHEN** 用户在未提交掌握检查中向 AI 求助
- **THEN** AI 上下文 MUST 只包含允许的题目、量规和分级提示
- **AND** MUST NOT 包含完整标准答案

#### Scenario: 用户明确查看完整解析

- **WHEN** 正式领域服务允许并记录完整解析披露
- **THEN** Attempt 支持等级 MUST 更新为 full_scaffold 或等价状态
- **AND** 后续掌握投影 MUST NOT 将该次结果视为独立证据

### Requirement: 所有写动作必须使用结构化提案

AI 主动提出的状态变更 MUST 形成白名单 `ActionProposal`，包含目标、影响预览、证据、确认方式、修订前置条件和失效时间；模型文本 MUST NOT 直接调用领域写接口。用户当前轮次的明确命令 MAY 视为确认，但仍 MUST 经过相同命令校验。

#### Scenario: AI 主动建议保存笔记

- **WHEN** AI 判断某段回答可能值得保存
- **THEN** 系统 MUST 展示待确认的保存笔记提案
- **AND** 用户确认前 MUST NOT 创建 LearningRecord

#### Scenario: 用户明确要求保存

- **WHEN** 用户说“帮我记成笔记”且目标上下文唯一
- **THEN** 系统 MUST 将该指令作为确认并执行白名单命令
- **AND** MUST NOT 再要求一次重复确认

### Requirement: 动作执行必须幂等并返回持久回执

确认后的动作 MUST 经过真实身份、目标归属、动作白名单、运行时修订、对象修订和幂等校验，由正式领域服务执行。成功或失败 MUST 返回持久 `ActionReceipt`，成功后 MUST 重新读取 LearningRuntime。

#### Scenario: 用户重复点击确认

- **WHEN** 客户端使用同一 idempotency_key 重复提交保存笔记命令
- **THEN** 服务端 MUST 只创建一个 LearningRecord 和一次逻辑执行
- **AND** 后续请求 MUST 返回同一执行回执

#### Scenario: 提案确认时已经过期

- **WHEN** 目标任务、课程版本或 runtime_revision_id 已发生关键变化
- **THEN** 服务端 MUST 返回 stale 或 conflict 回执
- **AND** MUST NOT 执行旧动作

### Requirement: 撤销必须使用补偿动作且不得抹除学习事实

可撤销动作 MUST 通过带修订校验的补偿命令执行。学习记录 SHOULD 通过归档或反向状态撤销；已提交答案、评分证据、完整解析披露和已发布课程版本 MUST NOT 被删除或改写。

#### Scenario: 撤销刚创建的笔记

- **WHEN** 笔记尚未被后续编辑且用户确认撤销
- **THEN** 系统 MUST 归档该记录并写入撤销事实
- **AND** MUST 保留原创建事件

#### Scenario: 尝试撤销正式提交

- **WHEN** 用户请求撤销已经提交的正式答案
- **THEN** 系统 MUST 拒绝删除历史证据
- **AND** SHOULD 提供重试、异议或新 Attempt 入口

### Requirement: 主动帮助必须由强证据触发并支持冷却

系统 MUST 使用确定性规则从正式证据生成 `TriggerCandidate`。停留时间、滚动速度、页面打开、一次错误、参与度分数、旧错题数量和 AI 猜测 MUST NOT 单独触发主动建议。拒绝和抑制 MUST 在刷新与跨设备后保持有效。

#### Scenario: 没有强干预证据

- **GIVEN** 当前只有少量一般学习事件且没有正式阻塞、诊断、到期复习或明确求助
- **WHEN** 页面计算主动帮助候选
- **THEN** 系统 MUST 不展示 AI 导师建议

#### Scenario: 用户拒绝当前建议

- **WHEN** 用户选择暂时不要或与我无关
- **THEN** 同一动作、目标和证据修订 MUST 进入对应冷却
- **AND** AI MUST NOT 通过更换措辞再次展示

### Requirement: AI 对话不得自动成为学习记录或稳定画像

块级 AI 的解释、举例、简化和提问 MUST 默认保持临时状态；MUST NOT 自动创建笔记、问题、复习任务、薄弱点、掌握结论或正式课程改写。只有用户明确选择“保留为个人内容”，系统才 MAY 通过现有白名单提案和确认协议创建带稳定内容锚点的 `LearningRecord`。

#### Scenario: 行内回答完成

- **WHEN** AI 完成对课程块的解释、举例、简化或回答
- **THEN** 结果 MUST 继续作为可移除的临时个人内容显示
- **AND** MUST NOT 自动写入 `LearningRecord` 或 `CourseDocument`

#### Scenario: 用户保留回答

- **WHEN** 用户点击“保留为个人内容”
- **THEN** 系统 MUST 使用 `block_id` 与 `block_revision_id` 创建或确认个人学习记录
- **AND** 保存完成后 MUST 由正式学习记录投影回来源块附近

#### Scenario: 用户移除临时回答

- **WHEN** 用户点击“移除”
- **THEN** 系统 MUST 移除当前行内表达
- **AND** MUST NOT 修改正式课程或已经持久化的全局会话历史

### Requirement: 前端必须提供唯一 AI 老师工作区

结构化课程块的解释、举例、简化和提问 MUST 在来源块附近进入同一个行内 AI 结果块；继续追问 MUST 更新该块的当前表达，不得为同一轮连续问答重复生成多张卡片。全局 AI 工作区 MAY 保留为历史会话、跨块问题和低频兜底入口，但块级协作与全局入口 MUST 共用同一会话、上下文、提案和回执协议，不得建立平行 AI 状态。

#### Scenario: 用户请求解释当前课程块

- **WHEN** 用户在一个结构化课程块选择“解释”
- **THEN** 系统 MUST 在该块下方显示临时 AI 结果
- **AND** MUST NOT 要求用户先打开右栏或离开当前阅读位置

#### Scenario: 用户继续追问

- **WHEN** 当前块已经存在一次 AI 回答且用户选择“继续追问”
- **THEN** 系统 MUST 在同一个行内结果块接收并显示新回答
- **AND** 全局会话历史 MUST 保留完整消息顺序

#### Scenario: 用户查看全局 AI

- **WHEN** 用户从全局 AI 入口查看历史或提出跨块问题
- **THEN** 系统 MUST 读取与行内问答相同的会话状态
- **AND** MUST NOT 把行内回答复制成第二套会话记录

### Requirement: 学生答疑与课程资产编辑必须分离

学生侧 AI 老师 MAY 解释正式课程并产生个人临时适配，但 MUST NOT 在聊天工作区直接保存课程正文。改写、简化、扩展、出题和替换正式内容 MUST 进入内部课程领域服务、影响分析和确认流程；系统 MUST NOT 为学生打开蓝图、版本或块拖拽工作台。

#### Scenario: 用户从正文请求换一种讲法

- **WHEN** 用户请求改写或扩展当前正式课程内容
- **THEN** AI 老师 MUST 默认给出临时解释或适配块
- **AND** 只有用户明确要求修改正式课程并确认影响后，内部课程服务才 MAY 应用正式变更

### Requirement: 旧导师状态链必须退出生产决策

`tutor_memory.json`、`UnifiedTutorMemory`、`ProactiveTutorEngine`、Learning OS legacy tutor signals 和前端 tutor 平行建议 MUST NOT 参与 AI 回答、主动触发、下一步或稳定画像。历史数据 MAY 做幂等低置信迁移或归档。

#### Scenario: 系统构建 AI 上下文

- **WHEN** AI 老师为当前课程装配上下文
- **THEN** MUST NOT 读取 tutor_memory 的掌握、错题、目标或画像副本
- **AND** MUST 从正式领域真源和 LearningRuntime 读取必要证据

### Requirement: AI 老师界面必须覆盖响应式与国际化状态

AI 老师新增或修改的标题、按钮、空状态、错误、提案和回执 MUST 同时提供中文与英文文案。桌面与移动端 MUST 保持内容、输入区、连续性状态条和底部工具栏不相互遮挡。

#### Scenario: 390px 移动端打开 AI 老师

- **WHEN** 用户在 390px 宽度打开 AI 工作区并接收长回答或动作回执
- **THEN** 文本和操作 MUST 不发生横向溢出
- **AND** 输入区 MUST 避开底部工具栏与安全区

### Requirement: 块级 AI 回答必须支持显式效果反馈

完整的块级 AI 回答 MUST 提供“已解决”和“还不清楚”两项显式反馈，并将选择写入统一 `LearningEvent`。反馈 MUST 关联当前用户、课程、节点、会话、assistant 消息、块级动作和稳定内容锚点；同一消息的重复提交 MUST 幂等。一次反馈 MUST NOT 自动创建学习记录、正式题目、诊断、补救、掌握结论、课程改写或唯一下一步。

#### Scenario: 用户确认回答已解决问题

- **WHEN** 用户对一条已完成的块级 AI 回答选择“已解决”
- **THEN** 系统 MUST 记录一条 `assistant_answer_feedback_submitted` 学习事件
- **AND** 结果 MUST 标记为 `resolved` 并保留会话、消息与内容块引用
- **AND** 系统 MUST NOT 自动执行其他 AI 或领域动作

#### Scenario: 用户仍然不清楚

- **WHEN** 用户选择“还不清楚”
- **THEN** 系统 MUST 记录结果为 `unclear` 的回答反馈事件
- **AND** 当前回答 MUST 继续保留并允许用户自行选择继续追问
- **AND** 系统 MUST NOT 自动生成下一步、题目或补救任务

#### Scenario: 回答尚未完成或不属于当前用户

- **WHEN** 客户端对生成中、失败、不存在或不属于当前用户的 assistant 消息提交反馈
- **THEN** 后端 MUST 拒绝写入学习事件
- **AND** MUST NOT 仅凭客户端提供的消息 ID 创建事实

### Requirement: AI 老师必须按意图读取最小学习者模型证据

AIContextPackage MUST 只在请求需要学习状态判断时读取 LearnerModel，并只包含相关目标的模型结论、证据类型、置信度和模型修订。普通解释请求 MUST NOT 默认注入完整画像或全部学习历史。

#### Scenario: 用户询问自己的薄弱点

- **WHEN** 当前问题明确要求学习复盘
- **THEN** 上下文 MUST 包含相关目标的正式模型结论及其证据摘要
- **AND** AI MUST 区分已验证事实、系统推断与证据不足

#### Scenario: 用户只要求解释选中文本

- **WHEN** 当前意图是解释一个课程块
- **THEN** 上下文 MUST 以课程片段和当前目标为主
- **AND** MUST NOT 加载无关目标的学习者模型详情

### Requirement: AI 老师不得把模型解释成新的正式事实

AI 回答 MUST 使用模型修订固定当次依据，并用有边界的语言表达推断。聊天、总结、主动建议和用户接受某种说法 MUST NOT 自动改变 LearnerModel；只有正式领域动作产生的新事实才能在下一次重算中改变模型。

#### Scenario: AI 建议重点复习一个目标

- **WHEN** 建议依据低置信或近期正式失败证据
- **THEN** AI MUST 说明依据与不确定性
- **AND** MUST NOT 自动把目标标记为薄弱或需要复习

### Requirement: 旧画像与 Learning OS 不得进入 AI 生产上下文

AI 老师构建回答、主动触发或提案时 MUST NOT 读取旧 AI profile、Learning OS 推断、localStorage 学习统计或默认用户数据。历史显式自我报告只有迁移到正式分区后才 MAY 作为有来源的上下文。

#### Scenario: 旧 profile 保存了 AI 生成的学习风格

- **WHEN** 系统装配当前 AI 上下文
- **THEN** MUST 忽略该 AI 生成画像
- **AND** MUST NOT 根据其调整回答或下一步

