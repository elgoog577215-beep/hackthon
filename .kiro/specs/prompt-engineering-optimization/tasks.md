# 实施计划：提示词工程优化

## 概述

将当前"一刀切"的提示词体系重构为学科感知（discipline-aware）的分层架构。按照数据流方向实施：共享配置 → 提示词模板 → 服务层 → API/路由层 → 测试，确保每一步都可增量验证。

## Tasks

- [x] 1. 共享配置层：新增 DisciplineType 枚举和验证函数
  - [x] 1.1 在 `shared/prompt_config.py` 中新增 `DisciplineType` 枚举（`natural_science`、`humanities`、`skill_based`）、`VALID_DISCIPLINE_TYPES` 列表和 `validate_discipline_type()` 函数
    - 在枚举类型定义区域新增 `DisciplineType(str, Enum)` 类
    - 新增 `VALID_DISCIPLINE_TYPES: List[str]` 常量
    - 新增 `validate_discipline_type(discipline_type: str) -> bool` 验证函数
    - 更新 `__all__` 导出列表
    - _Requirements: 8.2, 8.3_

  - [x] 1.2 在 `shared/prompt-config.ts` 中同步新增 `DisciplineType` 枚举、`VALID_DISCIPLINE_TYPES` 数组和 `validateDisciplineType()` 函数
    - 新增 `DisciplineType` 常量对象和类型
    - 新增 `VALID_DISCIPLINE_TYPES: string[]` 数组
    - 新增 `validateDisciplineType(disciplineType: string): boolean` 函数
    - 更新 `GenerateQuizParams` 接口，新增可选 `discipline_type` 字段
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 1.3 将 `shared/prompt-config.ts` 的变更同步到 `frontend/src/shared/prompt-config.ts`
    - 确保前端副本与根目录 `shared/` 完全一致
    - _Requirements: 8.1_

  - [ ]* 1.4 编写属性测试：前后端共享配置一致性（Property 5）
    - **Property 5: 前后端共享配置一致性**
    - 在 `frontend/src/__tests__/shared/prompt-config.test.ts` 中新增测试，验证 `VALID_DISCIPLINE_TYPES` 包含 `["natural_science", "humanities", "skill_based"]`
    - **Validates: Requirements 8.1**

  - [ ]* 1.5 编写属性测试：学科类型验证函数正确性（Property 6）
    - **Property 6: 学科类型验证函数正确性**
    - 在 `tests/test_prompt_properties.py` 中用 `hypothesis` 生成随机字符串，验证 `validate_discipline_type(s)` 返回 `True` 当且仅当 `s ∈ ["natural_science", "humanities", "skill_based"]`
    - 在 `frontend/src/__tests__/shared/prompt-config.test.ts` 中用 `fast-check` 做同样验证
    - **Validates: Requirements 8.3**

- [x] 2. 提示词模板层：学科差异化内容结构和测验配置
  - [x] 2.1 在 `backend/prompts.py` 中新增三套学科专用内容结构模板
    - 新增 `STRUCTURE_NATURAL_SCIENCE`、`STRUCTURE_HUMANITIES`、`STRUCTURE_SKILL_BASED` 常量
    - 自然科学模板包含：核心定义与物理意义、定理陈述与完整证明/推导、算法步骤/计算方法、可视化图解、工程/科研应用案例、推导题/证明题
    - 人文学科模板包含：概念定义与历史语境、论证链条展示、研究方法/分析框架、概念关系图、现实意义与当代关联、开放性问题/批判性思考题
    - 技能学科模板包含：技能定义与学习价值、技能背后的原理/机制、具体示范材料与练习任务、流程图/评分标准表、真实比赛/项目案例、实践任务/自我评估
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 2.2 在 `backend/prompts.py` 中新增三套学科专用测验配置
    - 新增 `QUIZ_CONFIG_NATURAL_SCIENCE`、`QUIZ_CONFIG_HUMANITIES`、`QUIZ_CONFIG_SKILL_BASED` 常量
    - 自然科学：计算/推导题 ≥ 30%，LaTeX 公式，分步骤求解
    - 人文学科：论述分析 40%，观点辨析 30%，语境理解 30%
    - 技能学科：情境判断 40%，实操步骤排序 30%，概念理解 30%
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [x] 2.3 在 `backend/prompts.py` 中新增子节点学科建议模板
    - 新增 `SUBNODE_HINTS_NATURAL_SCIENCE`、`SUBNODE_HINTS_HUMANITIES`、`SUBNODE_HINTS_SKILL_BASED` 常量
    - 自然科学建议：定理/公式推导、例题演练、实验/仿真
    - 人文学科建议：思想流派对比、原典解读、批判性讨论
    - 技能学科建议：技能示范、分步练习、评估标准
    - _Requirements: 7.2, 7.3, 7.4_

  - [x] 2.4 在 `backend/prompts.py` 中新增配置查询函数
    - 实现 `get_difficulty_config(level: str) -> str`：按难度等级返回对应配置片段
    - 实现 `get_style_config(style: str) -> str`：按教学风格返回对应配置片段
    - 实现 `get_discipline_structure(discipline_type: str) -> str`：按学科类型返回对应内容结构模板，无效值回退 `STRUCTURE_NATURAL_SCIENCE`
    - 实现 `get_quiz_discipline_config(discipline_type: str) -> str`：按学科类型返回对应测验配置，无效值回退通用配置
    - 实现 `get_subnode_discipline_hints(discipline_type: str) -> str`：按学科类型返回子节点建议，无效值返回空字符串
    - _Requirements: 1.4, 1.5, 4.4_

  - [ ]* 2.5 编写属性测试：学科配置函数返回学科专属内容（Property 1）
    - **Property 1: 学科配置函数返回学科专属内容**
    - 在 `tests/test_prompt_properties.py` 中验证：对任意两个不同的 discipline_type 值，`get_discipline_structure` 和 `get_quiz_discipline_config` 返回不同的字符串
    - **Validates: Requirements 1.4, 2.5**

  - [ ]* 2.6 编写属性测试：配置查询函数仅返回当前值的配置片段（Property 2）
    - **Property 2: 配置查询函数仅返回当前值的配置片段**
    - 在 `tests/test_prompt_properties.py` 中用 `hypothesis` 验证：`get_difficulty_config(level)` 返回的文本包含该等级标识关键词且不包含其他等级的标识关键词；`get_style_config(style)` 同理；`get_discipline_structure(type)` 仅包含该学科类型的板块标题
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 3. 提示词组装层：将配置查询函数集成到提示词模板
  - [x] 3.1 修改 `backend/prompts.py` 中 `generate_content` 相关提示词模板，使用 `get_discipline_structure(discipline_type)` 替换硬编码的 `STRUCTURE_REQUIREMENTS`
    - 将学科适配逻辑合并为单一权威来源，消除 system_prompt 和正文中的重复
    - _Requirements: 1.4, 4.5_

  - [x] 3.2 修改 `backend/prompts.py` 中 `generate_quiz` 相关提示词模板，使用 `get_quiz_discipline_config(discipline_type)` 替换固定题型分布
    - _Requirements: 2.5_

  - [x] 3.3 修改 `backend/prompts.py` 中提示词组装逻辑，使用 `get_difficulty_config(level)` 和 `get_style_config(style)` 替换全量配置嵌入
    - 确保提示词中仅包含当前请求对应的难度和风格配置
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 3.4 修改 `backend/prompts.py` 中 `generate_sub_nodes` 相关提示词模板，使用 `get_subnode_discipline_hints(discipline_type)` 注入学科建议
    - _Requirements: 7.1_

- [x] 4. Checkpoint - 确保提示词模板层变更正确
  - 确保所有测试通过，ask the user if questions arise.

- [x] 5. 服务层：学科检测改进和 Quiz/Course 服务适配
  - [x] 5.1 改进 `backend/ai_base.py` 中 `_detect_discipline_type` 方法
    - 实现加权评分机制：核心关键词权重=2，普通关键词权重=1
    - 扩展关键词库：新增生物学、地理学、天文学、医学（natural_science）；经济学、法学、心理学、教育学（按方向归类）
    - 新增英文关键词支持（machine learning、philosophy、debate 等）
    - 得分差距 ≤ 1 时使用加权评分决定
    - 所有学科得分均为 0 时返回 `natural_science` 并记录 `logger.warning`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 5.2 编写属性测试：加权评分机制中核心关键词优先（Property 3）
    - **Property 3: 加权评分机制中核心关键词优先**
    - 在 `tests/test_prompt_properties.py` 中用 `hypothesis` 生成包含核心/普通关键词组合的课程名称，验证核心关键词（权重=2）优先于普通关键词（权重=1）
    - **Validates: Requirements 5.1**

  - [x] 5.3 修改 `backend/ai_quiz_service.py` 中 `AIQuizService.generate_quiz` 方法，新增 `discipline_type` 参数
    - 将 `discipline_type` 传递给提示词模板组装
    - 当 `discipline_type` 为 `None` 时保持当前行为不变
    - _Requirements: 2.1, 3.4_

  - [x] 5.4 修改 `backend/ai_quiz_service.py` 中 `_generate_smart_fallback_quiz` 方法，新增 `discipline_type` 参数
    - 为每种学科类型创建至少 5 道不同类型的回退题目模板
    - 自然科学：概念辨析题 ×2 + 简单应用分析题 ×2 + 基础计算/推理题 ×1
    - 人文学科：观点理解题 ×2 + 语境分析题 ×2 + 论证评价题 ×1
    - 技能学科：操作步骤排序题 ×2 + 情境判断题 ×2 + 评估标准题 ×1
    - `discipline_type` 为 `None` 时使用当前通用回退模板
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 5.5 编写属性测试：回退测验题目池充足性（Property 4）
    - **Property 4: 回退测验题目池充足性**
    - 在 `tests/test_prompt_properties.py` 中验证：对任意有效 discipline_type，`_generate_smart_fallback_quiz(node_name, question_count=5, discipline_type=type)` 返回恰好 5 道题目，且至少包含 2 种不同题型
    - **Validates: Requirements 6.5**

  - [x] 5.6 修改 `backend/ai_course_service.py` 中 `generate_sub_nodes` 方法，传递 `discipline_type` 给提示词
    - 在方法中调用 `_detect_discipline_type` 获取学科类型
    - 将 `discipline_type` 传递给子节点生成提示词模板
    - _Requirements: 7.1_

  - [x] 5.7 修改 `backend/ai_course_service.py` 中 `generate_node_content` 方法，传递 `discipline_type` 给提示词
    - 在方法中调用 `_detect_discipline_type` 获取学科类型
    - 将 `discipline_type` 传递给内容生成提示词模板
    - _Requirements: 1.4_

- [x] 6. API/路由层：传递 discipline_type 参数
  - [x] 6.1 修改 `backend/models.py` 中 `GenerateQuizRequest` 模型，新增 `discipline_type: Optional[str] = None` 字段
    - _Requirements: 3.1_

  - [x] 6.2 修改 `backend/routers/quiz.py` 中 `generate_quiz` 路由，将 `req.discipline_type` 传递给 `ai_service.generate_quiz`
    - 同时传递 `req.node_name` 参数（当前路由缺失此参数传递）
    - _Requirements: 3.2_

  - [x] 6.3 修改 `backend/routers/nodes.py` 中 `generate_node_quiz` 路由，将 `req.discipline_type` 传递给 `ai_service.generate_quiz`
    - _Requirements: 3.3_

- [x] 7. 共享配置版本号更新
  - [x] 7.1 更新 `shared/prompt_config.py` 和 `shared/prompt-config.ts` 中 `PROMPT_VERSIONS` 的版本号
    - 更新 `generate_content`、`generate_quiz`、`generate_sub_nodes` 的版本号
    - 同步更新 `frontend/src/shared/prompt-config.ts`
    - _Requirements: 8.4_

- [x] 8. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- 标记 `*` 的任务为可选测试任务，可跳过以加速 MVP
- 每个任务引用了具体的需求编号以确保可追溯性
- 属性测试验证设计文档中定义的 6 个正确性属性
- 实施顺序遵循数据流方向：共享配置 → 提示词模板 → 服务层 → API 层，确保每步可增量验证
