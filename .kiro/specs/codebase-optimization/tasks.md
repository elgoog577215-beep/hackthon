# 实现计划：代码库优化与重构

## 概述

按依赖关系分阶段实施：先建立测试基础设施和共享模块，再进行后端拆分（模型集中化 → AI 服务拆分 → 路由模块化 → API 前缀统一），然后前端重构（HTTP 统一 → Annotations 清理 → Store 拆分 → 死代码清理），最后补充测试覆盖。每个阶段结束后设置检查点验证。

## 任务

- [x] 1. 后端模型集中化与共享依赖模块
  - [x] 1.1 将 main.py 中的 9 个内联 Pydantic 模型迁移到 backend/models.py
  - [x] 1.2 创建 backend/dependencies.py 共享依赖模块
- [x] 2. 检查点 - 验证模型迁移
- [x] 3. 后端 AI 服务拆分
  - [x] 3.1 创建 backend/ai_base.py 基础 LLM 调用层
  - [x] 3.2 创建 backend/ai_course_service.py 课程生成服务
  - [x] 3.3 创建 backend/ai_quiz_service.py 测验服务
  - [x] 3.4 创建 backend/ai_qa_service.py 问答服务
  - [x] 3.5 创建 backend/ai_graph_service.py 知识图谱服务
  - [x] 3.6 创建 backend/ai_learning_service.py 学习路径服务
  - [x] 3.7 创建 backend/ai_diagram_service.py 图表生成服务
  - [x] 3.8 重构 backend/ai_service.py 为 Facade 门面模块
  - [ ]* 3.9 编写属性测试验证 Facade 向后兼容性
- [x] 4. 检查点 - 验证 AI 服务拆分
- [x] 5. 后端路由模块化拆分与 API 前缀统一
  - [x] 5.1 创建 backend/routers/courses.py 课程管理路由
  - [x] 5.2 创建 backend/routers/nodes.py 节点操作路由
  - [x] 5.3 创建 backend/routers/annotations.py 标注与笔记路由
  - [x] 5.4 创建 backend/routers/quiz.py 测验路由
  - [x] 5.5 创建 backend/routers/knowledge_graph.py 知识图谱路由
  - [x] 5.6 创建 backend/routers/learning.py 学习路径路由
  - [x] 5.7 创建 backend/routers/review.py 复习调度路由
  - [x] 5.8 创建 backend/routers/tutor.py AI 辅导路由
  - [x] 5.9 创建 backend/routers/code_execution.py 代码执行路由
  - [x] 5.10 创建 backend/routers/diagrams.py 图表生成路由
  - [x] 5.11 创建 backend/routers/tasks.py 任务管理路由
  - [x] 5.12 重构 backend/main.py 为应用入口
  - [ ]* 5.13 编写属性测试验证 API 路由前缀一致性
- [x] 6. 检查点 - 验证后端路由拆分与 API 前缀
- [x] 7. 前端 HTTP 客户端统一与 API 路径更新
  - [x] 7.1 删除 frontend/src/utils/apiClient.ts 遗留模块
  - [x] 7.2 统一 course.ts 中 locateNode 方法的 HTTP 调用
  - [x] 7.3 将 KnowledgeGraph.vue 的直接 HTTP 调用改为通过 Store action
  - [x] 7.4 更新前端所有 HTTP 请求路径为 /api 前缀
  - [x] 7.5 简化 Vite 代理配置
- [x] 8. 检查点 - 验证前端 HTTP 统一与 API 路径
- [x] 9. 前端 Annotations 遗留系统清理
  - [x] 9.1 移除 course.ts 中的 Annotations 遗留代码
  - [x] 9.2 验证 Notes 系统功能完整性
- [x] 10. 前端 Course Store 拆分
  - [x] 10.1 创建前端类型定义文件
  - [x] 10.2 创建 frontend/src/stores/generation.ts 生成队列 Store
  - [x] 10.3 创建 frontend/src/stores/notes.ts 笔记 Store
  - [x] 10.4 创建 frontend/src/stores/learning.ts 学习路径 Store
  - [x] 10.5 创建 frontend/src/stores/review.ts 复习 Store
  - [x] 10.6 创建 frontend/src/stores/chat.ts 聊天 Store
  - [x] 10.7 精简 frontend/src/stores/course.ts 为核心课程 Store
  - [x] 10.8 更新所有组件和 composable 的 Store 导入
- [x] 11. 检查点 - 验证前端 Store 拆分
- [x] 12. 前端死代码清理
  - [x] 12.1 清理未使用的 TypeScript 模块、接口和类型
  - [x] 12.2 验证前端编译通过
- [x] 13. 后端测试覆盖增强
  - [x] 13.1 创建 tests/conftest.py 共享测试 fixtures
  - [x] 13.2 编写 tests/test_storage.py 存储层测试
  - [x] 13.3 编写 tests/test_courses_api.py 课程 API 测试
  - [x] 13.4 编写 tests/test_nodes_api.py 节点操作 API 测试
  - [x] 13.5 编写 tests/test_review.py SM-2 复习调度测试
  - [ ]* 13.6 编写 SM-2 ease_factor 属性测试
- [x] 14. 前端测试基础建设
  - [x] 14.1 编写 frontend/src/__tests__/shared/prompt-config.test.ts 验证规则测试
  - [ ]* 14.2 编写 prompt-config 验证函数幂等性属性测试
  - [x] 14.3 编写 frontend/src/__tests__/utils/http.test.ts HTTP 错误处理测试
  - [x] 14.4 编写 frontend/src/__tests__/utils/markdown.test.ts Markdown 渲染测试
  - [ ]* 14.5 编写拆分后 Store 的核心 action 单元测试
- [x] 15. 最终检查点 - 全面验证
