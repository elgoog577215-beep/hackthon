# 统一 AI 助手记忆链路

## 背景

课程生成、节点重写和画像已经收拢到 `CourseService` 与 `LearnerContext`，但 AI 助手问答仍会从 `ai_qa_service` 进入旧 `memory.py` 的 `DualMemoryController`。这让后端同时存在学习者上下文聚合层、导师记忆和旧双记忆控制器三条记忆链路，维护者很难判断真实生产入口。

## 目标

- 让 `/api/ask` 和 `/api/ask_events` 的 prompt 构造统一读取 `LearnerContext`。
- 保留现有问答接口、流式正文和 metadata 输出协议。
- 把旧双记忆控制器从生产问答链路中移除，避免旧电路继续影响 AI 助手。
- 保持轻量：不引入新依赖、不做数据库迁移、不改前端协议。

## 非目标

- 不重写前端聊天体验。
- 不删除 `/api/ask` 兼容入口。
- 不引入向量检索、重型 RAG 或多 Agent。
