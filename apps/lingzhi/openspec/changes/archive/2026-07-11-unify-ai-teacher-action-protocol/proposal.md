# 变更：统一 AI 老师动作协议

## Why

课程使用前六步已经通过 `LearningRuntime` 完成横向整合，但 AI 老师仍运行在更早的平行链路上。当前 `tutor_memory.json` 继续维护画像、掌握、错题和目标副本，主动导师引擎仍使用参与度、停留时间和连续错误触发建议；`TeachingDecision` 同时决定讲法和下一步，正文顶部 `TutorActionCard` 又重复展示 `LearningRuntime` 已经给出的主要动作。AI 问答还由前端拼接完整大纲、整节点、全部笔记和本地会话，缺少正式任务答案隔离、结构化提案、幂等执行、回执与拒绝冷却。

这些旧路径使 AI 老师可能读取过量或过期上下文、把弱信号当成干预依据、与连续性状态条竞争下一步，并在聊天面板中直接修改正式课程资产。第 7 步必须替换旧导师链，而不是继续在旧卡片和旧建议接口上叠加功能。

## What Changes

- 建立一次性 `AIContextPackage`，按请求意图选择当前现场、`LearningRuntime`、正式任务、课程片段、必要学习证据、会话摘要和权限策略；不复制领域状态。
- 将 AI 输出明确分为回答、解释、动作提案和确认后执行；所有写动作使用白名单 `ActionProposal -> ActionCommand -> ActionReceipt` 协议。
- 为动作执行增加身份与归属校验、版本前置条件、幂等键、领域服务分发、事件一致性、运行时刷新和可补偿撤销。
- 建立正式证据驱动的 `TriggerCandidate`、建议去重、拒绝语义、冷却和主动帮助设置；没有强证据时不展示导师建议。
- 建立按用户与课程隔离的 AI 会话、提案、回执和抑制生命周期；对话、学习事实、学习记录和学习者模型继续保持边界。
- 将 `SideAIPanel` 升级为唯一 AI 老师工作区，统一正文提问、练习求助、连续性解释和底部入口；移除正文顶部 `TutorActionCard`。
- 将课程改写、简化、扩展、出题和正文替换从学生 AI 对话中移出，转入正式课程版本与影响确认流程。
- 清退 `tutor_memory.json`、`UnifiedTutorMemory`、`ProactiveTutorEngine`、旧 tutor suggestion/greeting/review/goal 生产路径、Learning OS 旧导师信号和前端 tutor 平行建议状态。
- 修改旧 AI 规格中“metadata 创建 AI 笔记”“导师行动卡承载主动作”“旧导师记忆兼容补充”等已过时要求。

## 影响范围

- 后端：AI 上下文、问答事件协议、会话与动作仓库、动作执行器、主动触发、LearningRuntime 消费、旧 tutor/learning-os/learner-context 兼容链。
- 前端：AI 会话 Store、`SideAIPanel`、课程正文选择入口、练习求助、SmartBar、TutorActionCard、课程 Store 聊天职责和中英文文案。
- 数据：新增 AI 交互协调对象，但不新增学习状态真源；旧导师记忆只做显式迁移或归档，不再参与实时决策。
- 安全与一致性：模型不能构造任意接口或身份字段；正式答案、课程版本和稳定学习状态受领域权限与修订门禁保护。
