# 实现计划：课程生成系统全方位优化

## 概述

基于渐进式重构原则，按照"基础设施 → 核心模块拆分 → 后端功能 → 前端功能 → 集成联调"的顺序实现。每个任务构建在前一个任务之上，确保系统在重构过程中始终可用。技术栈：后端 Python + FastAPI，前端 Vue 3 + Pinia + TypeScript，测试 pytest + hypothesis / vitest + fast-check。

## Tasks

- [x] 1. 数据模型扩展与基础类型定义
  - [x] 1.1 扩展后端数据模型 `backend/models.py`
    - 新增 `NodeStatus` 枚举（PENDING/GENERATING/COMPLETED/ERROR/SKIPPED）
    - 新增 `NodeGenerationConfig`、`TaskLogEntry`、`TaskState`、`QualityScore`、`ConsistencyIssue`、`SimilarExample`、`CourseSnapshot`、`ErrorSeverity` 模型
    - 扩展现有 `Node` 模型，添加 `generation_status`、`generation_config`、`generated_chars`、`error_summary` 字段
    - 所有公共接口提供完整 Python type hints
    - _Requirements: 8.1, 13.5, 14.3, 9.5_

  - [x] 1.2 新增前端类型定义 `frontend/src/stores/types.ts`
    - 定义 `NodeGenerationConfig`、`TaskProgress`、`FailureReport`、`WSMessage`、`WSCommand` 接口
    - 扩展现有 `Node` 接口，添加 `generation_status`、`generation_config`、`generated_chars`、`error_summary` 字段
    - _Requirements: 8.1, 1.6_

- [x] 2. 存储层健壮性增强
  - [x] 2.1 重构 `backend/storage.py` 实现原子写入和并发锁
    - 实现 `_atomic_write` 方法：先写 `.tmp` 文件再 `os.rename`
    - 实现按 `course_id` 的 `asyncio.Lock` 文件级锁
    - 实现 `_create_snapshot` 版本快照方法
    - 实现 `rollback_course` 回滚方法
    - 实现 `validate_all_courses` 启动时 JSON 完整性验证
    - 版本快照上限为 3，超出时删除最旧快照
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 10.5_

  - [ ]* 2.2 编写 Storage 属性测试 `backend/tests/test_storage.py`
    - **Property 21: 并发写入安全** — 对同一 course_id 的并发写入通过文件级锁串行执行，最终文件为有效 JSON
    - **Validates: Requirements 10.5, 11.2**

  - [ ]* 2.3 编写 Storage 属性测试：原子写入故障恢复
    - **Property 22: 原子写入与故障恢复** — 写入失败时上一有效版本数据文件保持完整可读
    - **Validates: Requirements 11.1, 11.3**

  - [ ]* 2.4 编写 Storage 属性测试：版本快照上限
    - **Property 24: 版本快照上限** — 仅保留最近 3 个版本快照，超出时删除最旧快照
    - **Validates: Requirements 11.5**

  - [ ]* 2.5 编写 Storage 属性测试：启动时数据完整性验证
    - **Property 23: 启动时数据完整性验证** — 正确识别所有损坏文件并记录警告
    - **Validates: Requirements 11.4**

  - [ ]* 2.6 编写 Storage 属性测试：序列化往返
    - **Property 33: 课程数据序列化往返** — 序列化为 JSON 后反序列化产生等价对象
    - **Validates: Requirements 16.5**

- [x] 3. 检查点 - 存储层验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 代码架构清理与模块拆分
  - [x] 4.1 从 `ai_course_service_v5.py` 拆分 `backend/knowledge_graph.py`
    - 提取 `GlobalKnowledgeGraph` 类为独立模块
    - 实现 `register_concept`、`register_example`、`register_formula`、`get_context_for_node`、`get_used_example_titles`、`check_example_similarity`、`get_term_definition_source` 方法
    - 所有公共接口提供完整 type hints
    - _Requirements: 4.2, 4.3, 9.4, 15.1_

  - [ ]* 4.2 编写 GlobalKnowledgeGraph 属性测试 `backend/tests/test_knowledge_graph.py`
    - **Property 8: 知识图谱注册完整性** — 已注册节点包含核心概念列表、关键术语定义和已使用案例标题，案例摘要 ≥ 50 字且关联有效 node_id
    - **Validates: Requirements 4.2, 15.1**

  - [ ]* 4.3 编写案例重复检测属性测试
    - **Property 32: 案例重复检测** — 余弦相似度 ≥ 0.8 的案例被标记为重复
    - **Validates: Requirements 15.3**

  - [x] 4.4 从 `ai_course_service_v5.py` 拆分 `backend/quality_predictor.py`
    - 提取 `QualityPredictor` 类为独立模块
    - 实现 `predict_quality`、`evaluate_content`、`validate_mermaid` 方法
    - _Requirements: 5.1, 5.4, 9.4_

  - [x] 4.5 重构 `backend/content_validator.py` 升级质量评估
    - 使用结构化评分规则替代简单字符数阈值
    - 评估维度：最小段落数、代码示例数量、概念定义数量
    - 返回包含 structure_completeness、content_depth、readability、format_correctness 的 `QualityScore`
    - _Requirements: 5.1, 5.2_

  - [ ]* 4.6 编写 ContentValidator 属性测试 `backend/tests/test_content_validator.py`
    - **Property 10: 多维度质量评估** — 评分包含四个维度独立分数，基于结构化规则验证
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 4.7 编写 Mermaid 语法验证属性测试
    - **Property 12: Mermaid 图表语法保证** — 验证和修复后不存在语法错误的 Mermaid 图表
    - **Validates: Requirements 5.4, 5.5**

  - [x] 4.8 重构 `backend/content_consistency_validator.py`
    - 集成 `GlobalKnowledgeGraph` 进行跨节点一致性检查
    - 实现余弦相似度案例重复检测（阈值 0.8）
    - 检测重复案例、矛盾定义、断裂引用
    - 返回 `ConsistencyIssue` 列表，标注 severity 和 auto_fixable
    - _Requirements: 4.4, 4.5, 15.3_

  - [ ]* 4.9 编写 ConsistencyValidator 属性测试 `backend/tests/test_consistency_validator.py`
    - **Property 9: 一致性问题自动修复** — 修复后重新检测不再出现相同严重问题
    - **Validates: Requirements 4.5, 15.4**

  - [x] 4.10 重构 `ai_course_service_v5.py` 为 `backend/course_service.py`
    - 移除已拆分的 `GlobalKnowledgeGraph`、`ContentCache`、`QualityPredictor`，改为依赖注入
    - 实现 `generate_node_content_stream` 流式生成方法（on_chunk 回调）
    - 实现 `repair_content` 低质量内容修复方法
    - 实现 `run_consistency_check` 和 `auto_fix_consistency` 方法
    - _Requirements: 2.1, 5.3, 5.5, 9.4_

  - [ ]* 4.11 编写 CourseService 属性测试 `backend/tests/test_course_service.py`
    - **Property 7: 提示词上下文完整性** — 提示词包含前序节点摘要、术语定义引用、已使用案例列表、自定义指令
    - **Validates: Requirements 4.1, 4.3, 7.3, 15.2**

  - [ ]* 4.12 编写低质量自动修复属性测试
    - **Property 11: 低质量内容自动修复触发** — 评分 < 0.6 时自动触发修复流程
    - **Validates: Requirements 5.3**

  - [ ]* 4.13 编写生成配置解析属性测试
    - **Property 31: 生成配置解析** — 自定义配置优先于默认配置，所有参数反映在提示词中
    - **Validates: Requirements 14.2, 14.3, 14.4**

  - [x] 4.14 清理旧版本文件
    - 移除 `ai_course_service.py`、`ai_course_service_v2.py`、`ai_course_service_v3.py`、`ai_course_service_v4.py`
    - 移除 `prompts.py`、`prompts_v2.py`
    - 更新所有 import 语句和路由注册引用到新模块
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 5. 检查点 - 模块拆分验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 后端 WebSocket 服务与异步任务管理器
  - [x] 6.1 新建 `backend/websocket_service.py`
    - 实现 `WebSocketService` 类：连接管理、按 courseId 订阅/取消订阅
    - 实现 `push_node_completed`、`push_progress_update`、`push_stream_chunk`、`push_error` 推送方法
    - 实现 `handle_client_command` 处理 skip_node、retry_node、custom_instruction、stop_node、retry_all_failed 命令
    - 定义 `WSMessage`、`WSCommand` 消息协议
    - _Requirements: 1.1, 1.5, 1.6, 7.4_

  - [x] 6.2 重构 `backend/task_manager.py` 为纯 asyncio 架构
    - 移除 `threading.Thread` 和 `asyncio.new_event_loop` 的使用
    - 使用 `asyncio.Queue` 实现生产者-消费者模式
    - 使用 `asyncio.Semaphore` 控制并发上限（默认 5）
    - 实现层级优先调度策略（level 1 > level 2 > level 3，同层级按顺序）
    - 实现 `_consumer_loop`、`_schedule_nodes`、`_process_node` 方法
    - 实现 `skip_node`、`retry_node`、`stop_node`、`retry_all_failed` 单节点控制
    - 实现 `update_outline` 大纲变更后任务取消和重新调度
    - 实现优雅关闭（最长等待 30 秒）
    - 实现指数退避重试策略（初始 2s，最大 60s）
    - 实现任务执行日志记录
    - 集成 `WebSocketService` 进行实时推送
    - 集成 `CourseService` 的流式生成方法
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.1, 10.2, 10.3, 10.4, 6.5, 7.1, 7.2, 7.5, 13.1, 13.2, 13.4, 13.5_

  - [ ]* 6.3 编写 TaskManager 属性测试 `backend/tests/test_task_manager.py`
    - **Property 4: 并发上限不变量** — 任意时刻同时执行的节点生成任务数不超过 M
    - **Validates: Requirements 3.2**

  - [ ]* 6.4 编写层级优先调度属性测试
    - **Property 5: 层级优先调度顺序** — level 1 优先于 level 2，level 2 优先于 level 3，同层级按原始顺序
    - **Validates: Requirements 3.3**

  - [ ]* 6.5 编写失败隔离与重试属性测试
    - **Property 6: 失败隔离与重试上限** — 重试不超过 2 次，耗尽后标记 error，其他节点不受影响
    - **Validates: Requirements 3.5, 13.1**

  - [ ]* 6.6 编写进度计算属性测试
    - **Property 19: 进度计算正确性** — progress = completed_nodes / total_nodes * 100，各状态节点数之和 = 总节点数
    - **Validates: Requirements 8.4**

  - [ ]* 6.7 编写指数退避属性测试
    - **Property 29: 指数退避策略** — 第 k 次等待时间为 min(2^k * 2, 60) 秒
    - **Validates: Requirements 13.4**

  - [ ]* 6.8 编写任务日志完整性属性测试
    - **Property 30: 任务执行日志完整性** — 日志包含每个节点的开始时间、结束时间、重试次数、错误信息和生成字数
    - **Validates: Requirements 13.5**

  - [ ]* 6.9 编写优雅关闭属性测试
    - **Property 20: 优雅关闭** — 等待正在执行的任务完成（最长 30 秒），超时后强制终止
    - **Validates: Requirements 10.4**

  - [ ]* 6.10 编写大纲变更任务取消属性测试
    - **Property 15: 大纲变更任务取消** — 取消受影响节点的待执行任务，为新增节点创建新任务
    - **Validates: Requirements 6.5**

  - [ ]* 6.11 编写节点跳过属性测试
    - **Property 16: 节点跳过状态转换** — pending 节点跳过后变为 skipped，继续处理下一个节点
    - **Validates: Requirements 7.1**

  - [ ]* 6.12 编写节点重试属性测试
    - **Property 17: 节点重试任务创建** — error/completed 节点重试后创建新任务，结果覆盖原有内容
    - **Validates: Requirements 7.2**

  - [ ]* 6.13 编写失败节点汇总报告属性测试
    - **Property 27: 失败节点汇总报告** — 所有节点处理完毕后生成包含失败节点信息的汇总报告
    - **Validates: Requirements 13.2**

  - [ ]* 6.14 编写批量重试属性测试
    - **Property 28: 批量重试失败节点** — N 个 error 节点执行批量重试后创建 N 个重试任务
    - **Validates: Requirements 13.3**

- [x] 7. 后端路由与 WebSocket 端点集成
  - [x] 7.1 更新 `backend/main.py` 集成新架构
    - 使用 FastAPI lifespan 注册 TaskManager 启动和关闭
    - 注册 WebSocket 端点 `/ws`
    - 依赖注入 CourseService、WebSocketService、Storage 到 TaskManager
    - 移除旧的 `ConnectionManager` 和 threading 相关代码
    - _Requirements: 10.1, 10.3, 10.4_

  - [x] 7.2 更新 `backend/routers/courses.py` 路由
    - 更新 import 引用到新模块（course_service、knowledge_graph、quality_predictor）
    - 添加节点级操作 API（跳过、重试、自定义指令）作为 WebSocket 命令的 HTTP 回退
    - 添加大纲编辑确认 API
    - 添加生成配置更新 API
    - _Requirements: 7.1, 7.2, 7.3, 6.3, 14.4_

  - [x] 7.3 创建测试共享 fixtures `backend/tests/conftest.py` 和自定义策略 `backend/tests/strategies.py`
    - 定义 Hypothesis 自定义策略：`node_strategy`、`course_data_strategy`、`content_strategy`、`knowledge_entry_strategy`、`generation_config_strategy` 等
    - 定义共享 fixtures：mock CourseService、mock Storage、mock WebSocketService
    - _Requirements: 16.1, 16.2, 16.3_

- [x] 8. 检查点 - 后端核心功能验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 前端 WebSocket 客户端与状态管理重构
  - [x] 9.1 新建 `frontend/src/composables/useTaskWebSocket.ts`
    - 实现 WebSocket 连接、断开、自动重连逻辑
    - 实现按 courseId 订阅/取消订阅
    - 实现 `sendCommand` 发送 skip_node、retry_node、stop_node、custom_instruction、retry_all_failed 命令
    - 暴露 `isConnected`、`connectionState` 响应式状态
    - WebSocket 断开时自动回退到 HTTP 轮询，重连后停止轮询
    - _Requirements: 1.3, 1.4, 1.5_

  - [x] 9.2 重构 `frontend/src/stores/generation.ts` GenerationStore
    - 移除 `fetchGlobalTasks` 中基于 `Math.random()` 的随机刷新逻辑
    - 集成 `useTaskWebSocket`，WebSocket 连接成功后停止 `globalPollingTimer`
    - 实现 WebSocket 事件处理：`handleWSProgressUpdate`、`handleWSNodeCompleted`、`handleWSStreamChunk`、`handleWSTaskError`、`handleWSFailureReport`
    - 实现单节点控制 actions：`skipNode`、`retryNode`、`stopNode`、`setCustomInstruction`、`retryAllFailed`
    - 实现大纲编辑 actions：`enterOutlineEditMode`、`confirmOutline`、`updateOutline`
    - 编辑模式下阻断生成任务启动
    - 确定性刷新条件：仅在任务完成、手动切换课程、WebSocket 重连时刷新
    - _Requirements: 1.2, 1.3, 1.4, 6.2, 6.3, 7.1, 7.2, 7.5, 12.1, 12.2, 12.3, 13.3_

  - [ ]* 9.3 编写 GenerationStore 属性测试 `frontend/src/stores/__tests__/generation.test.ts`
    - **Property 2: 前端进度状态同步** — progress_update 事件更新对应任务状态，不影响其他任务
    - **Validates: Requirements 1.2**

  - [ ]* 9.4 编写精确节点更新属性测试
    - **Property 25: 精确节点更新** — node_completed 事件仅更新指定节点，其他节点不变
    - **Validates: Requirements 12.2**

  - [ ]* 9.5 编写确定性刷新条件属性测试
    - **Property 26: 确定性刷新条件** — 刷新仅在确定性条件下触发，不存在随机刷新逻辑
    - **Validates: Requirements 12.3**

  - [ ]* 9.6 编写编辑模式阻断属性测试
    - **Property 13: 编辑模式生成阻断** — 编辑模式下不启动任何生成任务
    - **Validates: Requirements 6.2**

  - [ ]* 9.7 编写大纲确认任务队列属性测试
    - **Property 14: 大纲确认后任务队列一致性** — 任务队列包含大纲中每个需要生成的节点，不包含大纲外节点
    - **Validates: Requirements 6.3**

- [x] 10. 前端 UI 组件增强
  - [x] 10.1 增强 `frontend/src/components/course/CourseTree.vue`
    - 实现可编辑模式：拖拽排序、重命名、删除、添加节点
    - 实现节点状态可视化：pending（灰色）、generating（蓝色脉冲）、completed（绿色勾选）、error（红色警告）、skipped（黄色跳过）
    - 实现总体进度条：已完成/总数 + 预估剩余时间
    - 实现节点级操作按钮：跳过、重试、自定义指令
    - 实现生成中节点的加载动画和已生成字数实时计数
    - 失败节点显示错误摘要和重试按钮
    - 支持为 level 1 节点设置难度级别和教学风格
    - 编辑模式下显示预估生成时间和内容量级
    - _Requirements: 6.1, 6.4, 7.1, 7.2, 7.3, 7.5, 8.1, 8.2, 8.4, 8.5, 14.1_

  - [x] 10.2 增强 `frontend/src/components/course/ContentArea.vue`
    - 实现流式内容实时渲染：接收 stream_chunk 追加到内容区域
    - 实现流式生成中的闪烁光标指示器
    - 实现"停止生成"按钮
    - 点击正在生成的节点时显示实时流式预览
    - _Requirements: 2.2, 2.3, 7.5, 8.3_

  - [x] 10.3 增强 `frontend/src/views/CourseView.vue`
    - 集成 WebSocket 连接状态指示器
    - 集成失败汇总弹窗和"重试所有失败"按钮
    - 集成大纲编辑确认流程
    - _Requirements: 1.4, 13.2, 13.3, 6.1_

- [x] 11. 检查点 - 前端功能验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. WebSocket 集成测试与端到端联调
  - [x] 12.1 编写 WebSocket 集成测试 `backend/tests/test_websocket_integration.py`
    - 测试 WebSocket 连接、订阅、消息推送完整流程
    - 测试多客户端并发订阅隔离
    - 测试客户端命令处理（skip_node、retry_node、stop_node、custom_instruction、retry_all_failed）
    - 测试 WebSocket 断开重连场景
    - _Requirements: 1.1, 1.5, 7.4, 16.4_

  - [ ]* 12.2 编写 WebSocket 消息结构属性测试
    - **Property 1: WebSocket 消息结构完整性与订阅隔离** — 消息包含全部必要字段，仅发送给订阅了对应 courseId 的客户端
    - **Validates: Requirements 1.1, 1.5, 1.6**

  - [ ]* 12.3 编写流式内容完整性属性测试
    - **Property 3: 流式内容完整性** — 所有 stream_chunk 拼接结果与最终写入 Storage 的完整内容一致
    - **Validates: Requirements 2.2, 2.5**

  - [ ]* 12.4 编写 WebSocket 命令处理属性测试
    - **Property 18: WebSocket 命令处理** — 有效命令被接受并转发给 TaskManager，返回确认响应
    - **Validates: Requirements 7.4**

  - [ ]* 12.5 编写前端 WebSocket 集成测试 `frontend/src/stores/__tests__/websocket.test.ts`
    - 测试 WebSocket 连接/断开时轮询模式切换
    - 测试消息接收和状态更新
    - _Requirements: 1.3, 1.4, 16.4_

- [ ] 13. 代码质量保障与 Linting 配置
  - [x] 13.1 配置 Python linting 工具
    - 配置 ruff 或 flake8，确保核心模块（CourseService、TaskManager、Storage、ContentValidator）无 linting 错误
    - 验证所有核心模块公共接口的 type hints 覆盖率
    - _Requirements: 9.5, 16.6_

- [x] 14. 最终检查点 - 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号以确保可追溯性
- 属性测试验证设计文档中定义的 33 个正确性属性
- 检查点确保增量验证，避免问题累积
- 后端使用 pytest + hypothesis，前端使用 vitest + fast-check
- 所有属性测试最少运行 100 次迭代
