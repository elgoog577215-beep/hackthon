# 需求文档：提示词工程优化

## 简介

Knowledge Map AI 的提示词系统（`backend/prompts.py`）当前存在两个核心问题：（1）测验生成对 STEM 学科质量低下——缺少计算题、推导题、LaTeX 公式要求，且题型分布固定不适配理工科需求；（2）课程内容结构"一刀切"——所有学科共用同一套 6 段式模板（💡🔍🛠️🎨🏭✅），未按学科类型差异化教学逻辑。此外，提示词信噪比低（嵌入全量配置而非当前配置）、学科类型在测验生成链路中丢失、学科检测逻辑存在歧义。本次优化旨在建立学科感知的提示词体系，使内容生成和测验生成均能根据学科类型（自然科学 / 人文学科 / 技能学科）产出结构化、高质量的输出。

## 术语表

- **Prompt_System**：`backend/prompts.py` 中的集中式提示词管理系统，包含所有 PromptTemplate 实例和共享组件
- **Quiz_Service**：`backend/ai_quiz_service.py` 中的 `AIQuizService` 类，负责测验题目生成、验证和回退逻辑
- **Course_Service**：`backend/ai_course_service.py` 中的 `AICoursService` 类，负责课程大纲、子节点和正文内容生成
- **Discipline_Detector**：`backend/ai_base.py` 中的 `_detect_discipline_type` 方法，基于关键词匹配识别学科类型
- **discipline_type**：学科类型枚举值，取值为 `natural_science`（自然科学）、`humanities`（人文学科）、`skill_based`（技能学科）
- **STRUCTURE_REQUIREMENTS**：`prompts.py` 中定义的 6 段式内容结构模板（💡🔍🛠️🎨🏭✅）
- **Fallback_Quiz**：`_generate_smart_fallback_quiz` 方法，当 LLM 调用失败时生成的模板化回退测验
- **DIFFICULTY_CONFIG**：提示词中嵌入的难度等级全量配置文本
- **STYLE_CONFIG**：提示词中嵌入的教学风格全量配置文本
- **Quiz_Router**：`backend/routers/quiz.py` 中的测验 API 路由
- **Node_Router**：`backend/routers/nodes.py` 中的节点操作 API 路由
- **Shared_Config**：`shared/prompt_config.py`（Python）和 `shared/prompt-config.ts`（TypeScript）中的共享枚举和验证规则

## 需求

### 需求 1：按学科类型差异化内容结构模板

**用户故事：** 作为学习者，我希望自然科学课程遵循"定义→定理→证明→例题→练习"的教学逻辑，人文课程遵循"语境→论证→多视角→批判→开放问题"的逻辑，技能课程遵循"概述→原理→示范→练习→评估"的逻辑，以便获得符合学科特性的结构化学习体验。

#### 验收标准

1. WHEN discipline_type 为 `natural_science` 时，THE Prompt_System SHALL 使用自然科学专用内容模板，包含以下必要板块：核心定义与物理意义、定理陈述与完整证明/推导、算法步骤/计算方法、可视化图解（Mermaid 图）、工程/科研应用案例、推导题/证明题形式的思考题
2. WHEN discipline_type 为 `humanities` 时，THE Prompt_System SHALL 使用人文学科专用内容模板，包含以下必要板块：概念定义与历史语境、论证链条展示（观点→论据→反驳→回应）、研究方法/分析框架、概念关系图、现实意义与当代关联、开放性问题/批判性思考题
3. WHEN discipline_type 为 `skill_based` 时，THE Prompt_System SHALL 使用技能学科专用内容模板，包含以下必要板块：技能定义与学习价值、技能背后的原理/机制、具体示范材料与练习任务、流程图/评分标准表、真实比赛/项目案例、实践任务/自我评估
4. THE Prompt_System SHALL 将当前的单一 STRUCTURE_REQUIREMENTS 替换为三个学科专用的结构模板，并在 `generate_content` 提示词组装时根据 discipline_type 参数选择对应模板
5. WHEN discipline_type 参数缺失或无法识别时，THE Prompt_System SHALL 回退使用 `natural_science` 模板作为默认值


### 需求 2：按学科类型差异化测验生成

**用户故事：** 作为学习者，我希望自然科学课程的测验包含计算题、推导题和公式应用题，人文课程的测验包含论述题和观点分析题，技能课程的测验包含实操评估题，以便测验能真正检验我对该学科知识的掌握程度。

#### 验收标准

1. THE Quiz_Service 的 `generate_quiz` 方法 SHALL 接受 `discipline_type` 参数，并将该参数传递给提示词模板
2. WHEN discipline_type 为 `natural_science` 时，THE Prompt_System SHALL 在测验提示词中要求：题型分布包含计算题和推导题（至少占比 30%）、选项中包含常见计算错误作为干扰项、题目和解析中使用 LaTeX 公式、解析包含分步骤求解过程
3. WHEN discipline_type 为 `humanities` 时，THE Prompt_System SHALL 在测验提示词中要求：题型分布侧重论述分析和观点辨析、选项涵盖不同学派/视角的观点、解析展示论证逻辑链条
4. WHEN discipline_type 为 `skill_based` 时，THE Prompt_System SHALL 在测验提示词中要求：题型分布侧重情境判断和实操步骤排序、选项基于真实操作场景、解析包含操作要点和评分标准
5. THE Prompt_System SHALL 将当前固定的题型分布（60% 选择 / 20% 判断 / 20% 简答）替换为按 discipline_type 动态调整的题型分布策略
6. WHEN discipline_type 参数缺失时，THE Quiz_Service SHALL 回退使用通用题型分布策略

### 需求 3：测验生成链路中传递学科类型

**用户故事：** 作为系统，我需要确保学科类型信息从课程创建阶段一直传递到测验生成阶段，以便测验内容与课程内容的学科特性保持一致。

#### 验收标准

1. THE `GenerateQuizRequest` 模型 SHALL 包含可选的 `discipline_type` 字段，类型为 `Optional[str]`，默认值为 `None`
2. WHEN Quiz_Router 收到测验生成请求时，THE Quiz_Router SHALL 将请求中的 `discipline_type` 参数传递给 Quiz_Service 的 `generate_quiz` 方法
3. WHEN Node_Router 收到节点测验生成请求时，THE Node_Router SHALL 将请求中的 `discipline_type` 参数传递给 Quiz_Service 的 `generate_quiz` 方法
4. WHEN `discipline_type` 参数为 `None` 时，THE Quiz_Service SHALL 保持当前行为不变，确保向后兼容

### 需求 4：提升提示词信噪比

**用户故事：** 作为系统，我需要减少发送给 LLM 的提示词中的冗余信息，以便降低 token 消耗、提高生成质量并减少 LLM 被无关信息干扰的概率。

#### 验收标准

1. THE Prompt_System SHALL 在组装提示词时仅嵌入当前请求对应的难度等级配置，而非全量 DIFFICULTY_CONFIG（包含所有三个等级的完整描述）
2. THE Prompt_System SHALL 在组装提示词时仅嵌入当前请求对应的教学风格配置，而非全量 STYLE_CONFIG（包含所有四种风格的完整描述）
3. THE Prompt_System SHALL 在组装提示词时仅嵌入当前请求对应的学科类型配置，而非全量 DISCIPLINE_TYPE_CONFIG（包含所有三种学科类型的完整描述）
4. THE Prompt_System SHALL 提供按参数值查询对应配置片段的函数（如 `get_difficulty_config(level)` → 仅返回该等级的配置文本）
5. THE Prompt_System SHALL 消除 `generate_content` 提示词中学科适配指令分散在多处（system_prompt 中的 DISCIPLINE_TYPE_CONFIG、正文中的"学科类型适配"段落）导致的重复和矛盾问题，将学科适配逻辑合并为单一权威来源

### 需求 5：改进学科类型检测逻辑

**用户故事：** 作为系统，我需要更准确地识别课程的学科类型，以便后续的内容生成和测验生成能选择正确的学科模板。

#### 验收标准

1. THE Discipline_Detector SHALL 处理跨学科关键词歧义问题——WHEN 课程名称同时匹配多个学科类型的关键词且得分差距小于等于 1 时，THE Discipline_Detector SHALL 使用加权评分机制（核心关键词权重高于边缘关键词）而非简单计数
2. THE Discipline_Detector SHALL 扩展关键词库，覆盖以下当前缺失的学科领域：生物学、地理学、天文学、医学（归入 natural_science）；经济学、法学、心理学、教育学（根据具体方向归入 humanities 或 skill_based）
3. IF 关键词匹配结果所有学科得分均为 0，THEN THE Discipline_Detector SHALL 返回 `natural_science` 作为默认值并记录警告日志
4. THE Discipline_Detector SHALL 支持英文关键词匹配（如 "machine learning"、"philosophy"、"debate"），以处理中英混合的课程名称

### 需求 6：改进回退测验质量

**用户故事：** 作为学习者，当 LLM 调用失败时，我仍然希望获得与当前学习内容相关的有意义的测验题目，而非千篇一律的模板化通用题目。

#### 验收标准

1. WHEN LLM 调用失败且 discipline_type 为 `natural_science` 时，THE Fallback_Quiz SHALL 生成包含基础概念辨析题和简单应用分析题的回退测验，题目文本中包含节点名称的具体学科术语
2. WHEN LLM 调用失败且 discipline_type 为 `humanities` 时，THE Fallback_Quiz SHALL 生成包含观点理解题和语境分析题的回退测验
3. WHEN LLM 调用失败且 discipline_type 为 `skill_based` 时，THE Fallback_Quiz SHALL 生成包含操作步骤排序题和情境判断题的回退测验
4. THE Fallback_Quiz SHALL 接受 `discipline_type` 参数，并根据该参数选择对应的回退题目模板集
5. THE Fallback_Quiz 的每个学科模板集 SHALL 包含至少 5 道不同类型的题目模板，确保在请求不同数量题目时有足够的题目池

### 需求 7：子节点生成的学科差异化

**用户故事：** 作为学习者，我希望课程的子章节结构也能反映学科特性——自然科学章节下的子节点应包含"定理证明"、"例题演练"类型的节点，人文章节下应包含"多视角论证"、"批判性讨论"类型的节点。

#### 验收标准

1. WHEN 生成 L2 子章节时，THE Course_Service SHALL 将 discipline_type 传递给 `generate_sub_nodes` 提示词
2. WHEN discipline_type 为 `natural_science` 时，THE Prompt_System SHALL 在子节点生成提示词中建议包含定理/公式推导、例题演练、实验/仿真类型的子节点
3. WHEN discipline_type 为 `humanities` 时，THE Prompt_System SHALL 在子节点生成提示词中建议包含思想流派对比、原典解读、批判性讨论类型的子节点
4. WHEN discipline_type 为 `skill_based` 时，THE Prompt_System SHALL 在子节点生成提示词中建议包含技能示范、分步练习、评估标准类型的子节点

### 需求 8：共享配置同步更新

**用户故事：** 作为开发者，我需要确保前后端共享配置保持同步，以便前端能正确传递新增的 discipline_type 参数并展示相关 UI。

#### 验收标准

1. WHEN `shared/prompt_config.py` 新增 discipline_type 相关枚举或常量时，THE Shared_Config SHALL 同步更新 `shared/prompt-config.ts` 中的对应定义
2. THE Shared_Config SHALL 新增 `DisciplineType` 枚举（或等效常量），包含 `natural_science`、`humanities`、`skill_based` 三个值
3. THE Shared_Config SHALL 新增 `VALID_DISCIPLINE_TYPES` 验证列表和 `validate_discipline_type` 验证函数
4. WHEN 提示词版本号因本次优化而变更时，THE Shared_Config SHALL 同步更新 `PROMPT_VERSIONS` 中对应模板的版本号
