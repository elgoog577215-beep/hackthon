## 1. 收拢助手记忆链路

- [x] 1.1 新增轻量助手上下文构建模块，复用 `LearnerContext` 和现有课程/请求上下文。
- [x] 1.2 改造 `AIQAService`，使 `/api/ask` 与 `/api/ask_events` 不再依赖旧 `memory.py` 控制器。
- [x] 1.3 处理无生产调用或已失配的旧 Socratic 入口，避免继续引用旧构造方式。

## 2. 验证旧链路不再活跃

- [x] 2.1 增加测试，确认问答 prompt 会读取统一学习者上下文。
- [x] 2.2 增加测试，确认旧 `memory.py` 控制器不会被问答链路导入调用。
- [x] 2.3 运行相关 pytest、Python 编译检查、OpenSpec 校验和 diff 检查。
