# 需求文档：课程生成系统全方位优化

## 简介

本文档定义了 KnowledgeMap 课程生成系统的全方位优化需求，涵盖生成速度、内容质量、实时交互、用户体验和代码架构五大领域。目标是将现有系统从"能用"提升到"好用"，在保持功能完整性的同时大幅提升代码质量、性能和可维护性。

## 术语表

- **TaskManager**: 后端任务管理器，负责调度和执行课程生成任务的核心组件
- **GenerationStore**: 前端 Pinia 状态管理模块（generation.ts），管理生成任务队列和进度状态
- **CourseService**: 后端 AI 课程生成服务（ai_course_service_v5.py），封装 LLM 调用和内容生成逻辑
- **PromptEngine**: 提示词引擎（prompt_engine_v5.py），构建发送给 LLM 的提示词
- **ContentValidator**: 内容验证器（content_validator.py），校验生成内容的结构和质量
- **ConsistencyValidator**: 一致性验证器（content_consistency_validator.py），检查跨节点内容一致性
- **QualityPredictor**: 质量预测器，根据章节信息预测内容复杂度并选择生成模式
- **GlobalKnowledgeGraph**: 全局知识图谱，维护跨节点的概念、示例和公式注册表
- **Storage**: 存储模块（storage.py），基于文件系统的 JSON 持久化层
- **WebSocket_Service**: WebSocket 服务端，负责向前端推送实时任务状态更新
- **WebSocket_Client**: WebSocket 客户端组合式函数（useTaskWebSocket.ts），接收并处理服务端推送
- **ContentArea**: 内容展示区组件（ContentArea.vue），渲染课程节点内容
- **CourseTree**: 课程树组件（CourseTree.vue），展示课程大纲结构
- **Node**: 课程节点数据结构，包含 node_id、node_name、node_content、node_level 等字段
- **BatchAction**: TaskManager 中的批量操作单元，包含操作类型和目标节点
- **GenerationMode**: 生成模式枚举（FAST/BALANCED/QUALITY），决定 LLM 调用次数和质量检查深度

## 需求

### 需求 1：WebSocket 实时推送替代 HTTP 轮询

**用户故事：** 作为用户，我希望在课程生成过程中实时看到进度更新，而不是每 2 秒才刷新一次，以便获得流畅的生成体验。

#### 验收标准

1. WHEN TaskManager 完成一个 Node 的内容生成, THE WebSocket_Service SHALL 在 500ms 内向已订阅的客户端推送 node_completed 事件，包含该 Node 的完整数据
2. WHEN WebSocket_Client 收到 progress_update 事件, THE GenerationStore SHALL 更新对应任务的进度状态，且不再依赖 HTTP 轮询获取进度信息
3. WHEN WebSocket_Client 成功建立连接, THE GenerationStore SHALL 停止 globalPollingTimer 定时器
4. IF WebSocket 连接断开, THEN THE GenerationStore SHALL 自动回退到 HTTP 轮询模式，并在 WebSocket 重连成功后再次停止轮询
5. THE WebSocket_Service SHALL 支持按 courseId 订阅，仅推送用户关注的课程的更新事件
6. WHEN TaskManager 更新任务状态, THE WebSocket_Service SHALL 推送包含 taskId、courseId、status、progress、currentNodeName、completedNodes、totalNodes 字段的结构化消息

### 需求 2：流式内容输出与实时预览

**用户故事：** 作为用户，我希望在内容生成过程中实时看到文字逐步出现，而不是等待整个节点生成完毕后才显示，以便及时了解生成质量。

#### 验收标准

1. WHEN TaskManager 通过批量模式生成 Node 内容, THE CourseService SHALL 使用流式 API 调用 LLM，并将每个文本片段实时通过 WebSocket 推送给前端
2. WHEN WebSocket_Client 收到流式内容片段, THE ContentArea SHALL 将片段追加到对应 Node 的内容区域并实时渲染 Markdown
3. WHILE 内容正在流式生成, THE ContentArea SHALL 在内容末尾显示一个闪烁的光标指示器
4. IF 流式传输中断, THEN THE CourseService SHALL 记录已接收的内容长度，并在重试时从断点位置继续生成
5. THE CourseService SHALL 在流式输出的同时缓存完整内容，流式结束后将完整内容写入 Storage

### 需求 3：并发生成策略优化

**用户故事：** 作为用户，我希望课程生成速度更快，多个章节能同时生成，以便减少等待时间。

#### 验收标准

1. THE TaskManager SHALL 使用 FastAPI 原生的 asyncio 事件循环执行异步任务，替代当前 threading.Thread + asyncio.new_event_loop 的混合模式
2. WHEN 执行批量内容生成, THE TaskManager SHALL 支持可配置的最大并发数（默认值为 5），并通过 asyncio.Semaphore 控制并发上限
3. WHEN 同一课程存在多个待生成节点, THE TaskManager SHALL 按照节点层级优先（level 1 > level 2 > level 3）、同层级按顺序的策略调度生成任务
4. THE TaskManager SHALL 在每个批次完成后立即调度下一批可用节点，而非等待整个阶段完成
5. IF 某个节点生成失败, THEN THE TaskManager SHALL 仅重试该节点（最多 2 次），不影响其他节点的并发生成

### 需求 4：跨节点上下文增强

**用户故事：** 作为用户，我希望生成的课程内容在章节之间保持连贯性和一致性，避免重复内容和断裂的叙述。

#### 验收标准

1. WHEN 生成某个 Node 的内容, THE CourseService SHALL 向 LLM 提供该 Node 的前序节点摘要（最多 3 个同级节点，每个摘要不超过 200 字）和后续节点标题列表
2. THE GlobalKnowledgeGraph SHALL 为每个已生成节点维护结构化摘要，包含：核心概念列表、关键术语定义、已使用的案例标题
3. WHEN 生成内容引用了已在其他节点定义的术语, THE CourseService SHALL 在提示词中标注该术语的原始定义位置，避免重复定义
4. WHEN 所有节点内容生成完毕, THE ConsistencyValidator SHALL 执行全局一致性检查，检测重复案例、矛盾定义和断裂的章节引用
5. IF ConsistencyValidator 检测到一致性问题, THEN THE CourseService SHALL 自动修复严重问题（重复案例、错误引用），并将轻微问题记录到生成日志

### 需求 5：内容质量评估体系升级

**用户故事：** 作为用户，我希望生成的内容质量稳定可靠，系统能自动识别和修复低质量内容。

#### 验收标准

1. THE QualityPredictor SHALL 基于以下维度评估内容质量：结构完整性（是否包含必要章节）、内容深度（关键概念覆盖率）、可读性（段落长度和过渡语句）、格式规范性（Markdown 语法正确性）
2. THE ContentValidator SHALL 使用结构化评分规则替代简单的字符数阈值（当前 600 字符），评估维度包括：最小段落数、代码示例数量（技术类课程）、概念定义数量
3. WHEN 内容质量评分低于 0.6, THE CourseService SHALL 自动触发内容修复流程，将具体的质量问题作为修复指令传递给 LLM
4. THE ContentValidator SHALL 在内容生成完成后立即验证 Mermaid 图表语法，检测未闭合的标签、错误的节点引用和不支持的图表类型
5. IF Mermaid 图表语法验证失败, THEN THE CourseService SHALL 自动修复图表语法或移除无法修复的图表并记录警告


### 需求 6：课程大纲预览与编辑

**用户故事：** 作为用户，我希望在内容生成开始前能预览和编辑课程大纲，以便调整不满意的章节结构。

#### 验收标准

1. WHEN 课程大纲生成完毕, THE CourseTree SHALL 进入可编辑模式，允许用户拖拽调整节点顺序、重命名节点、删除节点和添加新节点
2. WHILE CourseTree 处于编辑模式, THE GenerationStore SHALL 暂不启动内容生成任务，直到用户确认大纲
3. WHEN 用户确认大纲, THE GenerationStore SHALL 基于最终大纲结构创建生成任务队列
4. THE CourseTree SHALL 在编辑模式下为每个节点显示预估生成时间和内容量级（基于节点层级和标题复杂度）
5. IF 用户在内容生成过程中修改大纲, THEN THE TaskManager SHALL 取消受影响节点的待执行任务，并根据新大纲重新调度

### 需求 7：单节点生成控制

**用户故事：** 作为用户，我希望能对单个节点进行跳过、重试或自定义指令操作，而不是只能控制整个生成任务。

#### 验收标准

1. WHEN 用户对某个待生成节点点击"跳过", THE TaskManager SHALL 将该节点标记为 skipped 状态，并继续处理队列中的下一个节点
2. WHEN 用户对某个已失败或已完成的节点点击"重新生成", THE TaskManager SHALL 创建一个新的生成任务仅针对该节点，并将结果覆盖原有内容
3. WHEN 用户为某个节点输入自定义生成指令, THE CourseService SHALL 将该指令作为附加约束注入到该节点的生成提示词中
4. THE WebSocket_Service SHALL 支持接收前端发送的 skip_node、retry_node、custom_instruction 命令，并转发给 TaskManager 执行
5. WHILE 某个节点正在生成中, THE ContentArea SHALL 显示"停止生成"按钮，点击后 TaskManager 取消该节点的 LLM 调用并保留已生成的部分内容

### 需求 8：节点生成状态可视化

**用户故事：** 作为用户，我希望在课程树中直观看到每个节点的生成状态，以便了解整体进度。

#### 验收标准

1. THE CourseTree SHALL 为每个节点显示以下状态之一的视觉标识：pending（灰色）、generating（蓝色脉冲动画）、completed（绿色勾选）、error（红色警告）、skipped（黄色跳过标记）
2. WHILE 某个节点正在生成, THE CourseTree SHALL 在该节点旁显示一个加载动画和已生成字数的实时计数
3. WHEN 用户点击一个正在生成中的节点, THE ContentArea SHALL 显示该节点的实时流式内容预览
4. THE CourseTree SHALL 在课程树顶部显示一个总体进度条，包含已完成节点数/总节点数和预估剩余时间
5. IF 某个节点生成失败, THEN THE CourseTree SHALL 在该节点旁显示错误摘要和"重试"按钮

### 需求 9：代码架构清理与统一

**用户故事：** 作为开发者，我希望代码库中只保留一个版本的课程生成服务，消除冗余代码，以便降低维护成本和理解难度。

#### 验收标准

1. THE 代码库 SHALL 仅保留 ai_course_service_v5.py 作为唯一的课程生成服务实现，移除 ai_course_service.py、ai_course_service_v2.py、ai_course_service_v3.py、ai_course_service_v4.py
2. THE 代码库 SHALL 仅保留 prompt_engine_v5.py 作为唯一的提示词引擎实现，移除 prompts.py 和 prompts_v2.py，并将所有引用更新到 prompt_engine_v5
3. WHEN 移除旧版本文件, THE 代码库 SHALL 确保所有 import 语句和路由注册引用已更新为新版本模块
4. THE CourseService SHALL 将 GlobalKnowledgeGraph、ContentCache、QualityPredictor 从 ai_course_service_v5.py 中拆分为独立模块，每个模块职责单一
5. THE 代码库 SHALL 为所有公共函数和类提供类型注解（Python type hints），覆盖率达到核心模块（CourseService、TaskManager、Storage、ContentValidator）的全部公共接口

### 需求 10：异步架构统一

**用户故事：** 作为开发者，我希望后端的异步模型统一且高效，避免线程和事件循环的混合使用导致的潜在问题。

#### 验收标准

1. THE TaskManager SHALL 使用 FastAPI 的 BackgroundTasks 或 asyncio.create_task 在主事件循环中调度任务，移除 threading.Thread 和 asyncio.new_event_loop 的使用
2. THE TaskManager SHALL 使用 asyncio.Queue 替代当前基于列表遍历的任务调度机制，实现生产者-消费者模式
3. WHEN FastAPI 应用启动, THE TaskManager SHALL 通过 FastAPI 的 lifespan 事件注册后台任务管理器
4. WHEN FastAPI 应用关闭, THE TaskManager SHALL 优雅地等待所有正在执行的任务完成（最长等待 30 秒），然后释放资源
5. THE Storage SHALL 使用 asyncio.Lock 保护文件写入操作，防止并发写入导致数据损坏

### 需求 11：存储层健壮性增强

**用户故事：** 作为开发者，我希望存储层能安全处理并发写入，避免数据丢失或文件损坏。

#### 验收标准

1. THE Storage SHALL 使用原子写入模式（先写临时文件，再重命名）保存课程数据，防止写入中断导致文件损坏
2. THE Storage SHALL 使用文件级锁（每个 course_id 一把锁）保护并发写入，同一课程的写入操作串行执行
3. WHEN 文件写入失败, THE Storage SHALL 保留上一个有效版本的数据文件，并记录错误日志
4. THE Storage SHALL 在应用启动时验证所有课程 JSON 文件的完整性（有效 JSON 格式），对损坏的文件记录警告并尝试从备份恢复
5. THE Storage SHALL 支持为每个课程保留最近 3 个版本的数据快照，支持手动回滚

### 需求 12：去除随机刷新逻辑

**用户故事：** 作为开发者，我希望系统行为可预测，不依赖随机概率触发数据刷新。

#### 验收标准

1. THE GenerationStore SHALL 移除 fetchGlobalTasks 中基于 Math.random() 的随机刷新逻辑
2. WHEN WebSocket_Client 收到 node_completed 或 nodes_updated 事件, THE CourseStore SHALL 精确更新受影响的节点数据，而非刷新整个课程
3. THE GenerationStore SHALL 仅在以下确定性条件下触发课程数据刷新：任务状态变更为 completed、用户手动切换课程、WebSocket 重连成功后

### 需求 13：错误恢复与容错机制

**用户故事：** 作为用户，我希望单个节点的生成失败不会影响整个课程的生成进度，并且能方便地重试失败的节点。

#### 验收标准

1. IF 某个节点生成失败且重试次数耗尽, THEN THE TaskManager SHALL 将该节点标记为 error 状态，继续处理队列中的其他节点
2. WHEN 任务中存在失败节点, THE TaskManager SHALL 在所有其他节点处理完毕后生成一份失败节点汇总报告，通过 WebSocket 推送给前端
3. THE GenerationStore SHALL 提供"重试所有失败节点"的批量操作，一键重新生成所有 error 状态的节点
4. IF LLM API 返回速率限制错误（429）, THEN THE TaskManager SHALL 使用指数退避策略（初始 2 秒，最大 60 秒）等待后重试
5. THE TaskManager SHALL 为每个任务维护详细的执行日志，包含每个节点的开始时间、结束时间、重试次数、错误信息和生成字数

### 需求 14：生成配置灵活性增强

**用户故事：** 作为用户，我希望能为不同章节设置不同的生成参数，以便精细控制课程内容的深度和风格。

#### 验收标准

1. THE CourseTree SHALL 支持为每个 level 1 节点单独设置难度级别（beginner/intermediate/advanced）和教学风格
2. WHEN 用户未为某个节点设置单独配置, THE CourseService SHALL 使用课程级别的默认配置
3. THE CourseService SHALL 支持以下生成参数：难度级别、教学风格、目标字数范围、是否包含代码示例、是否包含练习题
4. WHEN 用户修改某个节点的生成配置后点击"重新生成", THE TaskManager SHALL 使用新配置重新生成该节点内容

### 需求 15：案例与示例去重增强

**用户故事：** 作为用户，我希望课程中不同章节使用不同的案例和示例，避免内容重复。

#### 验收标准

1. THE GlobalKnowledgeGraph SHALL 为每个已使用的案例和示例维护完整的文本摘要（不少于 50 字）和所属节点 ID
2. WHEN 生成新节点内容, THE CourseService SHALL 在提示词中列出已使用的案例标题列表，明确要求 LLM 避免重复
3. WHEN 内容生成完毕, THE ConsistencyValidator SHALL 使用文本相似度算法（余弦相似度，阈值 0.8）检测跨节点的案例重复
4. IF 检测到重复案例, THEN THE CourseService SHALL 自动替换重复案例，在提示词中指定需要替换的案例和替换方向

### 需求 16：测试覆盖与代码质量保障

**用户故事：** 作为开发者，我希望核心模块有充分的测试覆盖，以便在重构过程中确保功能正确性。

#### 验收标准

1. THE 代码库 SHALL 为 TaskManager 的任务调度、并发控制、错误恢复逻辑提供单元测试，覆盖正常流程和异常流程
2. THE 代码库 SHALL 为 Storage 的原子写入、并发锁、版本管理逻辑提供单元测试
3. THE 代码库 SHALL 为 ContentValidator 的质量评分、Mermaid 语法验证逻辑提供单元测试
4. THE 代码库 SHALL 为 WebSocket 消息处理逻辑提供集成测试，验证消息推送和状态同步的正确性
5. FOR ALL 有效的课程 JSON 数据, 序列化后再反序列化 SHALL 产生与原始数据等价的对象（往返属性）
6. THE 代码库 SHALL 配置 Python linting 工具（ruff 或 flake8），并确保核心模块无 linting 错误
