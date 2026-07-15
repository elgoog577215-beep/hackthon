# 任务列表：AI 调用层文档化

## Task 1: 创建 AI 调用层架构文档

**对应需求**: REQ-1, REQ-2

**目标文件**: `docs/ai-layer.md`

**具体工作**:
- [ ] 阅读 `backend/ai_base.py` 完整实现，确认 `AsyncOpenAI` 客户端初始化逻辑
- [ ] 阅读 `backend/ai_service.py`，确认 Facade 模式的多重继承结构
- [ ] 编写架构概述，包含 Mermaid 继承关系图
- [ ] 记录 `_call_llm` 的完整行为：模型路由、流式聚合、重试（3次指数退避）、`enable_thinking: False`
- [ ] 记录 `_stream_llm` 的行为：异步生成器、错误 yield 而非抛出
- [ ] 说明两种调用模式的选择依据

**完成标准**: `docs/ai-layer.md` 存在，内容准确反映代码实现

---

## Task 2: 记录各子服务公开接口

**对应需求**: REQ-3

**目标文件**: `docs/ai-layer.md`（追加到 Task 1 的文件）

**具体工作**:
- [ ] 阅读 `backend/ai_course_service.py`，记录所有 `async def` 公开方法的签名、参数和返回值
- [ ] 阅读 `backend/ai_quiz_service.py`，记录 `generate_quiz`（含回退机制）和 `analyze_quiz_performance`
- [ ] 阅读 `backend/ai_qa_service.py`，记录流式方法（`socratic_tutor`、`answer_question_stream`）和快速模型方法（`summarize_note`、`summarize_history`）
- [ ] 阅读 `backend/ai_graph_service.py`，记录 `generate_knowledge_graph` 的自愈验证流程
- [ ] 阅读 `backend/ai_learning_service.py`，区分 AI 调用方法和纯算法方法（SM-2、艾宾浩斯）
- [ ] 阅读 `backend/ai_diagram_service.py`，记录 `generate_diagram` 和 `_extract_mermaid_code`

**完成标准**: 每个子服务有独立章节，方法签名与代码一致

---

## Task 3: 记录提示词模板系统

**对应需求**: REQ-4

**目标文件**: `docs/prompt-system.md`（更新现有文件）

**具体工作**:
- [ ] 阅读 `backend/prompts.py`，确认 `PromptTemplate` 类的结构和 `get_prompt()` 实现
- [ ] 列出所有已注册的模板名称（通过 `list_prompts()` 或直接阅读注册代码）
- [ ] 记录 `ACADEMIC_IDENTITY` 共享组件的内容和使用场景
- [ ] 编写"新增提示词模板"的步骤说明
- [ ] 记录 `format(**kwargs)` 的占位符规范

**完成标准**: `docs/prompt-system.md` 包含完整的模板列表和使用示例

---

## Task 4: 记录工具方法

**对应需求**: REQ-5

**目标文件**: `docs/ai-layer.md`（追加工具方法章节）

**具体工作**:
- [ ] 阅读 `ai_base.py` 中 `_extract_json` 的实现，记录支持的输入格式（markdown 代码块、裸 JSON）
- [ ] 记录 `_clean_mermaid_syntax` 和 `_clean_latex_syntax` 处理的常见问题
- [ ] 记录 `clean_response_text` 的聚合清理顺序
- [ ] 记录 `_detect_discipline_type` 的检测逻辑和返回值类型
- [ ] 记录 `_extract_chapter_number` 的正则匹配规则

**完成标准**: 工具方法章节存在，每个方法有简短说明和使用场景

---

## Task 5: 编写扩展指南

**对应需求**: REQ-6

**目标文件**: `docs/ai-layer.md`（追加扩展指南章节）

**具体工作**:
- [ ] 编写"添加新子服务"的步骤（创建文件 → 继承 `AIBase` → 在 `ai_service.py` 添加多重继承）
- [ ] 编写"选择调用模式"决策树：何时用 `_call_llm`，何时用 `_stream_llm`，何时用 `use_fast_model=True`
- [ ] 编写"实现回退机制"规范：参考 `_generate_fallback_knowledge_graph` 和 `_generate_smart_fallback_quiz` 的模式
- [ ] 添加一个完整的新子服务示例代码片段

**完成标准**: 扩展指南章节存在，包含可操作的步骤和代码示例

---

## Task 6: 更新 design.md 中的 AI 层描述

**对应需求**: REQ-1, REQ-3

**目标文件**: `.kiro/specs/documentation-completion/design.md`

**具体工作**:
- [ ] 核对 design.md 第 5 节"AI提示工程设计"与实际代码的一致性
- [ ] 修正不准确的描述（如依赖版本、模型名称等）
- [ ] 在第 2.2 节"模块划分"中补充 AI 子服务的分层说明
- [ ] 确认 API 端点总览（第 15.3 节）与 `backend/main.py` 实际路由一致

**完成标准**: design.md 中 AI 相关描述与代码实现一致，无明显错误
