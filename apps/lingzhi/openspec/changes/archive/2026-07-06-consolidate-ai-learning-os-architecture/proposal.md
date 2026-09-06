## 为什么

当前系统已经有 `LearningEvent -> LearnerState -> TeachingDecision -> AI Learning Context` 的后端骨架，也有前端课程 block 操作、学习画像、导师卡、学习统计和 AI 助手等体验入口。但这些能力仍然存在几类断裂：

- 后端旧 `ai_learning_service`、`learning_record`、`tutor_service` 和新状态/决策层都能产生“弱点、掌握度、建议”，但没有统一读模型。
- 前端 `TutorActionCard`、`LearnerProfile`、`LearningStats`、`SideAIPanel` 都在表达学习状态，虽然已经有所收敛，但仍缺一个稳定的统一后端契约。
- UI 测验结果主要留在前端本地状态，后端事件账本未必能感知真实答题反馈，导致后续状态和教学决策证据不足。
- 课程生成的局部重写、扩展、总结已接入 AI Learning Context，但通用学习统计、复习、路径等旧链路仍绕开主链路。

这次变更的目的不是把所有旧代码一次性删除，而是建立一个理想主链路，让旧功能按职责归并：能成为证据的进入事件账本，能表达状态的进入 `LearnerState`，能表达下一步教学动作的进入 `TeachingDecision`，能给前端消费的通过统一 Learning OS 快照输出。

## 改什么

- 新增轻量 `LearningOSSnapshot` 后端统一读模型，整合学习者状态、教学决策、课程轨迹和旧导师记忆兼容信号。
- 让旧 `/api/tutor/learning-state` 保持兼容，同时返回统一快照，作为前端智能入口的主契约。
- 新增独立 `/api/learning-os/snapshot` 接口，作为后续前端和服务层逐步迁移的统一入口。
- 让 UI 测验提交通过现有导师学习记录接口回写后端事件账本，补齐做题证据。
- 调整前端学习洞察解析逻辑，优先消费统一快照，旧 `state/decision/suggestions` 仍可兼容。
- 修复已发现的节点扩展响应字段兼容问题，避免前端扩展内容无法正确拼接。
- 更新架构文档，明确前端和后端的理想分层、旧功能归并策略和下一步迁移顺序。

## 不改什么

- 不重写前端 UI，不新建另一套学习看板或课程编辑器。
- 不引入重型数据库，继续使用当前文件存储。
- 不删除尚未确认无调用的旧服务。
- 不改变 AI 问答、课程生成、导师接口的旧响应协议。
- 不把通用课程生成强行改成单用户私有生成；个性化只在已有上下文和局部内容操作中轻量生效。

## 影响

- 后端：`learning_os.py`、导师路由、主路由注册、模型字段兼容、测试。
- 前端：`tutorStore`、`learning-insights`、测验提交行为、课程扩展兼容。
- 文档：AI Learning OS 架构说明增加统一快照和前后端归并策略。
