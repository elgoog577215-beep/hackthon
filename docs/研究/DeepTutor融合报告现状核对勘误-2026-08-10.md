# DeepTutor 融合研究报告勘误附页（核对日期 2026-08-10）

> 文档状态：对 [DeepTutor 与灵知融合深度研究及实施方案](./DeepTutor-与灵知融合深度研究及实施方案-2026-07-23.md) 的逐条现状核对，不是当前产品或实施真源
>
> 核对基线：`dev/lz-ai-teacher` 分支当日代码（基线提交 `26b368bd`）
>
> 核对方式：每条结论都落到具体文件、符号或提交；无法从仓库确定的一律标注为"未确定"，不做推断

原报告写于 2026-07-23，其后主干推进了 228 个非合并提交（含 61 个合并提交）。报告本身最后一次改动是 2026-08-04 的文档重整（`4b6f39ea`），因此正文里有少量描述已经晚于标题日期。本附页只回答一个问题：**读原报告时，哪些关于灵知的描述今天不能直接采信。**

结论先行：报告的**架构判断（灵知是 Workflow-first、Agent 执行层应共享领域真源、不建立第二写权限）今天仍然成立**，不需要修订。已过时的是若干**事实性描述**，其中两条会直接误导 PoC 范围与决策清单。

## 1. 判定口径

| 判定 | 含义 |
| --- | --- |
| 仍然成立 | 今天的代码与报告描述一致 |
| 已过时 | 报告描述与今天的代码矛盾，直接采信会出错 |
| 需要修正表述 | 事实方向没错，但措辞会让读者找不到对象或高估/低估现状 |
| 未确定 | 仓库内证据不足，需要线下确认 |

## 2. 会影响决策的两条（优先修订）

### 2.1 「AI 老师不能调用研究工具」——已过时

原报告第 6.2 节把"发现缺资料后调用研究工具"列为灵知当前**做不到**的事，第 22 节又把"是否允许联网研究？出站域名和来源政策是什么？"列为 **PoC 前必须决定**的开放问题。

这两处今天都不成立：联网检索已经上线。

- 统一检索网关 `backend/web_retrieval.py`（`fb7c8f6f`，2026-08-05 19:38）。
- AI 老师专用检索 `backend/ai_teacher_retrieval.py`（`a1b39ef8`，2026-08-05 19:40），在 `backend/routers/assistant.py` 接入。
- 出站政策已经写进当前架构真源，不再是开放问题：默认 `SearXNGSearchProvider` 只接受回环地址、只访问同机 SearXNG；来源需通过本地相关性、URL 安全、隐私脱敏、注入过滤和分层规则准入（`docs/系统架构.md` 第 6 节）。
- 覆盖范围也已界定：只覆盖新课程蓝图/正文、题库和 AI 老师；评分、诊断、学习者模型、学习路径和 PPT 链路不出站（同上）。

**但报告的底层判断仍然对**，只是措辞需要精确化：检索是**确定性前置步骤**，不是模型自选的工具。开关是会话级设置（`should_retrieve_for_message`，`backend/ai_teacher_retrieval.py:136`，读 `conversation.retrieval_enabled`），检索在调用模型**之前**跑完，模型无法在回答中途"发现资料不足"再去检索。直接动作（保存笔记等）不触发检索。

> 建议修订为：检索能力已具备，但仍是前置管线而非 Agent 可选工具；PoC 需要决定的不再是"是否允许联网"，而是"是否允许模型自主决定何时检索"。

### 2.2 「灵知是 Python 3.10」——需要修正表述，且仓库内部本身不一致

报告第 0.2、6、12、21、22 节反复以"灵知 Python 3.10 vs DeepTutor >=3.11"作为 sidecar 隔离的主要理由之一，并把"升级 3.11 还是保持 3.10"列为正式实现前必须决定的事项。

今天的实际情况比"3.10"或"已升到 3.12"都更复杂——仓库内有四个互相矛盾的声明：

| 位置 | 声明 | 证据 |
| --- | --- | --- |
| 主镜像 | Python 3.10 | `Dockerfile:16` `FROM python:3.10-slim` |
| lint 目标 | Python 3.10+ | `pyproject.toml:3` `target-version = "py310"` |
| README | Python 3.10+ | `README.md:32` |
| 独立 Runner 镜像 | Python 3.12 | `runner/Dockerfile:3` `FROM python:3.12-slim` |
| 本地开发 venv | Python 3.12 | `backend/.venv/pyvenv.cfg` `version_info = 3.12` |

补充两点：`pyproject.toml` **没有 `requires-python`**，只设了 ruff 的 `target-version`；`.github/workflows/` 下三个工作流**没有任何 `setup-python` 或版本 pin**，因此 CI 不强制任何版本。部署走 `scripts/github-action-deploy.sh`，使用宿主机 `python3`，其版本**无法从仓库确定**。

> 建议修订为：不要把"Python 3.10"当作既定事实。当前状态是"主镜像 3.10、Runner 与本地开发 3.12、CI 不校验、生产宿主未知"。升级决策的前置条件是先把版本声明统一并在 CI 中锁定，否则"升不升 3.11"是个无法验证的问题。

## 3. 需要修正表述的三条

### 3.1 `AIConversation / Proposal / Receipt` 不是类

报告第 6.1 节把它们与 `CourseDocument`、`LearnerModel`、`CourseEvolutionPlan` 并列为领域对象，读者会去找同名符号，但仓库里**不存在名为 `AIConversation` 的符号**。

实际承载者：

- 存储：`backend/ai_teacher_state.py` 的 `AITeacherRepository`，内部按 `conversations / proposals / receipts / suppressions` 四个列表组织的 dict 记录。
- 语义：`backend/ai_teacher_actions.py` 的 `propose_action` / `execute_proposal` / `reject_proposal` / `undo_receipt`。

同段落中 `CourseEvolutionPlan` 是**真实的类**（`backend/course_evolution.py`，pydantic BaseModel），这条没问题。

> 建议修订为：明确区分"已建模为类的领域对象"和"以仓库 + 命令函数形式承载的协议记录"，避免读者按错误的粒度设计 Tool adapter。

### 3.2 报告第 9.4 节的四级工具权限——已有两级等价物，且是代码强制的

报告把 `read / draft / propose / commit` 四级权限当作需要新建的机制。实际上 `AIContextPackage v3` 已经有一个 `permissions` 块（`backend/ai_teacher_context.py`），承载了其中的 `propose` 与（反向的）`commit`：

- `allowed_proposals`：`create_note`、`create_issue`、`create_review_task`、`create_bookmark`、`open_runtime_action`
- `forbidden_actions`：`modify_mastery`、`modify_learner_profile`、`confirm_diagnostic`、`submit_student_answer`、`overwrite_course_content`

关键在于**这不只是写进 prompt 的君子协定**：`ai_teacher_actions.py` 在 `propose_action` 和 `execute_proposal` 两处都对 `ACTION_TYPES` 做白名单校验，越界抛 `ActionForbidden`。也就是说报告第 6.3 节"这些规则应继续是代码硬约束而不是 Skill 文本"的主张，在写入侧**已经落实**。

缺的是 `read` 与 `draft` 两级：今天的读取侧是一个**固定的预装配包**，没有可授予或拒绝的粒度，因此也没有分级的对象。

> 建议修订为：四级模型中 `propose`/`commit` 已存在且代码强制；真正的新增工作只在 `read`/`draft` 两级，而这两级的前提是先把读取侧从"固定预装配"改成"可请求的工具"。

### 3.3 「不能持久化并恢复长任务」——对 AI 老师成立，作为全局判断过强

报告第 6.2 节的这条对**AI 老师回合**仍然成立：今天没有回合级检查点，断线即结束该回合（`backend/routers/assistant.py` 的 `_persist_answer_turn` 只记录 completed/failed/cancelled 三种终态，不挂起）。

但灵知在**课程生成**链路上早已具备持久任务与恢复能力（`backend/task_manager.py`，含 `TaskRecoveryConflict`、检查点与部署后恢复），`docs/系统架构.md` 也把"任务可观察性与部署"列为稳定基座。

> 建议修订为：把这条限定到"AI 老师回合"，否则会让读者以为需要从零建设任务恢复设施，而实际上可复用的基座已经存在。

## 4. 仍然成立的关键结论（无需修订）

逐条核对后确认，报告以下判断今天依然准确：

| 报告结论 | 核对结果 |
| --- | --- |
| `AIQAService` 只把上下文渲染进 system prompt，然后调用一次 `_stream_llm`，无工具循环 | 仍然成立。`backend/ai_qa_service.py` 仍是单次流式调用；全 `backend/` 目录搜不到 `tools=` / `tool_choice` / `tool_calls`，`_stream_llm` 签名中也没有任何工具参数 |
| 不能先查课程知识再回答 | 仍然成立。知识切片由 `_knowledge_context()` 在调用前确定性装配（上限 16 节点 / 16 关系），模型无法索取更多 |
| 不能选择图解或代码执行 | 仍然成立。两者都存在（`routers/diagrams.py`、`routers/code_execution.py`）但只在独立端点，AI 老师问答链路不引用 |
| 不能生成练习后调用确定性校验 | 仍然成立。校验器存在（`assessment_validators.py`）但 AI 老师路径不引用 |
| 不能中途询问用户 | 仍然成立。问答链路没有 `ask_user` 机制 |
| 灵知没有 Agent Runtime / Tool Registry / Capability Registry / Skill Loader | 仍然成立。全仓（排除 `node_modules`）搜索这些概念，唯一命中就是报告本身；也没有任何 MCP 接入 |
| 前端没有 Agent trace / task card | 仍然成立。`stores/aiTeacher.ts` 只处理 context / answer / final_answer / sources / retrieval / proposal / error 等事件，没有 trace 或工具步骤事件；`CourseTaskCenter.vue` 是课程**生成**任务卡，不是 Agent 任务卡 |
| `CourseKnowledgeBase` 六类关系 | 仍然成立。`RELATION_TYPES` 恰为六项：`prerequisite`、`derives`、`equivalent_to`、`contrasts_with`、`applies_to`、`generalizes` |

## 5. 本附页之后又发生的变化

本附页核对期间，本线在 AI 老师上收束了三处缺口，会影响报告第 13 节 Phase 0 的通过门定义：

1. **统一回执**：确认与撤销的每一种终态（过期、已拒绝、运行时变化、执行失败、撤销目标被改动/缺失）现在都返回持久 `ActionReceipt`，带稳定 `result_code`。Phase 0 的"未授权写操作为 0"因此可以用回执审计直接测量，而不必依赖日志。
2. **模型异常分类**：provider 失败不再折叠成单一 `model_unavailable`，而是复用 `ai_base` 既有分类给出 8 个稳定 code 并区分是否可重试。Phase 0 若要比较"Agent 与当前一次性问答"的失败表现，现在有可比口径。
3. **流式取消**：取消或断线的回合会按学生**实际读到**的内容落库并标 `cancelled`，直接动作被打断不再留下 `presented` 半成品。这正对应报告 Phase 0 通过门里的"刷新和取消不会重复工具副作用"。

## 6. 未确定项

以下问题仓库内证据不足，需要线下确认后才能写进任何实施决策：

- 生产宿主机的实际 Python 版本（部署脚本使用宿主 `python3`，仓库不记录）。
- 报告引用的 DeepTutor `v1.5.2` 源码结论本轮**未复核**——本附页只核对报告对**灵知**的描述，不核对其对 DeepTutor 的描述。
- 报告第 5 节关于论文效果的结论本轮未复核。
