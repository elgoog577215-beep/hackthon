# 需求文档：代码库优化与重构

## 简介

Knowledge Map AI 项目在快速迭代中积累了大量技术债务：单体文件过大、职责混乱、死代码残留、抽象不一致等问题严重影响了可维护性和开发效率。本需求定义了一套分阶段的代码库优化方案，目标是在不改变用户可见功能的前提下，提升代码的可读性、可维护性和工程质量。

## 术语表

- **Router**：FastAPI 的 APIRouter，用于将路由按功能域拆分到独立模块
- **Store**：Pinia 状态管理单元，管理 Vue 应用中的共享状态
- **HTTP_Client**：前端用于发起 HTTP 请求的 Axios 封装模块（当前为 `utils/http.ts`）
- **API_Client_Legacy**：前端未使用的遗留 HTTP 客户端模块（`utils/apiClient.ts`）
- **Annotations_Legacy**：旧版标注系统，已被 Notes 系统取代但仍残留在代码中
- **Notes_System**：新版笔记系统，是当前活跃使用的笔记功能
- **Course_Store**：前端 Pinia 中管理课程相关状态的 store（`stores/course.ts`）
- **AI_Service**：后端 AI 服务类（`backend/ai_service.py`），包含所有 LLM 交互逻辑
- **Main_Module**：后端主模块（`backend/main.py`），包含所有 API 路由定义
- **Inline_Model**：在 Main_Module 中内联定义的 Pydantic 模型，与 `models.py` 中的定义重复
- **Shared_Config**：`shared/` 目录下的跨端共享配置（Python 和 TypeScript 各一份）
- **Task_Queue_Frontend**：前端 Course_Store 中的课程生成队列管理逻辑
- **Task_Queue_Backend**：后端 `task_manager.py` 中的后台任务队列
- **Vite_Proxy**：Vite 开发服务器的 API 代理配置

## 需求

### 需求 1：后端路由模块化拆分

**用户故事：** 作为开发者，我希望后端路由按功能域拆分为独立模块，以便我能快速定位和修改特定功能的 API 端点。

#### 验收标准

1. THE Main_Module SHALL 使用 FastAPI APIRouter 将路由拆分为以下功能域模块：课程管理（courses）、节点操作（nodes）、标注与笔记（annotations）、测验（quiz）、知识图谱（knowledge_graph）、学习路径与复习（learning）、AI 辅导（tutor）、代码执行（code_execution）、图表生成（diagrams）、任务管理（tasks）
2. WHEN 路由拆分完成后，THE Main_Module SHALL 仅保留应用初始化、中间件配置、WebSocket 管理和 Router 注册逻辑，行数不超过 200 行
3. THE Router 模块 SHALL 各自存放在 `backend/routers/` 目录下，每个文件对应一个功能域
4. WHEN 路由拆分完成后，THE 系统 SHALL 保持所有现有 API 端点的路径和行为不变
5. THE 每个 Router 模块 SHALL 仅包含路由定义和请求参数校验，业务逻辑调用委托给对应的 service 模块

### 需求 2：消除后端内联模型重复

**用户故事：** 作为开发者，我希望所有 Pydantic 请求/响应模型集中定义在 `models.py` 中，以便我能在一个地方查看和维护所有数据结构。

#### 验收标准

1. THE Main_Module 中的所有 Inline_Model（KnowledgeGraphRequest、SummarizeNodeRequest、GenerateDiagramRequest、GenerateDiagramResponse、CreateGoalRequest、UpdateGoalProgressRequest、RecordLearningRequest、SessionSummaryRequest、TutorContextRequest）SHALL 迁移到 `backend/models.py` 中统一定义
2. WHEN 模型迁移完成后，THE Main_Module SHALL 不包含任何 Pydantic BaseModel 子类定义
3. THE `models.py` SHALL 按功能域使用注释分组组织模型定义（课程、节点、标注、测验、学习路径、复习、代码执行、图表、辅导）
4. WHEN 模型迁移完成后，THE 所有 Router 模块 SHALL 从 `models.py` 导入模型，不存在重复定义

### 需求 3：后端 AI 服务拆分

**用户故事：** 作为开发者，我希望 AI_Service 按功能域拆分为独立的服务模块，以便我能独立理解和修改每个 AI 功能的实现。

#### 验收标准

1. THE AI_Service SHALL 拆分为以下独立服务模块：`ai_course_service.py`（课程生成与节点内容）、`ai_quiz_service.py`（测验生成与分析）、`ai_qa_service.py`（问答与聊天）、`ai_graph_service.py`（知识图谱生成）、`ai_learning_service.py`（学习路径与复习调度）、`ai_diagram_service.py`（图表生成）
2. THE 各服务模块 SHALL 共享一个基础 LLM 调用层（`ai_base.py`），包含 `_call_llm`、`_stream_llm`、`_extract_json`、`clean_response_text` 等通用方法
3. WHEN 拆分完成后，THE 原 `ai_service.py` SHALL 作为向后兼容的门面模块（facade），从各子模块重新导出所有公开方法，确保现有调用方无需修改
4. THE 每个服务模块 SHALL 包含完整的错误处理和 fallback 逻辑，不依赖其他服务模块的内部实现

### 需求 4：前端 HTTP 客户端统一

**用户故事：** 作为开发者，我希望前端只有一个 HTTP 客户端模块，以便我能清楚地知道该使用哪个模块发起 API 请求。

#### 验收标准

1. THE API_Client_Legacy（`frontend/src/utils/apiClient.ts`）SHALL 被删除，因为该模块在整个前端代码库中没有任何导入引用
2. WHEN API_Client_Legacy 被删除后，THE HTTP_Client（`frontend/src/utils/http.ts`）SHALL 作为唯一的 HTTP 请求模块
3. THE KnowledgeGraph 组件 SHALL 通过 Course_Store 的 action 发起 HTTP 请求，而非直接导入 HTTP_Client
4. THE Course_Store 中 `locateNode` 方法 SHALL 使用 HTTP_Client（`http`）替代直接使用 `axios`，保持与其他方法一致的请求方式

### 需求 5：前端 Course Store 拆分

**用户故事：** 作为开发者，我希望 Course_Store 按功能域拆分为多个独立的 Pinia store，以便我能快速定位特定功能的状态管理逻辑。

#### 验收标准

1. THE Course_Store SHALL 拆分为以下独立 store：`course.ts`（课程列表、当前课程、节点树的核心状态与操作）、`generation.ts`（课程生成队列、任务管理、进度追踪）、`notes.ts`（笔记的增删改查、导出、标签与分类管理）、`learning.ts`（学习路径、知识掌握度、学习统计）、`review.ts`（间隔复习调度、复习结果提交、复习进度）、`chat.ts`（聊天历史、AI 问答、流式响应管理）
2. WHEN 拆分完成后，THE 各 store 之间 SHALL 通过 Pinia 的 `useXxxStore()` 进行跨 store 访问，不使用直接的状态引用
3. THE 拆分后的各 store SHALL 不包含任何未被引用的 state、getter 或 action（即清除所有死代码）
4. WHEN 拆分完成后，THE 所有引用 Course_Store 的组件和 composable SHALL 更新为从对应的新 store 导入

### 需求 6：清除 Annotations 遗留系统

**用户故事：** 作为开发者，我希望移除旧版 Annotations 系统的残留代码，以便 Notes_System 成为唯一的笔记管理方案，消除概念混乱。

#### 验收标准

1. THE Course_Store 中的 `annotations` state 字段和 `Annotation` 接口 SHALL 被移除
2. THE Course_Store 中的 `activeAnnotation` state 字段 SHALL 被移除
3. THE Course_Store 中所有引用 `annotations` 数组的代码（如 `deleteNote` 中的 `this.annotations.filter`）SHALL 被清除
4. WHEN Annotations_Legacy 代码被移除后，THE Notes_System SHALL 保持所有现有笔记功能正常工作，包括创建、编辑、删除、标签管理、分类管理和导出
5. IF 后端 annotations API 端点仅被 Notes_System 使用，THEN THE annotations 端点 SHALL 保留但在代码注释中标注其服务于 Notes_System

### 需求 7：统一 API 路径前缀

**用户故事：** 作为开发者，我希望所有后端 API 端点使用统一的 `/api` 前缀，以便简化 Vite 代理配置并为未来的 API 版本控制做准备。

#### 验收标准

1. THE 所有后端 API 路由 SHALL 使用 `/api` 作为统一路径前缀（例如 `/courses/{id}` 变为 `/api/courses/{id}`）
2. WHEN API 路径前缀统一后，THE Vite_Proxy SHALL 简化为单一的 `/api` 代理规则和一个 `/ws` WebSocket 代理规则
3. WHEN API 路径前缀统一后，THE 前端所有 HTTP 请求路径 SHALL 更新为使用 `/api` 前缀
4. THE 后端静态文件服务（`/` 路径）SHALL 不受 API 前缀变更影响，继续正常提供前端静态资源

### 需求 8：前端死代码清理

**用户故事：** 作为开发者，我希望前端代码库中不存在未使用的模块、接口和函数，以便减少代码噪音和维护负担。

#### 验收标准

1. THE 前端代码库 SHALL 不包含任何未被导入引用的 TypeScript 模块文件
2. THE 前端代码库 SHALL 不包含任何未被使用的导出接口（export interface）或导出类型（export type）
3. THE Course_Store 拆分过程中识别出的未被任何组件或 composable 引用的 state 字段、getter 和 action SHALL 被移除
4. WHEN 死代码清理完成后，THE 前端项目 SHALL 通过 `npm run build`（包含类型检查）无错误编译

### 需求 9：后端测试覆盖增强

**用户故事：** 作为开发者，我希望后端关键模块有基本的测试覆盖，以便我在重构时能快速验证功能是否正常。

#### 验收标准

1. THE 后端测试 SHALL 覆盖以下关键模块：存储层（`storage.py` 的读写操作）、课程 CRUD API 端点、节点操作 API 端点、复习调度算法（SM-2 计算）
2. THE 测试 SHALL 存放在 `tests/` 目录下，按模块组织（如 `test_storage.py`、`test_courses_api.py`、`test_review.py`）
3. WHEN 所有重构完成后，THE 后端测试 SHALL 全部通过，验证重构未引入功能回归
4. THE SM-2 复习调度算法测试 SHALL 包含 round-trip 属性验证：对于任意有效的复习结果输入，计算下次复习时间后再次提交相同质量的复习结果，ease_factor 的变化方向 SHALL 保持一致

### 需求 10：前端测试基础建设

**用户故事：** 作为开发者，我希望前端关键 store 和工具函数有基本的单元测试，以便我在重构 store 时能验证逻辑正确性。

#### 验收标准

1. THE 前端测试 SHALL 覆盖以下模块：拆分后的各 Pinia store 的核心 action、`utils/http.ts` 的错误处理逻辑、`utils/markdown.ts` 的渲染工具函数、`shared/prompt-config.ts` 的验证规则
2. THE 测试 SHALL 使用 Vitest 框架，存放在 `frontend/src/__tests__/` 目录下
3. WHEN 所有前端重构完成后，THE 前端测试 SHALL 通过 `npm run test` 全部通过
4. FOR ALL 有效的 prompt-config 验证规则输入，THE 验证函数 SHALL 对相同输入产生相同的验证结果（幂等性）
