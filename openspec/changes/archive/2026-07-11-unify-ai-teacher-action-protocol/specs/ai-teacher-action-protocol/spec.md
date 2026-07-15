# ai-teacher-action-protocol Specification

## ADDED Requirements

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

普通提问和 AI 回答 MUST 保持在会话领域；MUST NOT 自动创建笔记、问题、复习任务、薄弱点或掌握结论。只有用户明确命令、确认提案或正式领域事实才能进入长期系统。

#### Scenario: 用户普通提问

- **WHEN** 用户询问某个概念并收到回答
- **THEN** 系统 MAY 记录最小帮助请求事实
- **AND** MUST NOT 自动保存 AI 回答或创建薄弱点

#### Scenario: 用户删除会话

- **WHEN** 用户删除一段 AI 会话
- **THEN** 原始消息和仅由该会话派生的摘要 MUST 删除
- **AND** 已确认创建的学习记录、正式 Attempt、LearningEvent 和动作回执 MUST 保留

### Requirement: 前端必须提供唯一 AI 老师工作区

正文提问、练习求助、连续性解释、学习记录引用和全局 AI 入口 MUST 打开同一个 AI 老师工作区。页面 MUST NOT 同时存在重复导师卡片、独立建议横幅或竞争主动作。

#### Scenario: 用户进入普通课程页面

- **WHEN** 当前没有强证据触发主动帮助
- **THEN** 页面 MUST NOT 展示 TutorActionCard 或页面级 AI 导师建议
- **AND** SmartBar MAY 保留一个统一 AI 入口

#### Scenario: AI 响应包含动作提案

- **WHEN** 流式回答完成且提案通过结构校验
- **THEN** 对应消息 MUST 最多展示一个主要提案
- **AND** 执行后 MUST 用持久回执替换确认按钮

### Requirement: 学生答疑与课程资产编辑必须分离

学生侧 AI 老师 MAY 解释正式课程，但 MUST NOT 在聊天工作区直接保存课程正文。改写、简化、扩展、出题和替换正式内容 MUST 进入课程版本、影响分析和确认流程。

#### Scenario: 用户从正文选择改写

- **WHEN** 用户请求改写或扩展当前正式课程内容
- **THEN** 系统 MUST 打开课程编辑或版本工作流并生成候选修改
- **AND** AI 老师工作区 MUST NOT 直接调用 saveNodeContent 覆盖当前正文

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
