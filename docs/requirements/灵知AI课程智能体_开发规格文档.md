# 灵知 AI 课程智能体 — 开发规格文档（AI 可执行版）

> 本文档按本仓库既有的 OpenSpec 规范撰写（`Requirement` + `Scenario`，关键字用 MUST/SHALL/WHEN/THEN/AND），供 AI 编码 Agent（Claude Code 等）直接读取并据此规划任务、生成代码与自检。人类可读的背景资料见 `灵知AI课程智能体_开发需求文档.md`；两份文档配合使用，本文档是**验收基准**，背景文档是**动机与上下文**。

## 0. Agent 须知（先读）

- **你是谁**：本仓库（`hackthon`，前后端一体的 AI 课程生成/学习产品）的开发 Agent。技术栈见仓库根目录 `pyproject.toml`（后端 Python）、`frontend/`（前端）、`backend/`、`shared/`。开发/调试用 `dev.bat`（Windows）或 `dev.sh`。
- **唯一事实来源**：本文档中的 `Requirement`/`Scenario` 是验收标准，不是背景聊天记录里的原话。实现前先在 `openspec/changes/` 下创建对应变更目录（参照仓库已有的 `build-structured-adaptive-course-ai`、`fix-mermaid-rendering-pipeline` 等），按 `proposal.md → design.md → tasks.md → specs/*/spec.md` 顺序推进，不要跳过规划直接写代码。
- **不确定时怎么办**：本文档标注为 MUST 的条款不可自行放宽；标注为 SHOULD 的可根据代码库现状调整但需在 PR/commit 说明中注明理由；未覆盖的场景，优先复用 §5 中"参考实现"描述的既有模式（四步质量管线、JSON Schema 兜底等），不要发明新的架构风格。
- **完成定义（Definition of Done）**：一个 Requirement 被视为完成，当且仅当其下所有 Scenario 都有对应的自动化测试或可复现的手动验证步骤，且不引入 §6 中列出的已知反模式（硬编码密钥、无质检兜底、静默覆盖正式课程等）。

## 1. Why（为什么做这件事）

课程当前的生成方式是"多次独立生成大纲/正文/PPT"，缺乏统一语义源，导致同一课程的不同产物互相不一致；同时课程一旦生成即固定，无法依据学生的真实学习证据演化。这两点分别对应下文的**结构化同源**与**个体化生长**两条产品原则，是本轮开发要解决的核心问题。

## 2. What Changes（要交付什么）

### 新增能力（New Capabilities）

- `course-knowledge-structure`：课程作为带稳定节点标识的结构化树，大纲/正文/知识地图为同一课程源的投影。
- `learning-evidence-adaptation`：从学生学习证据到课程变更建议的判定链路。
- `pending-change-review`：AI 变更以"待确认"形式呈现，由学生审阅、接受/拒绝/重新生成。
- `generation-quality-guardrail`：课程生成结果的结构校验、截断提示、生成后质检与可追溯记录（参照 §5 审计结论落地）。

### 本轮不做（见 §6 Out of Scope）

## 3. 数据模型（Entities，供 Agent 设计 schema 时对齐命名）

```
SubjectKnowledgeLibrary   学科知识库（可复用，学科级）
  └─ CourseKnowledgeBase   课程知识库（建课时创建，可持续细化）
       └─ CourseKnowledgeMap   课程知识地图（知识节点 ↔ 章节/课程块 映射）

CourseDocument             已确认课程（正式版本）
  + PendingChangeOverlay    待确认 AI 变更层
  + AdaptiveBlock           可演化课程块（课程树的最小可寻址节点）
  + LearningRecord          学习记录（承载 EvidenceItem）

EvidenceItem → AdaptationHypothesis → CourseChangeSet → （学生确认）→ CourseDocument / KnowledgeBase
```

字段级设计留给实现阶段，但以下约束是 MUST：
- `AdaptiveBlock` 必须有稳定、跨重新生成保持不变的标识（node id），供大纲/正文/知识地图/PPT 互相引用。
- `CourseChangeSet` 必须能表达作用域（当前块 / 当前小节 / 多个小节 / 多个章节 / 全书）与来源证据引用。
- `PendingChangeOverlay` 中的条目必须可与 `CourseDocument` 中对应节点做 diff。

## 4. Requirements

### Requirement: 课程内容 MUST 保持结构化同源

课程的大纲、正文、知识地图，以及未来的 PPT，MUST 是同一课程源（以 `AdaptiveBlock` 节点树表达）的不同投影，禁止各产物各自独立生成互不关联的副本。

#### Scenario: 课程正文节点发生编辑
- **GIVEN** 一个已确认的 `CourseDocument` 中某个 `AdaptiveBlock` 的正文被修改
- **WHEN** 系统检测到该节点存在下游依赖节点（如后续章节引用了该节点定义的概念）
- **THEN** 系统 MUST 识别受影响的上游/下游/关联节点
- **AND** MUST 生成可审阅的联动变更（`CourseChangeSet`），而不是直接静默改动下游节点

#### Scenario: 大纲重新生成
- **WHEN** 用户触发大纲重新生成
- **THEN** 系统 MUST 复用既有 `AdaptiveBlock` 节点 id（若语义节点仍存在），不得为未变化的节点重新分配 id
- **AND** 已有的个体化生长内容（见下条）不得因大纲重生成而被静默丢弃

### Requirement: 学习证据 MUST 驱动个体化课程演化

系统 MUST 综合学生与 AI 的对话、追问、重解释行为、错题、笔记、理解检查和课程内输入，作为 `EvidenceItem`，用于判断学生当前理解状态并生成适配建议。

#### Scenario: 学生连续要求更详细解释
- **GIVEN** 学生在同一小节内连续两次以上要求"讲得更详细"或表现出重解释请求
- **WHEN** 证据聚合模块处理这些 `EvidenceItem`
- **THEN** 系统 MUST 生成 `AdaptationHypothesis`，判断该节点当前推导颗粒度偏粗
- **AND** 达到证据门槛后 MUST 生成 `CourseChangeSet`，内容包括对当前块的补充说明，以及对后续相关章节的预防性补充建议

#### Scenario: 证据门槛判定
- **GIVEN** 一条极强的单一证据（如学生明确点击"这段完全看不懂"并给出具体原因）
- **WHEN** 系统评估是否触发变更
- **THEN** 系统 MAY 立即触发变更，不要求达到"多次出现"的机械计数条件
- **GIVEN** 多条弱证据（如反复的短暂停留、多次快速跳过）
- **WHEN** 系统评估是否触发变更
- **THEN** 系统 MUST 结合强度、一致性、覆盖范围、时效性、可逆性和误判成本综合判断，不得仅以固定次数作为唯一触发条件

### Requirement: AI 变更 MUST 以待确认形式呈现，不得直接写入正式课程

AI 生成的任何课程级修改（增加、修改、替换、删除、移动、难度调整）MUST 先进入 `PendingChangeOverlay`，不能绕过学生确认直接覆盖 `CourseDocument`。

#### Scenario: AI 生成变更建议
- **WHEN** 系统基于证据生成 `CourseChangeSet`
- **THEN** 变更内容 MUST 在前端以高亮、差异标记和"AI 生成"标签呈现
- **AND** MUST 展示变更理由、使用的证据、影响范围（作用域）
- **AND** 在学生处理前 MUST 保持可见，不得因用户暂不处理而自动消失或静默应用

#### Scenario: 学生处理待确认变更
- **WHEN** 学生对某条待确认变更选择"接受"
- **THEN** 系统 MUST 将该变更写入正式 `CourseDocument`，并记录版本与来源证据
- **WHEN** 学生选择"拒绝"并可选填写理由
- **THEN** 系统 MUST 将拒绝行为与理由作为新的 `EvidenceItem` 回流，供后续证据判断使用
- **WHEN** 学生选择"重新生成"
- **THEN** 系统 MUST 基于原证据与用户补充意见重新生成该条 `CourseChangeSet`，不得复用完全相同的输出

### Requirement: 变更作用域 MUST 可控且显式

`CourseChangeSet` 的作用域 MUST 支持：当前块、当前小节、多个小节、多个章节、全书，且 MUST 在用户界面中显式呈现该次变更实际影响的范围。

#### Scenario: AI 提出跨章节预防性建议
- **WHEN** 系统判断某个概念的理解缺口会影响后续多个章节
- **THEN** 生成的 `CourseChangeSet` MUST 明确列出所有受影响章节/节点
- **AND** 学生 MUST 能够对该变更集中的不同节点分别接受或拒绝，而不是只能整体接受/拒绝

### Requirement: 个体化调整 MUST 限定在当前课程范围内

系统 MUST NOT 将单个学生在某门课程内的个性化调整自动传播到该学生的其他课程或教师端（启智）。

#### Scenario: 学生在课程 A 中产生个性化变更
- **WHEN** 变更被接受并写入课程 A 的 `CourseDocument`
- **THEN** 系统 MUST NOT 修改该学生在课程 B 中的内容
- **AND** MUST NOT 将该变更同步给教师端（启智），除非未来专门的联动能力被显式启用

### Requirement: 课程与知识库 MUST 支持双向联动提案

正文层面的变化 MUST 能够提出知识库层面的变化建议；知识库层面的变化 MUST 能够提出课程中受影响节点的联动变化建议。两者均遵循"待确认变更"规则（不得绕过审阅直接写入）。

#### Scenario: 正文修改触发知识库联动
- **WHEN** 学生接受了一条修改课程正文定义的变更
- **AND** 该定义在 `CourseKnowledgeBase` 中有对应知识节点
- **THEN** 系统 MUST 生成对知识库该节点的联动变更建议，而不是自动改写知识库

### Requirement: 课程生成 MUST 具备结构校验与生成后质检

参照 §5 审计中已验证有效、也已识别风险的实现模式，课程/教案/PPT 等生成产物 MUST 通过结构化 Schema 校验，且 MUST 有生成后的质量检查步骤，不得仅依赖"模型一次输出即为最终结果"。

#### Scenario: 生成结果解析失败
- **WHEN** 模型输出未通过 JSON Schema / 结构校验
- **THEN** 系统 MUST 将校验错误信息回传给模型进行受控重试（可降低采样温度），MUST NOT 静默丢弃错误直接展示给用户
- **AND** 重试仍失败时 MUST 触发对应粒度的兜底（如单页/单节点隔离失败，不拖垮整体生成），并向用户明确标注该部分未成功生成

#### Scenario: 输入内容超出单次上下文处理上限
- **WHEN** 参考资料或已有正文超出模型单次处理的字数/token 上限，需要截断
- **THEN** 系统 MUST 按章节/语义边界截断而非硬切字符数（若受限于既有实现只能硬切，MUST 在生成记录中显式标注截断范围）

#### Scenario: 生成记录可追溯
- **WHEN** 任意一次课程/正文/PPT 生成完成
- **THEN** 系统 MUST 记录所用的模型 ID、提示词模板版本（或 hash）、关键参数与截断信息，供事后复盘

### Requirement: 密钥与凭证 MUST NOT 硬编码在源码中

#### Scenario: 配置模型调用凭证
- **WHEN** 系统需要调用 LLM 服务的 API Key 或其他凭证
- **THEN** 凭证 MUST 从环境变量或密钥管理服务读取
- **AND** MUST NOT 出现在提交到 git 的源码文件中

## 5. 参考实现（现状基线，非强制照搬）

以下描述的是本项目"启智"（教师端）现有 dev 分支中一套已验证可运行的生成链路模式，供实现上述 Requirement 时参考，**不是灵知必须复用的架构**，但其中的质量管线思路（分析→初稿→核查→修订）与结构化约束（Schema 校验 + 兜底）值得借鉴：

- 大纲/教案采用四步质量管线：`analyze`（不产正文，只给写作策略，限 400 字）→ `outline/teaching_plan`（生成正文）→ `verify`（严格 JSON issues 输出的事实/引用/一致性核查）→ `refine`（仅按问题清单定稿）。
- PPT 生成分两阶段：`OUTLINE_PROMPT` 先产出页序 DeckPlan（JSON），再并发调用 `CONTENT_FILL_PROMPT`/`QA_FILL_PROMPT`/`SUMMARY_FILL_PROMPT` 逐页填充；最终由固定渲染器（HTML + python-pptx）而非模型直接产出文件，保证样式稳定。
- 所有结构化产物（DeckPlan、SlideFill、文档分析结果）用 Pydantic Schema 校验；解析失败时把校验错误追加进下一轮 user prompt 并降温重试；单页失败时该页返回空内容而不是让整个生成失败。
- 已识别但**尚未修复**的问题（灵知开发时必须规避，不要重犯）：
  - 默认密钥硬编码在 `agents/llm.py` 中 → 对应本文档"密钥与凭证"Requirement。
  - `verify.md` 明示"无联网检索能力"，事实核查只能做自洽性判断，不能验证外部真实性 → 若灵知需要面向学生呈现"事实校验"能力，MUST 在设计阶段就规划外部检索/来源链接，而非重复"自称核查、实为自洽"的模式。
  - PPT 用户的补充要求只拼进页序阶段的 prompt，逐页填充阶段感知不到 → 提醒：凡是"用户意图需要贯穿多阶段生成"的场景，都要显式把意图转成结构化 policy 逐层传递，而不是只在第一步拼接。
  - 教案输入按固定字符数（16,000/6,000）硬截断，未做语义分块 → 结构化同源的课程树天然可以按节点做语义级截断，灵知应优先使用这种方式而非重蹈固定字符截断。
  - 缺少生成后的可视化/内容质检（空页、重复标题、内容溢出）与专项自动化测试 → 对应本文档"生成后质检"与"可追溯"Requirement，属于本轮必须补齐项，不是可选项。

## 6. Out of Scope（本轮明确不做）

- 启智（教师端）与灵知（学生端）之间的自动联动、内容同步。
- PPT 与课程正文的双向联动编辑。
- 视频/动画讲解等多模态生成能力（仅做架构预留，不实现）。
- 将单个学生的个体化调整跨课程或跨用户传播。

以上四项 MUST NOT 在本轮实现中被排期，但设计时 SHOULD 预留扩展接口（如变更事件总线、统一节点 id 体系），避免未来接入时需要推倒重来。

## 7. 建议实施顺序（供拆解 tasks.md 使用）

1. 数据底座：`AdaptiveBlock` 节点树、版本、`EvidenceItem`/`CourseChangeSet`/`PendingChangeOverlay` 的存储模型与状态机。
2. 生成侧：课程/大纲/正文生成改造为写入统一节点树，接入 §4 的结构校验与生成后质检 Requirement。
3. 证据侧：`EvidenceItem` 采集（对话、追问、错题、理解检查等）与 `AdaptationHypothesis` 判定逻辑。
4. 变更侧：`CourseChangeSet` 生成、`PendingChangeOverlay` 前端展示（高亮/差异/AI标签）、接受/拒绝/重新生成交互。
5. 联动侧：课程 ↔ 知识库双向变更提案。
6. 端到端验证：走通 §8 最小演示闭环，作为该阶段的验收标准，而不是以"接口可调用"为完成标志。

## 8. 最小演示闭环（第一阶段验收目标）

```
学生在第二节连续要求更详细解释
→ 系统积累对话与重解释证据（EvidenceItem）
→ AI 判断当前课程的推导颗粒度偏粗（AdaptationHypothesis）
→ 生成变更：在当前块补充一段解释 + 对第三/四/五节提出预防性补充建议（CourseChangeSet）
→ 新增内容和行内修改均高亮并标记"AI 生成"（PendingChangeOverlay）
→ 学生查看理由与范围
→ 学生分别接受、拒绝或重新生成
→ 接受项写入正式课程（CourseDocument），拒绝原因回流为新证据（EvidenceItem）
```

该闭环覆盖了 §4 中除"课程↔知识库联动"外的全部 Requirement，是判断第一阶段是否可交付的唯一标准。

## 9. 变更记录

| 日期 | 说明 |
|---|---|
| 2026-07-15 | 由原始群聊记录、技术交接包、启智生成能力审计报告、产品截图四份资料整理为背景文档，再重构为本 OpenSpec 风格开发规格文档。 |
