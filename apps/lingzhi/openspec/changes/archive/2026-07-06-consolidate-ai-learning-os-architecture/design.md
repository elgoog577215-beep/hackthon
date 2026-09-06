## 目标架构

本轮采用“目标架构牵引式合并”，把现有功能当作素材归并到一条主链路：

```text
用户行为
  -> LearningEvent 事件账本
  -> LearnerState 学习者状态
  -> TeachingDecision 教学决策
  -> LearningOSSnapshot 统一快照
  -> 前端导师卡 / 画像依据 / 统计轨迹 / AI 助手
  -> AI 回答、课件局部生成、复习练习
  -> 新结果继续回写事件账本
```

这条链路的原则是：

- `LearningEvent` 只记录发生过什么，不做画像判断。
- `LearnerState` 只从事件聚合状态，区分事实和推断。
- `TeachingDecision` 只表达下一步怎样教，不直接调用大模型。
- `LearnerContext` 和旧 `tutor_memory` 作为长期背景、旧画像、错题本、目标和遗忘曲线资产保留，但不再成为主建议来源。
- `LearningOSSnapshot` 是前端和旧接口的统一读模型，负责把新链路与旧资产整理成一个可消费结构。

## 旧功能归并矩阵

| 旧功能/模块 | 保留价值 | 归并方式 |
| --- | --- | --- |
| `learning_events.py` | 统一证据账本 | 保持主链路底座，继续扩展事件类型 |
| `learner_state.py` | 结构化状态 | 保持事实/推断边界，作为快照核心 |
| `teaching_decisions.py` | 下一步教学动作 | 作为主建议源，前端导师卡优先消费 |
| `ai_learning_context.py` | AI prompt 编排 | 继续服务 AI 助手和课程局部生成 |
| `tutor_service.py` | 目标、错题本、遗忘曲线、旧记忆 | 作为 legacy signals 进入快照；旧建议接口保持兼容 |
| `ai_learning_service.py` | 学习路径、掌握度、SM-2 复习 | 暂保留为复习/路径资产，后续逐步改成消费快照 |
| `learning_record.py` | 旧答题记录 | 暂保留兼容；新答题证据优先写入事件账本 |
| `LearningStats.vue` | 学习时长、轨迹、报告 | 收束为轨迹层，不再生成主建议 |
| `LearnerProfile.vue` | 画像、自评、依据解释 | 收束为解释层，展示事实与推断边界 |
| `TutorActionCard.vue` | 下一步行动 | 保持唯一主行动入口 |
| `SideAIPanel.vue` | 对话与轻量状态 | 保持轻摘要，不替代画像或统计 |
| `CourseNode.vue` block 操作 | 结构化课件编辑体验 | 继续复用，不另造课件编辑器 |

## LearningOSSnapshot 结构

快照应提供：

- `state`：`LearnerState` 原始结构。
- `decision`：`TeachingDecision` 原始结构。
- `state_summary` / `decision_summary`：供 UI 和 prompt 快速展示。
- `insights`：前端友好的统一洞察，包括主行动、候选行动、证据亮点、薄弱点、风险、最近活动。
- `trajectory`：课程级轨迹数据，如节点数、已读数、测验均分、弱节点、强节点。
- `legacy_signals`：旧导师记忆中的目标、错题本、复习项、连续学习等兼容信号。
- `compatibility`：声明哪些旧数据参与了快照，哪些仍是本地或旧链路。

## 前端分层

前端不新增“第五套智能中心”，而是把现有入口稳定分工：

- 导师行动卡：只展示当前最重要下一步动作。
- 学习画像：解释为什么系统这样判断，区分事实和推断。
- 学习统计：展示时间、完成率、测验、图谱、报告等轨迹。
- AI 助手：对话入口，只展示轻量状态摘要，回答时由后端 prompt 使用完整上下文。
- 课程内容 block：作为课件局部编辑和局部练习入口。

## 本轮第一批落地

本轮先做主链路的“统一读 + 关键写”：

1. 后端新增 `learning_os.py`。
2. 新增 `/api/learning-os/snapshot`。
3. `/api/tutor/learning-state` 内部改用快照并保持旧字段。
4. 前端 `buildLearningInsights` 优先消费 `snapshot.insights`，旧结构兼容。
5. 测验提交调用 `/api/tutor/record-learning`，让答题结果进入事件账本。
6. 修复节点扩展返回字段兼容。

## 后续迁移

- 复习提交 `/review/submit` 也应写入事件账本。
- `learning_path` 和 `knowledge_mastery` 应逐步消费 `LearningOSSnapshot`，不再只看课程节点字段。
- `tutor_service.generate_greeting` 可用快照补充问候和复习提醒。
- 前端本地 `reviewStore` 的错题可逐步同步后端，避免跨设备丢失。
