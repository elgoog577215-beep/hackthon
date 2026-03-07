# 需求文档：AI 调用层完整文档化

## 背景

当前仓库的 AI 调用层已经完成了功能拆分（从单体 `ai_service.py` 拆分为 6 个子服务模块），但缺乏统一的开发者文档，导致：
- 新开发者难以快速理解各模块职责和调用方式
- 模型路由策略（智能模型 vs 快速模型）没有明确说明
- 提示词模板系统（`prompts.py`）的使用规范未文档化
- 流式 vs 非流式调用的选择依据不清晰

## 目标

为 AI 调用层提供完整、准确的开发者文档，覆盖架构、接口、提示词系统和扩展指南。

---

## 功能需求

### REQ-1：AI 调用层架构文档

**描述**：记录 AI 调用层的分层架构和模块关系。

**验收标准**：
- 描述 `AIBase → 子服务 → AIService(Facade)` 的继承链
- 说明 `AsyncOpenAI` 客户端的初始化方式（环境变量配置）
- 说明模型路由策略：`model_smart`（复杂任务）vs `model_fast`（简单任务）
- 包含架构图（Mermaid）

### REQ-2：核心调用方法文档

**描述**：记录 `_call_llm` 和 `_stream_llm` 两个核心方法的行为规范。

**验收标准**：
- `_call_llm`：说明重试机制（3次，指数退避）、流式聚合、`enable_thinking: False` 参数
- `_stream_llm`：说明异步生成器模式、错误处理（yield 错误信息而非抛出异常）
- 说明两者的选择依据：非流式用于需要完整响应后处理（JSON提取）；流式用于实时展示

### REQ-3：各子服务接口文档

**描述**：记录 6 个子服务模块的公开方法签名和职责。

**验收标准**：
- `AICourseService`：`generate_course`、`generate_sub_nodes`、`generate_node_content`、`redefine_node_content`（流式）、`extend_content`、`summarize_content`
- `AIQuizService`：`generate_quiz`、`analyze_quiz_performance`
- `AIQAService`：`socratic_tutor`（流式）、`answer_question_stream`（流式）、`summarize_note`（快速模型）、`summarize_chat`、`summarize_history`（快速模型）
- `AIGraphService`：`generate_knowledge_graph`、`locate_node`
- `AILearningService`：`generate_learning_path`、`analyze_knowledge_mastery`、`generate_review_schedule`、`submit_review_results`、`get_review_progress`；以及纯算法方法 `calculate_next_review`（SM-2）、`calculate_retention_rate`（艾宾浩斯）
- `AIDiagramService`：`generate_diagram`

### REQ-4：提示词模板系统文档

**描述**：记录 `prompts.py` 中 `PromptTemplate` 和 `get_prompt()` 的使用规范。

**验收标准**：
- 说明 `get_prompt(name)` 的调用方式和 `.format(**kwargs)` 的使用
- 列出所有已注册的模板名称
- 说明 `ACADEMIC_IDENTITY` 共享组件的作用
- 说明新增提示词模板的步骤

### REQ-5：工具方法文档

**描述**：记录 `AIBase` 中的辅助工具方法。

**验收标准**：
- `_extract_json`：从 LLM 响应中提取 JSON，支持 markdown 代码块和裸 JSON
- `_clean_mermaid_syntax` / `_clean_latex_syntax`：语法修复说明
- `clean_response_text`：聚合清理方法
- `_detect_discipline_type`：学科类型检测（用于调整提示词策略）
- `_extract_chapter_number`：章节编号提取

### REQ-6：扩展指南

**描述**：为开发者提供添加新 AI 功能的标准流程。

**验收标准**：
- 说明如何创建新的子服务（继承 `AIBase`，在 `AIService` 中添加多重继承）
- 说明何时使用 `_call_llm` vs `_stream_llm`
- 说明何时使用 `use_fast_model=True`
- 说明回退（fallback）模式的实现规范

---

## 非功能需求

- 文档语言：中文（与项目主语言一致）
- 文档格式：Markdown，可嵌入 Mermaid 图表
- 准确性：所有描述必须基于实际代码，不得凭假设编写
