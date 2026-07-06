## 1. 收拢课程 AI 链路

- [x] 1.1 在 `CourseService` 中补齐节点重写、扩展、摘要和定位能力，让课程内容相关路由不再调用旧 `AICourseService`。
- [x] 1.2 迁移 `nodes` / `courses` 路由中的课程内容操作到 `CourseService`，保留响应格式兼容。
- [x] 1.3 确认 block 级重写仍只替换目标 block，整节重写仍刷新 `content_blocks`。

## 2. 建立学习者上下文账本

- [x] 2.1 新增轻量 `LearnerContext` 聚合模块，从标注、导师记忆和请求画像中构造稳定上下文。
- [x] 2.2 让 `memory.py` 的导师问答用户记忆读取聚合层，移除硬编码偏好占位。
- [x] 2.3 让 `profile/generate` 返回并持久化最小画像快照，供后续 AI prompt 复用。
- [x] 2.4 让 block 级重写注入学习者上下文，但不覆盖课程蓝图上下文。

## 3. 验证与收束

- [x] 3.1 为学习者上下文聚合与课程内容迁移补最小回归测试。
- [x] 3.2 运行后端相关测试、Python 编译检查和 OpenSpec 校验。
- [x] 3.3 检查工作区，避免提交无关前端 lockfile 或历史诊断文档。
