# 多模态课程生成全景调研与灵知融合方案

> 日期：2026-07-15
> 面向对象：灵知产品、算法、后端、前端与技术负责人
> 文档性质：市场调研、产品判断、技术架构与实施路线的统一交接稿
> 前置材料：[`AI 教育产品与开源项目全景调研`](ai-education-landscape-and-integration-2026-07-14.md)、[`灵知产品蓝图`](../product-blueprint.md)、[`灵知 AI 课程智能体需求文档`](../requirements/灵知AI课程智能体需求文档.md)

---

## 0. 执行摘要：灵知不应成为“能生成很多媒体的软件”，而应成为“会选择并编译教学表达的课程系统”

这次调研后的核心判断可以压缩成一句话：

> **同一门结构化课程，应能从同一语义真源生长出文本、图解、幻灯、讲解音频、教学动画、交互模拟、练习与对话等多种教学表达；这些表达不是彼此孤立的文件，而是可追溯、可替换、可验证、会随学生证据共同演化的课程投影。**

因此，灵知要建立的不是一个“图片生成 + 视频生成 + PPT 生成 + 配音”的工具集合，而是一套**多模态教学表达编译器**：

```text
课程语义真源
CourseDocument + CourseKnowledgeMap + LearningObjective + EvidenceUnit
        ↓
教学意图与表达规划
这个知识为什么需要另一种表达、面向谁、解决什么困难、怎样验证有效
        ↓
结构化中间产物
Storyboard / SceneSpec / NarrationSpec / InteractionSpec / AssessmentSpec
        ↓
渲染器与模型提供方
图表、白板、动画、音频、幻灯、模拟、视频、数字人
        ↓
多模态质量门
语义一致、教学完整、公式正确、节奏清楚、可访问、可追溯、成本可控
        ↓
RepresentationSet
挂回原 CourseBlock，而不是另造第二门课程
        ↓
学习运行时依据当前任务和学生证据选择、组合或生成
        ↓
LearningEvent / PracticeAttempt / Feedback 反向评价表达效果
```

这条路线比“接入最强的视频模型”更难，也更有产品壁垒。模型能力会快速商品化，而以下三点不会自动由模型提供：

1. **同源性**：一处知识、目标或例子变化后，哪些文本、图、PPT、动画、题目和字幕必须失效或更新，系统能够确定性地知道。
2. **教学性**：系统不是问“能不能生成视频”，而是问“这个知识障碍最适合用哪种表达，怎样设计节奏和交互，生成后是否真的帮助理解”。
3. **成长性**：不是给每个人永久贴上“视觉型/听觉型”标签，而是依据当前课程、当前目标、当前证据动态选择表达，并用后续证据检验这次选择是否有效。

### 0.1 对灵知现阶段最重要的四项决定

| 决定 | 应该怎么做 | 明确不要怎么做 |
| --- | --- | --- |
| 产品定义 | 定义为“会生长的多模态课程”，强调同一课程的多种教学表达 | 定义为一站式 AIGC 媒体工具箱 |
| 数据结构 | `CourseBlock` 继续是语义与顺序真源，新增可挂载多种表达的 `RepresentationSet` | 为 PPT、视频、音频分别复制课程树和正文 |
| 生成策略 | 先规划教学意图，再生成结构化中间产物，最后按需渲染 | 把整章文本直接扔给视频模型，希望一次成片 |
| 个体化策略 | 依据知识类型、教学作用、任务和证据选择表达 | 用固定“学习风格”标签决定学生只能看某种模态 |

### 0.2 竞争位置：灵知真正可以占据的空位

市场上已经出现了四类能力，但大多只覆盖其中一段：

- NotebookLM、Oboe 擅长把已有资料快速变成多种学习产物。
- Learn Your Way 展示了“同一个个性化文本底座派生多种表达”的研究范式。
- Mindsmith、Articulate Rise、Coursebox 擅长课程制作、发布和企业培训工作流。
- OpenMAIC 展示了由场景、角色、白板动作和交互组件构成的可执行 AI 课堂。

灵知的机会不在复制某一家的表面功能，而在把它们没有贯通的部分贯通起来：

> **课程结构真源 → 多模态表达 → 学习现场 → 证据 → 可确认课程生长。**

这也是灵知已有资产最有价值的地方。当前的 `CourseDocument / CourseBlock`、统一知识库、课程知识映射、学习目标、正式练习、学习事件、学习者模型、块级 AI、候选变更与确认机制，不是前期负担，而是让多模态真正成为“课程能力”而非“文件生成”的底座。

---

## 1. 研究边界与判断框架

### 1.1 本次研究回答的不是“有哪些视频模型”，而是六个产品问题

1. 课程里哪些内容值得转成图片、图解、PPT、音频、动画、模拟、视频或数字人？
2. 各模态的生成成熟度、成本、可编辑性和教学风险分别如何？
3. 市场上哪些产品已经把多模态做成原生课程，而不是附件？
4. 哪些开源项目值得直接移植，哪些只适合吸收架构思想？
5. 闭源产品的哪些体验、工作流和商业判断值得借鉴？
6. 灵知如何让已有的每一份课程资产产生多次价值，而不是重复生成、重复存储？

### 1.2 三个容易混淆的概念

#### 多媒体课程

课程里有文字、图片、音频和视频，但它们可能互不关联，往往只是教师上传的附件。这是“媒体共存”。

#### 多模态生成

系统能从提示词或资料生成多种媒体。它解决的是生产效率，但不必然理解课程结构，也不必然知道各种产物之间的关系。

#### 原生多模态课程

同一个知识目标可以用多种教学表达呈现；表达拥有共同语义来源、稳定绑定、适用条件、质量信息和效果证据。修改语义后依赖项会失效，学习运行时也能依据任务和证据选择表达。这才是灵知的目标。

### 1.3 本报告采用的八个评价维度

| 维度 | 核心问题 |
| --- | --- |
| 教学适配 | 是否知道为什么用该模态，而不只是能生成 |
| 同源与可追溯 | 是否能追到课程块、知识、目标和资料证据 |
| 可编辑性 | 修改是否作用于结构化内容，而非只能重做整段文件 |
| 双向联动 | 媒体中的语义修改能否安全回流课程真源 |
| 个体化 | 是否能依据学生证据动态选择或调整表达 |
| 质量与评测 | 是否检查知识、公式、节奏、可读性和教学效果 |
| 工程与成本 | 是否支持任务、缓存、重试、降级、版本和提供方替换 |
| 开放与合规 | 开源许可、素材来源、隐私、版权和无障碍是否可控 |

---

## 2. 各模态的市场成熟度：生成能力已经很多，教学可靠性远未统一

### 2.1 总体能力矩阵

| 教学表达 | 当前成熟度 | 最适合的知识任务 | 主要技术路线 | 最大风险 | 灵知建议优先级 |
| --- | --- | --- | --- | --- | --- |
| 结构化文本、公式、代码 | 高 | 定义、推导、论证、步骤、代码解释 | LLM + 结构化 schema + Markdown/LaTeX | 幻觉、证据漂移、结构不稳定 | P0，现有真源继续加强 |
| 思维导图、流程图、关系图 | 高 | 知识结构、过程、依赖、比较 | Mermaid、Excalidraw、Graph/ECharts | 图形正确但教学关系错误 | P0，最先补齐 |
| 数据图表 | 高 | 数量关系、趋势、分布、函数 | Vega-Lite、ECharts、Python/JS | 数据与坐标误读、视觉误导 | P0 |
| 幻灯片 / narrated slides | 中高 | 章节导学、复习、课堂演示、故事化讲解 | 结构化 slide schema + PPTX/HTML + TTS | 只生成漂亮页面、内容断裂 | P1 |
| 音频讲解 / podcast | 中高 | 复习、语言、叙事、概念对谈 | TTS、多角色脚本、时间轴 | 难以回看公式与空间关系 | P1 |
| 白板动画 / 代码动画 | 中 | 推导、算法、几何、物理过程 | Manim、Motion Canvas、SVG/Canvas | 代码失败、节奏差、公式错误 | P1-P2 |
| 交互模拟 / 可操纵图形 | 中 | 因果、参数、空间、实验、系统行为 | HTML/JS、Three.js、H5P、沙箱组件 | 交互热闹但没有学习目标 | P2，高价值 |
| 生成式视频 | 中低（视觉高、教学低） | 情境引入、难以拍摄的宏观/微观场景 | 视频生成模型 + 后期编排 | 事实、数量、符号和连续性错误 | P3，严格限域 |
| 数字人讲解 | 中 | 导学、语言练习、标准化培训 | Avatar API + TTS + 字幕 | “像老师”不等于教得更好 | P3，可选外观层 |
| 分支情境 / AI 角色扮演 | 中高 | 沟通、历史决策、医疗/商业案例、语言 | 状态机 + LLM 角色 + rubric | 角色漂移、结果不可复验 | P2 |
| VR/3D 沉浸场景 | 中低 | 空间结构、实验、安全训练 | Three.js/WebXR/游戏引擎 | 成本高、设备门槛、易炫技 | P4，专项而非默认 |

### 2.2 最重要的路线判断：教育中的“可控结构化生成”应优先于“像素级自由生成”

对精确知识，模态生成应遵循以下优先序：

```text
确定性排版与图形
> 可检查的结构化图表/场景
> 可执行代码动画
> 有来源的检索素材
> 自由生成图片/视频
```

原因不是保守，而是教学内容的失败模式与普通创意内容不同：一条箭头方向、一个符号、一个物体数量或一个先后顺序错误，就可能使整段讲解失效。2026 年的 [EduVideoBench](https://arxiv.org/abs/2605.26918) 指出，前沿视频模型在课堂可用性上仍存在明显差距；[PhyEduVideo](https://arxiv.org/abs/2601.00943) 也显示，模型可以生成连贯、流畅的物理教学视频，却仍会在概念准确性上失手，尤其是电磁学和热力学。针对早期算术的[方程到视觉评测](https://arxiv.org/abs/2605.31212)进一步显示，模型甚至会在对象数量和关系上失败。

因此：

- “什么是城市热岛效应”的情境引入，可以用生成式短视频。
- “三个苹果减去一个苹果”的数量表达，不应优先用自由视频生成。
- “矩阵变换如何扭曲平面”，应优先用可操纵坐标与结构化动画。
- “高斯消元每一步为何成立”，应优先用公式状态机与逐步高亮。

### 2.3 多模态不是越多越好

多媒体学习研究长期强调一致性、信号提示、空间邻近、时间邻近、分段和去冗余等原则，而不是“文字、画面、声音一起上”。可参考 Cambridge Handbook 中关于[多媒体学习原则的综述](https://doi.org/10.1017/CBO9781139547369.015)。

对灵知而言，这意味着：

- 图片必须解释正文难以表达的空间或关系信息，否则只是装饰。
- 旁白不应逐字朗读屏幕上的长段文字。
- 动画应允许暂停、分步和回看关键状态。
- 交互必须对应一个可说明的认知动作，例如预测、比较、操纵、解释或验证。
- 每种高成本表达都必须有低成本、可访问的替代版本。

### 2.4 不采用固定“学习风格”标签

“视觉型、听觉型、动觉型学生应该分别接受对应媒体”的匹配假说缺乏可靠证据，经典综述见 Pashler 等人的[Learning Styles: Concepts and Evidence](https://doi.org/10.1111/j.1539-6053.2009.01038.x)。灵知可以记录“某学生在某类任务、某种表达下的理解效果”，但不能把它固化为人格标签。

正确的选择函数应是：

```text
知识形态
+ 当前 CourseBlock 的教学 role
+ 当前学习目标
+ 学习者在本课程的证据
+ 设备、时间与无障碍约束
+ 表达质量、成本与延迟
→ 本次最合适的表达组合
```

---

## 3. 原生多模态课程产品：市场已验证什么，尚未解决什么

### 3.1 产品分层总览

| 产品 / 项目 | 原生能力 | 最值得学 | 主要缺口 | 对灵知的意义 |
| --- | --- | --- | --- | --- |
| Google Learn Your Way | 个性化教材、沉浸文本、测验、讲解幻灯、音频、思维导图 | 同一个性化文本底座派生所有表示 | 研究原型，长期学习与课程演化未验证 | “同源派生”最强参照 |
| Google NotebookLM | 基于资料生成音频、视频、幻灯、导图、信息图、测验、卡片 | 资料有据、Artifact Studio 心智简单 | 产物关系弱，修订能力仍受限 | 学习产物入口与按需生成参照 |
| Oboe | 目标生成课程，正文内自动嵌入 podcast、图、代码、测验 | 让媒体在需要的位置出现 | 课程长期真源、证据闭环不透明 | “上下文内嵌表达”参照 |
| Coursebox | prompt/文档到课程、视频、分支、图解、AI tutor | 快速商业化与多语言交付 | 复杂结构与个体课程生长不突出 | 一键出课和交付链参照 |
| Mindsmith | storyboard、30+ 内容块、互动、动画、模拟、AI 对话 | 专业课程制作块与预览工作流 | 更偏作者工具，学生个体课程演化弱 | 表达块库和编辑器参照 |
| Articulate Rise | 响应式块课程、AI 初稿、测验、旁白、LMS | 成熟的人机协同创作与企业生态 | AI 原生同源和个体生长有限 | 发布、无障碍与作者控制参照 |
| Sana | 文件生成课程、卡片、图片、目标；自适应挑战和复习 | 接受/丢弃 AI 产物，自适应运行 | 多模态深度和开放性有限 | 审核手势和适应层参照 |
| OpenMAIC | 角色、场景、幻灯、白板、对话、测验、模拟、PBL | 把课程变成可执行课堂场景 | 不是学生长期学习事实系统 | 场景 DSL 与播放器优先移植对象 |
| ClassBuild | 章节、阅读、PPTX、测验、音频、图解、SCORM | 完整资产计划和批量导出 | 平行产物字段多，幻灯偏图片化 | 资产规划与失效检测参照 |

### 3.2 Google Learn Your Way：目前最接近“同源多模态教材”的范式

Google Research 的 [Learn Your Way](https://research.google/blog/learn-your-way-reimagining-textbooks-with-generative-ai/) 从 PDF 教材出发，先按年级重新调整内容，再依据学生兴趣个性化例子；这个个性化文本成为沉浸式正文、测验、讲解幻灯、对谈音频和思维导图的共同底座。论文见 [arXiv:2509.13348](https://arxiv.org/abs/2509.13348)。

它最值得灵知吸收的不是“五种产物”，而是三层方法：

1. **先建立个性化语义底座，再派生其他表示。** 这样不同模态至少从同一内容出发，不会各自提示、各自发挥。
2. **不同模态需要不同生成架构。** 思维导图可以由模型直接生成；讲解幻灯需要多 Agent 与工具配合；教育插图甚至需要专门微调模型。不能指望一个万能 prompt 解决所有模态。
3. **评测必须落到学习结果。** 其随机对照实验包含 60 名 15–18 岁学生、单一主题、约 40 分钟学习；即时测验提升约 9%，3–5 天后保留率约为 78% 对 67%。这是积极信号，但样本、主题和时间都很有限，不能外推成“多模态一定提升所有学习”。

灵知可以进一步超越它：Learn Your Way 的重点仍是一次性教材再表达；灵知已有学习事件、正式作答、诊断和课程候选机制，可以让后续证据继续改变表达选择和课程结构。

### 3.3 NotebookLM：最成熟的“资料到学习产物”入口，但也是同源编辑的反例

[NotebookLM](https://support.google.com/notebooklm/answer/16296687) 已把 Audio Overview、Video Overview、Flashcards/Quizzes、Mind Maps、Infographics 和 Slide Decks 放进同一 Studio。它证明了一个非常强的用户心智：

> 用户不必理解媒体模型，只需围绕一组可信资料，选择自己当前需要的学习产物。

对灵知可借鉴：

- 在课程块或章节上提供“生成另一种讲法”，而不是单独建立视频工厂。
- 所有产物默认带来源范围，用户知道它基于哪些资料和课程位置。
- 高成本产物按需生成，不在创建课程时一次性全部生成。

但 NotebookLM 的 [Slide Deck 修订说明](https://support.google.com/notebooklm/answer/16757456?hl=en) 也暴露了灵知必须解决的问题：修订可以改文字、布局和视觉，但修订时暂不做来源核验，而且不能增删幻灯片。这说明“能修改结果”不等于“结果与语义真源双向联动”。灵知需要把编辑分成两类：

- 颜色、布局、镜头、语速等表现修改，只作用于某个表示。
- 事实、例子含义、知识顺序和目标修改，必须转为课程 `ChangeOperation` 候选，确认后使依赖产物失效或重编译。

### 3.4 Oboe：媒体不应集中在一个 Studio，而应出现在需要它的正文位置

[Oboe](https://oboe.com/blog/introducing-the-all-new-oboe) 从学习目标生成章节，支持文本和 podcast，并根据上下文自动嵌入测验、卡片、STEM 图形和代码。它自己的[产品学习课程](https://oboe.com/learn/landing-a-job-at-oboe-ehcsrx)还展示了按需生成 podcast、diagram、flashcard，以及通过追问在当前位置形成新 section 的方式。

这一点与灵知现有“块级 AI 在正文现场工作”的方向高度一致：多模态不应首先表现为首页上的一排生成按钮，而应在具体 `CourseBlock` 附近出现，例如：

- 对推导块：生成逐步动画、可操纵公式或讲解幻灯。
- 对定义块：生成概念图、反例图或口语解释。
- 对案例块：生成情境分支、角色对话或短视频引入。
- 对知识图：生成可交互先修路径和复习路线。

### 3.5 专业课件平台：成熟之处不在“AI”，而在人机协同和交付纪律

[Mindsmith](https://www.mindsmith.ai/) 及其 [Lesson Editor](https://help.mindsmith.ai/en/articles/12037477-the-lesson-editor) 提供 storyboard、30 多种 tile、动画视频、分支、模拟、AI 对话、旁白、SCORM/xAPI 和分析；[Articulate Rise](https://www.articulate.com/360/rise/) 提供响应式块、AI 课程初稿、知识检查、旁白和成熟 LMS 交付；[Coursebox](https://www.coursebox.ai/) 则强调从 prompt 或文档快速得到课程，并自动混合测验、视频、分支、图解和 AI tutor。

这些平台对灵知的启发是：

- 真正进入教学场景的多模态必须可预览、可替换、可发布、可降级，而不是只展示生成成功。
- 每种块都要有移动端、可访问性、导出和失败状态。
- AI 先生成结构化草稿，人在关键节点审核，通常比端到端黑箱更可靠。
- 企业平台擅长“教师制作后给很多人用”；灵知应保留其交付纪律，但把优势放到“同一学生的课程会继续长”。

### 3.6 Sana：AI 改动的接受/丢弃手势值得直接借鉴

[Sana 的文件生成课程](https://help.sana.ai/en/articles/104553-generate-from-file)会产出 outline、cards、text、images 和 outcomes，并允许接受或丢弃生成内容；其[自适应学习](https://help.sana.ai/en/articles/7485-adaptive-learning)通过起点测评、挑战与个性化复习调整学习路径。

灵知已经确定未确认课程变化必须高亮并允许接受、拒绝、重生成和修改范围。多模态层应沿用完全相同的语法，而不是另建一个媒体审核系统：

- AI 新增的图、动画或旁白显示来源、理由和适用范围。
- 替换原表达前先并排预览，不静默覆盖。
- 用户拒绝某个表达，不等于否定背后的课程语义。
- 用户只修改外观时，不应触发整门课程重写。

---

## 4. 灵知与市场产品的本质差异

### 4.1 不是“生成产物”，而是“维护课程与产物之间的关系”

大多数产品的单位是一个 artifact：一段音频、一份 PPT、一个视频、一组卡片。灵知的单位应继续是带稳定身份、教学作用、知识引用和证据引用的 `CourseBlock`，artifact 只是它的一种教学表达。

```text
市场常见模式
资料 → 分别生成 PPT / 音频 / 视频 / 测验 → 各自成为文件

灵知目标模式
课程语义块 → 表达计划 → 多种表示 → 挂回同一块
              ↑                         ↓
         学习证据决定选择        效果证据反向评价
```

### 4.2 灵知已有但竞品通常没有贯通的资产

| 灵知既有资产 | 放进多模态后产生的新价值 |
| --- | --- |
| `CourseDocument / CourseBlock` | 所有媒体拥有稳定课程位置和修订，不再是漂浮附件 |
| `kind + role` 分离 | 能区分“视频这种形式”与“例子这种教学作用”，为路由提供正确维度 |
| `LearningObjective` | 生成前说明要达成什么，生成后判断是否覆盖目标 |
| `EvidenceUnit` | 图、旁白、PPT 和视频可追到教材证据，避免无依据发挥 |
| 统一学科知识库与 `CourseKnowledgeMap` | 可生成知识图、先修动画，并检查不同模态概念是否一致 |
| `PracticeTask / MasteryCriterion` | 动画暂停点、视频理解检查、模拟任务能回到正式评测 |
| `LearningEvent / LearnerModel` | 不靠固定风格标签，而是用真实效果选择下一次表达 |
| `CourseChangeSet / ChangeOperation` | 媒体里的语义编辑可安全回流课程，而不是直接覆盖正文 |
| `GenerationJob` 与失败恢复 | 高成本媒体能排队、缓存、重试、降级，不阻断基础课程 |

### 4.3 灵知应形成的产品表述

面向用户可表述为：

> **一句话生成一门会生长的课程。它不只生成文字，而会把同一知识组织成图解、讲解、动画、模拟和练习；随着你学习，它会选择更适合你的表达，并把每次变化清楚标出来。**

面向技术团队应表述为：

> **以 `CourseDocument` 为唯一语义真源，以 typed intermediate representation 为生成中间层，以 `RepresentationSet` 为多模态投影，以学习证据和质量门驱动选择与迭代。**

### 4.4 当前灵知与竞品能力对账

| 能力 | 市场成熟参照 | 当前灵知 | 目标结合点 |
| --- | --- | --- | --- |
| 一句话/资料生成课程 | Coursebox、Oboe、Mindsmith | 已有统一生成任务、资料证据、教学模式、难度、蓝图、质量门和规范课程发布 | 保留现有主链，不另建“多模态课程生成”入口 |
| 资料到多种学习产物 | NotebookLM | 资料可追溯到课程块，但尚未形成统一 Artifact/Representation 派生 | EvidenceUnit 直接进入 RepresentationPlan 和每个表示的 provenance |
| 同一个性化底座派生多模态 | Learn Your Way | 已有个体化生长规格，但尚无正式表示实体 | 让同一 CourseBlock revision 成为文本、图、音频、幻灯和动画共同源 |
| 上下文内嵌多种表达 | Oboe | 已有块级 AI 与正文现场，媒体仍主要是块类型或附件 | 在原块增加“换一种讲法”和 RepresentationSet，不建独立媒体 Studio 主流程 |
| 专业课程块与发布 | Mindsmith、Rise | 已有异构 CourseBlock、正式练习与学习现场 | 吸收成熟块预览、响应式、无障碍、导出和人工审核纪律 |
| 可执行 AI 课堂场景 | OpenMAIC | 尚无 Scene/Action DSL 和播放器状态机 | 移植场景发动机，所有场景仍由灵知课程、目标和证据控制 |
| 可编辑 PPT | NotebookLM、ClassBuild、Rise | 蓝图已提出 PPT 投影，尚未实现对象级同源与反向语义 diff | SlideDeckSpec + object metadata + ChangeOperation 回流 |
| 结构化动画与模拟 | OpenMAIC、Code2Video、Math-To-Manim | 有 Mermaid、代码、媒体渲染零件，尚无统一 spec/renderer/quality 链 | 建立 SceneSpec、InteractionSpec、代码沙箱和局部修复 |
| 学习证据驱动的主动变化 | Sana 自适应、灵知自己的核心设计 | 正式事实与 LearnerModel 已在主链；课程生长尚在规格阶段 | 同一证据同时决定内容粒度和表达选择，仍走候选确认 |
| 跨模态效果验证 | 市场普遍较弱 | 已有正式作答、诊断、反馈和延迟复验底座 | 建立表示曝光与效果投影，比较高成本表达和简单替代 |

这一对账说明：灵知的短板不是“比别人少一个视频按钮”，而是**现有强课程内核与外部媒体能力之间缺少正式领域层**。这层一旦建立，市场产品的许多能力都可以成为可替换插件；如果不建立，再多模型都会把灵知拉回多真源和不可维护状态。

### 4.5 三类结合方式

1. **直接移植**：协议清晰、许可证可接受、不会拥有课程真源的渲染与播放零件，例如 Mermaid/ECharts renderer、OpenMAIC 场景动作、PPTX exporter。
2. **架构吸收**：项目本身不够成熟或领域模型与灵知冲突，但过程设计优秀，例如 Math-To-Manim 的 typed artifacts、ClassBuild 的资产计划与 stale hash。
3. **体验借鉴**：闭源能力无法移植，但用户心智已经被验证，例如 NotebookLM Studio 的按需产物、Sana 的接受/丢弃、Oboe 的正文内生成、Rise 的响应式审核与发布。

---

## 5. 开源项目调研：哪些可以移植，哪些只应吸收思想

### 5.1 第一优先级：OpenMAIC 的“可执行课堂场景”能力

[OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) 是本次调研中与灵知多模态目标最接近、最值得深挖的开源项目。它不是简单把文字转成 PPT，而是把一次课程表达成舞台、场景、角色、幻灯、白板动作、讨论和互动组件的序列；可由主题或资料生成 slides、quiz、HTML simulation、PBL 等课程，并支持教师与同伴角色在课堂中讲解、书写和讨论。

#### 真正有价值的内部思想

OpenMAIC 采用两阶段结构：

```text
课程主题 / 资料
→ Outline
→ Stage
→ Scene[]
→ SceneContent
→ Action[]
→ 播放器按状态机执行
```

其 `Action` 不是一段不可解释的视频，而是一组可执行的教学动作，包括：

- 角色讲话、聚光、切换角色。
- 白板文本、形状、连线、图表、LaTeX、表格与代码。
- 内容编辑、高亮、逐步显示。
- 视频播放、角色讨论。
- widget 状态更新和交互揭示。

这套结构与灵知特别契合，因为它把“动画/课堂”从像素文件还原成可检查、可编辑、可暂停的结构。灵知可以知道某个场景讲了哪个知识点、用了哪个例子、在哪一步插入检查，而不是只得到一个 MP4。

#### 建议移植的模块

| OpenMAIC 能力 | 移植方式 | 在灵知中的落点 |
| --- | --- | --- |
| 场景与动作 DSL | 提炼协议，不照搬课程实体 | 新增 `SceneSpec / TimelineAction` 中间产物 |
| 白板与幻灯渲染器 | 作为前端独立 renderer | `TeachingRepresentation` 的 structured scene 类型 |
| 播放状态机 | 封装为可暂停、跳步、回看组件 | 正文中的动画/讲解块与专注弹窗 |
| slide schema 与 PPTX 导出 | 适配灵知资产引用 | 章节讲解幻灯与教师侧未来导出 |
| HTML widget / simulation 导入 | 加强沙箱后复用 | 交互模拟、参数实验、小游戏 |
| provider registry | 吸收接口思想 | 灵知统一 `GenerationProvider` 注册表 |
| HTML/ZIP/PPTX exporter | 按需求拆取 | 离线学习包、课堂演示、启智未来交付 |

#### 明确不要整体 fork

OpenMAIC 自己拥有课程、角色、项目、场景和播放状态。如果把整套应用嵌进灵知，会形成第二个课程真源、第二套会话和第二套学习状态。正确方式是“摘发动机，不换底盘”：

- 灵知 `CourseDocument` 决定讲什么和顺序。
- `RepresentationPlan` 决定哪些块要编译成 OpenMAIC 风格场景。
- 场景 DSL 只承担如何讲，不拥有课程语义。
- 互动结果写回灵知正式 `LearningEvent / PracticeAttempt`，不存进播放器私有状态。

#### 许可证判断

仓库主项目在 2026-06-28 从 AGPL 调整为 MIT；但其第三方依赖仍需逐项审计，例如 `mathml2omml` 为 LGPL-3+，`pptxgenjs` 为 MIT。技术负责人不能只看根目录许可证便默认整条依赖链都可无条件商业使用。

### 5.2 第二优先级：ClassBuild 的课程资产计划与批量生产纪律

[ClassBuild](https://github.com/jtangen/classbuild) 采用 Setup → Syllabus → Research → Build → Export 的流程，可以为每章生成 reading、widgets、PPTX、quizzes DOCX、practice、audio、activities、infographic、weekly challenge 和 SCORM。

它最值得吸收的不是页面，而是两个工程习惯：

1. **先有 Curriculum/Asset Map，再批量生成。** 系统明确每章需要哪些资产，而不是生成正文后临时到处补附件。
2. **保存 syllabus hash 判断资产陈旧。** 上游教学大纲变化后，系统能够知道哪些下游内容可能已失效。

这些思想可以升级为灵知的 `RepresentationPlan + AssetDerivationGraph`：

```text
上游 CourseBlock revision / objective revision / concept revision / evidence revision
→ derivation fingerprint
→ 下游表示的 fresh / stale / blocked / rebuilding 状态
```

不建议照搬的部分：

- `GeneratedChapter` 通过大量平行字段分别保存各种产物，容易演变成每种模态一套真源。
- 当前部分幻灯以整张 4K 图片生成，视觉完成度高但文字、布局和语义几乎不可编辑。
- 音频生成若只剥离 HTML 文本，会丢失图表、公式和交互所承载的语义。

### 5.3 数理动画：Code2Video 适合借鉴多 Agent 修复，Math-To-Manim 适合借鉴工件链

#### Code2Video

[Code2Video](https://github.com/showlab/Code2Video) 将一个知识点通过 Planner、Coder、Critic 转成 Manim 动画，并建立视觉锚点；其评测关注 TeachQuiz、视觉审美与生成效率。它说明数理动画不能只有“写代码”一步：

```text
教学规划
→ 场景代码
→ 渲染
→ 批评与修复
→ 教学问题反测
```

灵知可借鉴：

- Planner 读取知识、目标、role 与难度，不直接让 Coder 自由发挥。
- Critic 除了检查代码能否运行，还要检查公式、对象关系、节奏和知识覆盖。
- 动画完成后自动生成少量理解题，反测它是否清楚表达了目标，而不是把题目当装饰。

#### Math-To-Manim

[Math-To-Manim](https://github.com/HarleyCoops/Math-To-Manim) 的文档展示了一条更完整的 typed artifact chain：

```text
intent
→ prerequisite graph
→ curriculum
→ math packet
→ storyboard
→ scene spec
→ code
→ AST / static validation
→ render
→ video review
→ package
```

它尤其值得吸收三点：

- 每个阶段都有落盘工件，可以定位失败、复用和审计。
- 代码失败时基于冻结的 `SceneSpec` 局部修复，不从最初 prompt 重新随机生成整段。
- 最终产物带 manifest 和 trace，能够追踪使用了哪些输入和版本。

其当前大量实现位于 archive/experimental 路径，不能直接视为成熟生产库；建议吸收架构，不把整个仓库作为核心依赖。

### 5.4 建议纳入的结构化渲染器

| 项目 | 许可证 | 适合生成什么 | 灵知接入建议 |
| --- | --- | --- | --- |
| [Mermaid](https://github.com/mermaid-js/mermaid) | MIT | 流程图、时序图、关系图 | P0；服务端校验，前端严格 sandbox，关注其[安全公告](https://github.com/mermaid-js/mermaid/security) |
| [Excalidraw](https://github.com/excalidraw/excalidraw) | MIT | 手绘感概念图、白板 | P0-P1；保存 scene JSON，不只导出 PNG |
| [Vega-Lite](https://github.com/vega/vega-lite) | BSD-3-Clause | 声明式数据可视化 | P0；保存 spec、数据和解释 |
| [Apache ECharts](https://github.com/apache/echarts) | Apache-2.0 | 图表、关系图、交互数据视图 | P0；适合中文生态与交互图表 |
| [Manim](https://github.com/ManimCommunity/manim) | MIT | 数学、算法、几何、公式动画 | P1；异步沙箱渲染并保存 scene spec/code/log |
| [Motion Canvas](https://github.com/motion-canvas/motion-canvas) | MIT | 代码驱动 2D 动画、时间轴讲解 | P1；适合 Web 预览和精细时间轴 |
| [Three.js](https://github.com/mrdoob/three.js) | MIT | 3D、空间结构、物理可视化 | P2；只用于确有空间价值的主题 |
| [H5P](https://github.com/h5p/h5p-php-library) | GPL-3.0 | 通用互动学习组件 | P2；先审内容类型许可证与打包边界，不直接混入闭源核心 |

这些渲染器有一个共同优势：输出不是不可解释的像素，而是结构化 spec 或代码。灵知能做版本、局部修改、主题适配、无障碍替代和质量检查。

### 5.5 可自托管的语音、视频模型与许可证边界

| 模型 / 项目 | 适合用途 | 许可证与风险 | 建议 |
| --- | --- | --- | --- |
| [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) | 中文/多语 TTS、讲解旁白 | Apache-2.0；仍需处理声音授权与克隆滥用 | 可作为中文自托管 TTS 候选 |
| [Wan2.2](https://github.com/Wan-Video/Wan2.2) | 文生/图生视频 | Apache-2.0；GPU 成本和教学正确性仍高 | 进入 provider 池，不进入语义主链 |
| [LTX-2](https://github.com/Lightricks/LTX-2) | 视频生成与编辑 | 自定义许可；年营收达到其阈值的实体需另行商业许可 | 只在法务确认后接入；不要与旧 LTX-Video 许可混淆 |
| [HunyuanVideo](https://github.com/Tencent-Hunyuan/HunyuanVideo) | 视频生成 | 自定义社区许可存在地域等限制 | 不作为默认可移植基座 |
| [Remotion](https://www.remotion.dev/license) | React 程序化视频编排 | 特殊许可；个人、非营利和不超过特定规模团队免费，其他企业需商业许可 | 适合作为可选编排器，接入前确认组织资格 |

结论：模型权重“能下载”不等于产品“可以无条件商用”。多模态供应链必须为每项资产记录 `provider / model / model_version / license_basis / source / consent / generated_at`，并允许在许可证变化时替换提供方。

---

## 6. 闭源能力调研：不复制模型，复制产品决策

### 6.1 图片生成与编辑

[OpenAI Image API](https://developers.openai.com/api/docs/guides/image-generation) 支持生成、编辑与多轮图像修改。对灵知最有价值的是“基于现有图持续编辑”的交互，而不是每次从头生成：

- 用户指出“把右侧箭头改成反向”时，系统先判断这是表现修改还是知识修改。
- 表现修改产生新 asset revision。
- 如果箭头承载因果或推导语义，则必须形成课程语义候选并重新验证。

[Adobe Firefly Services](https://developer.adobe.com/firefly-services/docs/firefly-api/api/) 的价值更多在企业生产、模板化处理和商用工作流。灵知可借鉴“品牌/主题模板与内容生成分离”，让学校主题、课程视觉和知识语义互不污染。

### 6.2 视频生成与编辑

[OpenAI Video API](https://developers.openai.com/api/docs/guides/video-generation) 体现了异步任务、短片生成、延长与编辑等能力；[Google Veo](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/overview) 支持文本、图片、首尾帧、素材组合、延展、插入和移除；[Runway API](https://docs.dev.runwayml.com/guides/pricing/) 则把模型、时长与 credits 成本明确产品化。

灵知应借鉴的不是某家特定模型，而是统一任务抽象：

```text
GenerationJob
├── capability: text_to_video / image_to_video / extend / edit / inpaint
├── provider + model + version
├── source representation + derivation fingerprint
├── cost estimate + budget policy
├── status + progress + retryability
├── result asset + provenance
└── fallback chain
```

任何视频提供方都只能是 renderer/provider，不得决定课程结构或直接写学习事实。

### 6.3 配音、多语言与数字人

[OpenAI TTS](https://developers.openai.com/api/docs/guides/text-to-speech) 可承担常规讲解音频；[ElevenLabs Dubbing](https://elevenlabs.io/docs/overview/capabilities/dubbing) 展示了跨语言配音工作流；[HeyGen Avatar API](https://developers.heygen.com/reference/create-avatar)、Synthesia 与 Colossyan 展示了数字人和培训视频的规模化生产。

对灵知的判断：

- TTS 是高性价比模态，应早于自由视频。
- 多语言不应只翻译字幕，还要维护术语表、公式读法、专有名词和例子文化适配。
- 数字人只是 narrated presentation 的一种皮肤，不应成为独立课程真源。
- “真人感”不是学习效果指标。447 名参与者、1,788 次处理的[AI 与真人教学视频研究](https://doi.org/10.1016/j.compedu.2024.105164)显示知识结果相近，但真人略受偏好；另一个 [AI avatar 试点研究](https://doi.org/10.2196/89277)样本仅 38 人，主观参与和清晰度更高，客观成绩差异不显著。现阶段不能把数字人包装为确定的学习增益。

### 6.4 闭源产品最值得借鉴的五条产品原则

1. **按需生成**：先让用户看到可靠的基础课程，需要时再生成高成本表达。
2. **输入资产复用**：文本、图片、首尾帧、角色、声音和主题模板可复用，减少随机漂移。
3. **提供方可替换**：产品不应绑定某个模型的 prompt 与返回结构。
4. **编辑优先于重生成**：局部延展、插入、删除、配音和重排比整段重做更符合课程迭代。
5. **成本前置可见**：时长、分辨率、等待时间、失败概率和预算都应进入生成决策，而不是生成后才暴露。

---

## 7. 深挖灵知已有资产：让一份内容产生十次价值，而不是重新生成十份内容

### 7.1 复用的基本单位不是“文件”，而是带身份的语义资产

灵知现有课程中的每个定义、例子、推导、代码、目标、证据、知识关系和题目，都应被视为可以派生多种表示的语义资产。所谓“深度挖掘”，不是把同一段话分别丢给十个模型，而是先拆清它拥有什么教学含义，再让不同表示复用同一组稳定引用。

每个多模态产物至少要回答：

```text
它源自哪个 CourseBlock revision？
服务哪个 LearningObjective revision？
覆盖哪些 concept / ability / misconception？
依据哪些 EvidenceUnit？
承担什么教学 role？
对哪个难度与学习情境有效？
由哪个 RepresentationPlan / provider / model 生成？
如何验证，何时失效？
```

### 7.2 课程内容资产的衍生全景

| 既有内容 | 可衍生表达 | 深挖方式 | 不能丢失的关系 |
| --- | --- | --- | --- |
| 课程总览 | 章节导览、路线图、预习音频、开场短片、课程海报 | 把目标、先修、难度曲线与章节关系重新编排，而非摘要正文 | 目标覆盖、章节稳定 ID、先修关系 |
| 定义块 | 简明/严谨文本、术语卡、概念图、正反例图、口语讲解、辨别题 | 将“必要条件、充分条件、边界、反例”拆成可视与可测元素 | concept、evidence、definition revision |
| 原理/命题 | 直觉图、条件-结论图、证明动画、应用场景、错误命题对照 | 区分直觉、形式表述与证明，不让动画代替条件 | objective、premise、conclusion、proof refs |
| 推导块 | 逐步公式、状态机、白板动画、旁白幻灯、可拖动步骤、缺步题 | 每一步保存 before/after、依据、口播与视觉焦点 | step ID、公式 AST、推导依据、顺序 |
| 例子块 | 配图、故事情境、角色对话、数值模拟、分支案例、迁移例 | 保留例子所说明的机制，允许替换表面情境 | example purpose、concept refs、difficulty |
| 反例块 | 对比图、错误路径动画、真假判断、误区对话 | 高亮“看似成立的原因”和“在哪一步失败” | misconception refs、counter evidence |
| 代码块 | 静态解释、可运行沙箱、执行轨迹、变量表、算法动画、debug 任务 | 从 AST/运行结果生成状态，而非让视频模型想象代码执行 | source code revision、runtime、test、output |
| 数据/表格 | 交互图表、趋势讲解、筛选任务、异常点问题、音频摘要 | 数据、spec、文字结论三者分离；结论必须能追到数据 | dataset hash、chart spec、claim refs |
| 图片 | 局部标注、热点图、对比图、分步揭示、无障碍描述、图像问答 | 不只存图片 URL，还保存标注层与语义区域 | source/license、region anchors、alt text |
| 知识图/课程知识映射 | 思维导图、先修路径动画、当前章节地图、复习路线、掌握覆盖 | 按任务投影子图，不把完整学科库一次性展示 | official ID、map revision、relation type |
| 学习目标 | 目标导语、自检清单、讲解重点、测验蓝图、总结模板 | 所有表示都要声明覆盖哪些目标，不让“好看”替代达成 | objective revision、mastery criterion |
| 正式题目 | 口头问答、视频暂停题、交互预测、分步提示、变式题 | 复用题目身份和评分要求，表现层只改变呈现方式 | task revision、answer/rubric isolation |
| 掌握标准 | 讲解检查点、模拟成功条件、项目量规、复验问题 | 把标准编译成互动约束和质量门 | criterion revision、objective refs |
| 易错点 | 错误演示、对比动画、AI 角色争辩、诊断分支 | 将易错点作为候选地图，必须由真实证据确认个人命中 | misconception ID、diagnostic evidence |
| 提升点 | 挑战任务、远迁移案例、开放模拟、项目分支 | 在已达成基础目标后生成，不用简单加字或加题冒充进阶 | ability refs、readiness evidence |
| 教材证据 | 引用卡、原文对照、图表来源、讲解脚注、版权信息 | 同一证据片段可支撑多种表示，但每个主张仍单独映射 | asset/evidence revision、page/span |
| 学生笔记 | 个人解释重排、回顾卡、问题清单、个人音频摘要 | 只在用户授权的个人域内派生，不自动混入正式课程 | learner、course、anchor、privacy |
| AI 问答 | 当前块补充、不同讲法、对话回顾、待解决问题 | 临时回答与正式课程分离；明确保留后才成为个人内容 | conversation/message/block refs |
| 错题与诊断 | 错误路径回放、最小补救动画、相似情境、独立复验 | 根据已验证错因选择表达，不因一次错误直接生成画像 | attempt、diagnostic case、evidence |

### 7.3 一个推导块如何被“榨干价值”

以“高斯消元”为例，同一个推导块可以先被结构化为：

```text
DerivationSpec
├── initial_state：增广矩阵
├── steps[]
│   ├── operation：R2 ← R2 - 2R1
│   ├── rationale：保持方程组等价
│   ├── before / after
│   ├── focus_cells
│   ├── common_error
│   └── check_prompt
├── final_state
└── concept / objective / evidence refs
```

随后不重复理解知识，直接派生：

- 正文中的逐步公式与高亮。
- 白板动画中的矩阵变换。
- narrated slides 的每页内容和旁白。
- 可由学生点击“下一步”的交互演示。
- 缺失步骤排序题与错误步骤诊断题。
- 音频版本中的口头描述与“请查看当前矩阵”的同步提示。
- 教师端未来 PPT 中可编辑的公式和动画备注。

如果第三步的数学语义被修改，所有依赖第三步的表示进入 `stale`；只修改动画速度，则其他表示不失效。这就是同源结构真正节省的成本。

### 7.4 一个知识图如何产生多种“任务化视图”

知识图不能只做一张可以缩放的网络图。基于同一 `CourseKnowledgeMap`，灵知可以生成：

- **导学视图**：本章要经过哪些概念，为什么按这个顺序。
- **先修视图**：当前概念依赖什么，缺口在哪里。
- **推理视图**：某个结论如何由前置概念共同推出。
- **复习视图**：到期目标和关联例题构成的最小路线。
- **误区视图**：经过诊断确认后，错误理解与正确概念冲突在哪里。
- **成长视图**：不是展示“你很差”，而是展示已获得证据、待复验和下一层能力。

这些都是同一图谱的运行时投影，绝不能分别保存成六套知识图。

### 7.5 把学习证据也转化为“表达资产”，但不泄露学生隐私

学习证据的价值不只在生成画像，还可以决定课程如何表达：

| 证据模式 | 可能的表达调整 | 仍需遵守的边界 |
| --- | --- | --- |
| 连续要求“再讲细一点” | 后续推导增加中间状态、口播解释和检查点 | 先形成有范围的假设，不自动扩大到全书 |
| 文本看完但图形任务反复失败 | 为相关概念加入可操纵图形或空间动画 | 不得推断成永久“视觉型学生” |
| 视频频繁回看同一位置 | 生成该位置的静态步骤图和关键帧摘要 | 回看只是一条证据，需结合后续作答 |
| 音频学习后正式复验表现更好 | 相似叙事内容可提高音频候选优先级 | 仅在当前课程和相近任务中使用 |
| 交互模拟操作正确但解释错误 | 加入口头/文字因果解释，不把操作成功视为掌握 | 正式标准同时检查行为与解释 |
| 多次跳过高成本媒体且文本完成良好 | 默认折叠高成本表达，保留按需入口 | 不删除可访问替代，也不降低目标 |

### 7.6 复用的四层深度

灵知不能把“复用”只理解为缓存文件。应依次实现：

1. **语义复用**：知识、目标、例子、推导步骤、证据只理解一次。
2. **结构复用**：同一个 storyboard/scene spec 可渲染为 Web、PPTX、视频或静态图。
3. **媒体复用**：配音、插图、角色、镜头、主题和关键帧可跨产物复用。
4. **效果复用**：某种表达在相似知识任务上被验证有效后，提高后续路由优先级，但保留置信度、范围和反证。

---

## 8. 目标架构：在现有课程真源之上增加“教学表达编译层”

### 8.1 完整分层

```text
第一层：课程语义层（现有真源）
CourseDocument / CourseBlock / CourseKnowledgeBase / CourseKnowledgeMap
LearningObjective / PracticeTask / MasteryCriterion / EvidenceUnit

第二层：教学表达规划层（新增）
RepresentationPlan / RepresentationRequirement / RepresentationPolicy
决定为什么生成、生成什么、面向谁、覆盖什么、成本上限是什么

第三层：结构化中间产物层（新增）
SlideDeckSpec / Storyboard / SceneSpec / NarrationSpec / DiagramSpec
ChartSpec / InteractionSpec / SimulationSpec / AssessmentEmbeddingSpec

第四层：渲染与提供方层（新增适配器）
Mermaid / ECharts / Excalidraw / Manim / Motion Canvas / Three.js
TTS / Image Model / Video Model / Avatar / Exporter

第五层：表示与资产层（扩展现有 MediaAsset）
TeachingRepresentation / RepresentationSet / MediaAsset / AssetDerivationGraph

第六层：学习运行与证据层（复用现有主链）
LearningRuntime / LearningEvent / PracticeAttempt / DiagnosticCase / LearnerModel
```

### 8.2 为什么必须有“教学表达规划层”

如果没有这一层，产品只能做：

```text
选中内容 → 选择视频 → 生成
```

有了这一层，系统才能做：

```text
发现当前块 role=reasoning，目标要求解释因果，学生在中间状态反复出错
→ 候选表达：逐步可控动画，而非写实视频
→ 必须展示 4 个状态、2 个关键不变量、1 个理解检查
→ 首选 Motion Canvas/Manim；失败回退为静态步骤图
→ 预算上限、预计时长、质量门和证据回写均已定义
```

### 8.3 核心新实体

#### `TeachingRepresentation`

表示“同一课程语义的一种教学表达”，不是原始媒体文件。

建议最小字段：

```text
representation_id
course_id
source_block_ids[]
source_revisions[]
objective_refs[]
concept_refs[]
evidence_refs[]
role
modality
format
spec_ref
asset_refs[]
applicability
quality_report_ref
provenance
derivation_fingerprint
status: planned / generating / ready / stale / blocked / failed / archived
revision
```

#### `RepresentationSet`

挂在一个或多个稳定课程块上的表示集合，保存默认表示、替代表示、组合规则与降级链：

```text
representation_set_id
source_scope
default_representation_id
alternative_representation_ids[]
selection_policy
fallback_order[]
accessibility_pairs[]
revision
```

#### `RepresentationPlan`

回答“为什么需要生成”和“怎样才算完成”：

```text
plan_id
source_scope
learning_problem
teaching_intent
target_objectives
required_semantic_units
recommended_modality
rejected_modalities + reasons
duration / complexity / cost budget
interaction checkpoints
accessibility requirements
quality gates
```

#### Typed Specs

- `DiagramSpec`：节点、关系、布局语义、重点与文字替代。
- `SlideDeckSpec`：页、版式角色、讲述顺序、视觉对象、speaker notes。
- `NarrationSpec`：语句、停顿、术语读法、语气、同步锚点。
- `SceneSpec`：场景、对象、状态、动作、焦点、时间与转换。
- `InteractionSpec`：可操作参数、状态约束、任务、反馈与成功条件。
- `SimulationSpec`：变量、模型、初始条件、允许范围、观测量与验证案例。

#### `AssetDerivationGraph`

不一定首期独立建库，但必须形成明确依赖关系：

```text
CourseBlock@r7
├── SlideDeckSpec@r2
│   ├── deck.pptx@r1
│   ├── deck.html@r2
│   └── narration.wav@r3
├── SceneSpec@r4
│   ├── interactive.html@r2
│   └── animation.mp4@r1
└── DiagramSpec@r1
    ├── diagram.svg@r1
    └── alt_text@r1
```

上游修订变化时，根据依赖粒度计算失效，不靠人工猜测。

### 8.4 `MediaAsset` 与 `TeachingRepresentation` 的边界

| 对象 | 含义 | 示例 |
| --- | --- | --- |
| `MediaAsset` | 一个受控文件或外部资源及其技术元数据 | SVG、MP3、MP4、PPTX、字幕、缩略图 |
| `TeachingRepresentation` | 这些文件怎样共同承担某个教学表达 | “用逐步白板动画解释行变换不改变解集” |
| `RepresentationSet` | 同一语义有哪些可选择或组合的表达 | 正文 + 交互动画 + 静态步骤图 + 音频替代 |

一段视频可以有多个文件资产：视频、字幕、讲稿、缩略图和音频描述；但它们共同组成一个教学表示。反过来，同一张概念图也可以被多个讲解引用，因此文件与教学意义不能混为一体。

### 8.5 `CourseBlock.kind` 不应膨胀成所有媒体类型

现有 `kind` 继续描述该块当前的主要呈现或交互方式，例如 `rich_text / formula / code / video / diagram / practice_ref`。替代表示通过 `representation_refs` 或 `RepresentationSet` 挂载，不要把一个概念块复制成 text block、audio block、video block 三份。

只有当某种表达本身在课程顺序中承担独立教学作用，例如一段必须完成的实验模拟，才应成为独立 `CourseBlock`。仅仅是“同一内容的另一种讲法”时，它属于表示层。

---

## 9. 双向编辑：PPT、动画和视频改了以后，课程应该怎样变

### 9.1 “双向联动”不能理解为任何像素修改都反写课程

用户最初提出的目标是：修改课程文字时 PPT 自动变化；修改 PPT 时目录、章节和正文也能相应变化。这个方向成立，但必须先区分三类编辑：

| 编辑类型 | 示例 | 正确处理 |
| --- | --- | --- |
| 表现编辑 | 改颜色、字体、版式、镜头、转场、语速、配音角色 | 只产生该表示的 revision，不修改课程语义 |
| 明确语义编辑 | 改定义、删除条件、替换例子含义、调整知识顺序、增加目标 | 解析为 `ChangeOperation` 候选，展示影响，确认后修改课程真源 |
| 模糊编辑 | 拖动箭头、删掉一张图、缩短某页，但无法判断是否影响知识 | 保持为待解释修改，要求用户选择“仅改呈现”或“同步课程含义” |

如果把所有 PPT 编辑都自动反写课程，会出现严重错误：教师只是为了排版删掉一句话，课程正文却被永久删掉；用户移动一个箭头，系统误以为知识关系改变。真正的双向联动是**可解释、可确认的语义回流**，不是盲目同步。

### 9.2 文本到 PPT 的正向编译

```text
CourseDocument 当前修订
+ CourseKnowledgeMap
+ LearningObjective
+ 选定章节/块
→ RepresentationPlan
→ SlideDeckSpec
   ├── slide role：导入 / 概念 / 推导 / 例子 / 检查 / 总结
   ├── source block refs
   ├── semantic units
   ├── layout intent
   ├── visual refs
   └── speaker notes
→ PPTX / HTML slides / PDF
```

修改正文后，不必整套重做：

- 只改某个例子：标记依赖该例子的 2 页为 stale。
- 调整小节顺序：重新计算页序和过渡，其他页面内容保持。
- 改课程主题色：只重新渲染，不重新规划知识。
- 改学习目标：重新检查整套幻灯的目标覆盖，可能触发多页候选。

### 9.3 PPT 到课程的反向解析

可编辑 PPT 中每个关键对象应带隐藏的稳定元数据，例如：

```text
representation_id
slide_id
source_block_id
semantic_unit_id
object_role
source_revision
```

当用户在灵知内编辑或重新导入 PPT 时：

```text
读取对象级 diff
→ 分类表现变化 / 语义变化 / 无法判断
→ 语义变化映射为 ChangeOperation
→ 计算对正文、知识、目标、题目和其他表示的影响
→ 原位置高亮候选 + 理由 + 范围
→ 用户接受 / 拒绝 / 部分接受 / 重新生成
→ CourseCommand 修改唯一课程真源
→ 依赖图标记其他表示 stale
→ 按需重编译
```

无法保留对象元数据的外部编辑文件仍可通过文本、顺序和视觉差异做辅助比对，但置信度必须降低，不能静默应用。

### 9.4 动画、模拟和视频的反向编辑

- **结构化动画**：修改 `SceneSpec` 中的公式、对象关系或步骤，可以精确映射课程语义；改时间轴与镜头只影响表示。
- **交互模拟**：修改变量、规则、成功条件可能影响知识或掌握标准，必须进入候选；修改控件样式不影响语义。
- **自由生成视频**：像素本身无法可靠反向解析课程。反向编辑应作用于 storyboard、script、shot list 和 narration，而不是把视频文件当课程真源。
- **字幕/讲稿**：若修改的是知识陈述，可生成语义候选；若只是口语润色，保留在 narration revision。

### 9.5 冲突与陈旧处理

| 场景 | 系统行为 |
| --- | --- |
| 用户基于旧课程修订编辑了一份 PPT | 标记 source revision 冲突，显示当前课程差异，不能直接覆盖 |
| 同一语义在正文和 PPT 被并行修改 | 分别形成候选，按 semantic unit 做三方合并 |
| 上游课程变化但媒体仍可观看 | 允许继续查看，显著标记“可能已过期”，不作为默认表示 |
| 重编译失败 | 保留旧产物与静态/文本降级，不阻断学习 |
| 用户拒绝语义回流 | PPT 保留为 representation-specific override，并显示与课程真源不一致 |

---

## 10. 多模态路由与个体化生长：决定“什么时候生成什么”

### 10.1 路由不是一个 prompt，而是一套可解释策略

建议路由分四步：

```text
第一步：识别教学问题
空间难以想象 / 过程不可见 / 关系复杂 / 语言负担 / 缺少情境 / 需要操练

第二步：提出候选表达
图解 / 逐步动画 / 音频 / 交互模拟 / 分支对话 / 讲解幻灯

第三步：约束与排序
知识精度、目标、role、证据、设备、时间、无障碍、成本、已有资产

第四步：生成或复用
优先已有且新鲜的高质量表示；其次轻量编译；最后才调用高成本模型
```

### 10.2 `kind × role × knowledge shape` 的推荐矩阵

| 知识/任务形态 | 常见 role | 首选表示 | 次选表示 | 通常不应首选 |
| --- | --- | --- | --- | --- |
| 抽象定义与边界 | concept / misconception | 概念图、正反例、辨别题 | 口语解释、短幻灯 | 写实视频 |
| 多步数学推导 | reasoning | 可暂停公式动画、逐步白板 | narrated slides、静态步骤图 | 数字人口播长视频 |
| 空间变换 | reasoning / application | 可操纵图形、3D/2D 模拟 | 代码动画、关键帧图 | 纯音频 |
| 算法执行 | reasoning / example | 代码轨迹、变量状态动画 | runnable sandbox、流程图 | 自由视频生成 |
| 历史因果 | orientation / reasoning | 时间线、地图、角色多视角 | 分支决策、对谈音频 | 无来源的写实重现 |
| 语言会话 | application / checkpoint | AI 角色对话、口语反馈 | 情境音频、字幕视频 | 长篇静态图表 |
| 实验与系统行为 | application / transfer | 交互模拟、预测-观察-解释 | 实验视频、数据图表 | 只有结论的动画 |
| 复习与回忆 | summary / checkpoint | 卡片、短音频、知识路径 | 讲解摘要、错因对比 | 重新播放整章视频 |

### 10.3 个体化不是“给每人生成所有东西”

高成本内容应采用分级、懒生成策略：

| 层级 | 表达 | 生成时机 |
| --- | --- | --- |
| Tier 0 | 文本、公式、代码、正式题目 | 课程基础发布时必须可用 |
| Tier 1 | 图解、流程图、数据图、静态步骤图 | 基于课程结构批量生成或首次查看时生成 |
| Tier 2 | narrated slides、TTS、结构化动画 | 目标明确且有需求/证据时生成 |
| Tier 3 | 交互模拟、3D、分支角色 | 对高价值概念专项生成并审核 |
| Tier 4 | 自由视频、数字人、高保真场景 | 情境确有价值且预算允许时按需生成 |

课程创建时不应一次性生成 Tier 2–4 的所有内容。否则会造成：等待时间过长、成本浪费、课程还没稳定媒体就已陈旧，以及学生根本不会使用的资产堆积。

### 10.4 证据如何触发当前和未来章节的表达调整

沿用灵知已经确定的“思维证据 + 事实证据”与动态门槛：

```text
学生在第二节连续要求展开两个推导步骤
+ 正式检查显示中间状态理解不足
→ 形成“当前章节需要更多可见中间状态”的 AdaptationHypothesis
→ 第二节：立即候选逐步动画/补充步骤图
→ 第三至第五节：扫描同类 reasoning blocks
→ 只对匹配块提出提前调整候选
→ 目录标记 AI 建议，用户可按小节/章节/全书确认范围
```

这里不能机械地规定“连续三次才触发”。单条非常明确的证据，例如用户指出“我无法想象特征向量经过变换后为何方向不变，并在图形题中失败”，就足以立即提出局部交互图候选；扩大到全课程仍需要跨位置一致证据或用户明确授权。

### 10.5 表达偏好的证据模型

建议只在当前课程内维护低风险、可撤销的 `RepresentationEffectSignal` 投影，可由既有学习事实计算而来，不建立新的隐藏画像真源：

```text
scope: knowledge_shape / role / course region
representation_type
exposure evidence
behavior evidence: play / pause / seek / interact / skip
subjective feedback
independent performance evidence
confidence
freshness
counterevidence
```

权重上应满足：

```text
独立正式复验
> 诊断任务表现
> 多次一致行为
> 单次主观偏好
> 单次点击或观看时长
```

观看完成只能说明接触过，不能说明掌握；点击动画也不能说明动画有效。

### 10.6 多模态变化仍走同一套确认语法

AI 可主动提出：

- 在当前块增加静态图、动画或音频替代。
- 把后续三个推导块改为逐步表达。
- 将某个已有视频替换成可交互模拟。
- 缩短叙事音频并增加两个检索问题。
- 为全章增加无障碍字幕和静态替代。

候选必须显示：

- **理由**：哪些证据、知识形态或质量问题支持它。
- **范围**：当前行/块/小节/章节/目录框选范围。
- **影响**：会新增什么、替换什么、成本和等待如何、哪些产物会失效。
- **操作**：接受、拒绝、部分接受、重新生成、补充要求、撤销。

未确认的多模态候选可以高亮保留并供用户预览，但不得成为正式默认课程表达。

---

## 11. 生成任务、提供方与成本控制

### 11.1 复用现有 `GenerationJob`，不要为每种模态建立任务系统

多模态是现有生成主链的扩展。统一任务应覆盖：

```text
planning
→ spec_generation
→ deterministic_validation
→ rendering / provider_generation
→ artifact_validation
→ pedagogical_quality
→ packaging
→ publication
```

首次课程生成与后续表达生成可以是不同 job type，但必须共享状态、持久化、恢复、幂等、日志和权限协议。

### 11.2 Provider Adapter 契约

```text
capabilities()
estimate(request)
validate_input(request)
submit(request)
poll(job_ref)
cancel(job_ref)
fetch_result(job_ref)
normalize_result(result)
health()
```

统一请求不暴露某家模型专属字段到课程层；专属参数进入 provider options。这样可在成本、地区、隐私或质量变化时替换提供方。

### 11.3 缓存与复用键

缓存不能只按 prompt 文本，而应按派生指纹：

```text
hash(
  semantic units + source revisions + objective revisions + evidence revisions
  + representation spec + renderer/provider version
  + locale + accessibility profile + theme version
)
```

主题改变只重渲染；语义改变重新规划相关部分；提供方重试可以复用中间 spec。

### 11.4 降级链必须在生成前定义

示例：

```text
交互矩阵变换
→ 失败：结构化动画
→ 失败：静态关键帧图
→ 失败：逐步公式文本
```

```text
数字人讲解视频
→ 失败：narrated slides
→ 失败：音频 + 图文同步
→ 失败：讲稿文本
```

任何高成本媒体失败都不能阻断 Tier 0 基础课程发布和阅读。

### 11.5 成本预算不是后台细节，而是路由输入

预算建议分为：

- 课程级预生成预算。
- 学生个人按需预算。
- 单次候选预算。
- 提供方月度/学校配额。
- 教师批准的高成本专项预算。

路由应同时考虑：已有表示可否复用、生成预计成本、等待时间、失效率、学生当前是否真的需要，以及低成本替代能否达到同一教学目的。

---

## 12. 多模态质量门：能播放只是最低标准

### 12.1 九类质量检查

| 质量门 | 检查内容 | 可自动化程度 |
| --- | --- | --- |
| 语义忠实 | 与课程块、知识、目标和资料是否一致 | 规则 + 模型交叉检查 + 抽样人工 |
| 教学覆盖 | 是否完整承担声明的 role 和目标 | schema 检查 + rubric |
| 跨模态一致 | 文本、图、旁白、字幕、题目是否互相矛盾 | 对齐检查 + 模型判别 |
| 数理/代码正确 | 公式、单位、数量、代码执行和图表数据是否正确 | AST、执行、数值测试优先 |
| 可读与可听 | 字号、对比度、画面停留、语速、术语读法、字幕同步 | 多数可确定性检查 |
| 节奏与分段 | 单段认知负荷、关键停顿、是否可暂停回看 | 规则 + 用户行为证据 |
| 互动有效 | 操作是否对应预测、比较、解释或验证，反馈是否正确 | 状态测试 + rubric |
| 可访问性 | 字幕、讲稿、alt text、键盘、减少动态、静态替代 | 大量可自动化 |
| 来源与合规 | 证据、素材许可、声音/肖像授权、安全和隐私 | 元数据门禁 + 人工审批 |

### 12.2 结构化内容优先做确定性验证

- Mermaid/ECharts/Excalidraw spec 先解析和渲染 smoke。
- Manim/Motion Canvas 代码在隔离环境做 lint、AST、依赖白名单和超时。
- 公式对比使用结构化 LaTeX/MathML 或符号表达，不只比较截图。
- 图表绑定原始数据 hash，检查坐标、单位和比例。
- 模拟用已知输入输出与不变量做测试。
- PPT 检查文字溢出、元素遮挡、对比度和对象元数据完整性。

### 12.3 生成式图片/视频需要更严格的教学抽检

至少检查：

- 画面中物体数量、相对位置、方向和时序。
- 公式、文字、坐标、仪器与历史符号。
- 人物、场景和文化表述是否产生偏见或误导。
- 画面是否与旁白同一时刻表达同一事实。
- 是否出现没有资料依据的“逼真细节”。
- 是否能用更可靠的结构化表达替代。

高风险学科、关键定义、公式推导和正式评测不应以自由生成视频作为唯一表达。

### 12.4 无障碍不是后补字段，而是同一表示的派生产物

参照 W3C 的[音视频无障碍指南](https://www.w3.org/WAI/media/av/)，每个媒体类型至少规划：

- 音频：讲稿、时间标记、非语言声音说明。
- 视频：字幕、讲稿、必要时音频描述、键盘控制。
- 动画：暂停/逐步、减少动态、静态关键帧替代。
- 图表/图片：简短 alt + 需要时的长描述或数据表。
- 交互：键盘路径、焦点状态、屏幕阅读标签、非拖拽替代。
- 颜色：不以颜色作为唯一信息编码。

无障碍产物与主媒体共享语义引用和修订，不允许媒体更新后字幕仍停留在旧内容。

### 12.5 安全与隔离

- LLM 生成的 Mermaid、HTML、SVG、JS 与动画代码均按不可信输入处理。
- HTML/模拟在严格 iframe sandbox、CSP、网络白名单与资源限额中运行。
- 禁止生成代码读取宿主页面 token、本地文件、摄像头和未授权网络。
- 渲染任务使用隔离容器、CPU/GPU/内存/时间上限和依赖白名单。
- 上传媒体在解析前做类型、恶意载荷和元数据处理。
- 学生私人笔记、问答和错题生成的个人媒体不得被其他学生复用。
- 教师或学校共享前，必须去除个人证据与会话内容，只保留经过治理的通用课程改进。

### 12.6 质量效果必须做“表达级”实验，而不是只看生成成功率

建议对每个 `TeachingRepresentation` 记录：

- 生成成功率、等待时间、成本、失败类型。
- 首次播放、完成、暂停、回看、互动与跳过。
- 主观“解决了吗”反馈。
- 同目标的即时检查与延迟复验。
- 采用前后的错误类型变化。
- 静态替代与高成本表达的相对效果。

最重要的比较不是“AI 视频 vs 没有视频”，而是：

```text
对哪类知识、哪个教学 role、哪种学生证据
某种表达是否比更便宜、更简单的替代方案产生稳定增益？
```

---

## 13. 用户体验：多模态能力应该怎样出现在灵知里

### 13.1 一句话创建课程

用户输入：

> “给我做一门面向高中生的线性代数入门课，希望直观理解矩阵变换，数学推导不要省略。”

系统流程：

1. 先生成课程 brief、目标、知识覆盖、难度曲线、`CourseDocument` 与基础 Tier 0 内容。
2. `RepresentationPlanner` 扫描知识形态和 role，给出资产计划：
   - 向量与矩阵：图解。
   - 线性变换：可操纵平面。
   - 矩阵乘法：分步动画。
   - 高斯消元：白板推导。
   - 章节复习：narrated slides + 正式练习。
3. Tier 1 内容随课程快速完成；高成本内容显示计划与按需入口，不阻塞课程发布。
4. 用户第一次到达相关块时，复用或生成适合当前设备与需求的表达。
5. 每个新增表达都显示“为什么在这里出现”，并能追溯到知识、目标和资料。

### 13.2 正文现场的“换一种讲法”

块级 AI 仍保留解释、举例、简化和提问；多模态不是另起入口，而是这些动作的表达升级。

例如用户在推导块点击“解释”：

```text
默认：生成临时文字解释
如果空间关系强：同时建议“打开可操纵图形”
如果步骤关系强：建议“逐步播放推导”
如果用户正在通勤：可选“生成 3 分钟音频”
```

用户也可以直接要求：

- “把这里画成图。”
- “做成可以拖动参数的动画。”
- “用老师在白板上讲的方式播放。”
- “给我一个 2 分钟音频，公式部分提醒我看屏幕。”
- “把这一节做成可编辑 PPT。”

系统先形成 `RepresentationPlan`，必要时展示预计时间、成本和更可靠替代，再执行生成。

### 13.3 主动生长候选

当证据足够时，AI 可在原位置提出：

> 你在本节两次要求展开中间步骤，正式检查也显示你能得到结果但无法解释变换过程。我建议把本节剩余两个推导和下一节第一个例子改成“逐步状态 + 可暂停动画”。这是当前课程内的局部调整，预计新增 3 个表示，不改变学习目标。

界面提供：

- 预览一个样例。
- 接受当前块。
- 应用到本小节。
- 在目录中框选范围。
- 拒绝。
- 重新生成并说明要求。

所有未确认变化继续高亮保留，和文本课程生长使用同一套 `CourseChangeSet` 体验。

### 13.4 课程表达面板，而不是媒体素材仓库

每个块可展开一个轻量“教学表达”面板：

```text
当前默认：逐步公式
可选：
✓ 静态步骤图（已就绪，适合快速回看）
✓ 可暂停动画（已就绪，3:10）
○ 音频讲解（按需生成，约 30 秒）
— 写实视频（不推荐：此处要求精确符号关系）

依据：目标 LO-3 · 知识 KP-17 · 教材第 42 页
状态：与课程当前修订一致
```

产品重点是“为什么选”和“是否一致”，而不是文件缩略图数量。

### 13.5 编辑和确认

用户在 PPT 中把例子从“电商销量”改成“校园食堂排队”：

1. 系统识别这是例子语义变化，不只是版式变化。
2. 生成候选：“将本节例子替换为校园排队，并同步正文、图表、旁白和相关练习情境。”
3. 列出不会变化的概念与目标，避免用户误以为整节重做。
4. 用户可以只保留 PPT 特例，或确认同步到课程。
5. 确认后其他依赖资产进入精准重编译，不相关章节不受影响。

---

## 14. 五类样板课程：验证系统不是只适合一种学科

### 14.1 线性代数：验证结构化动画、模拟与公式同源

**主题**：特征向量与特征值。

```text
定义块
→ 正反例概念图
→ 可拖动向量与矩阵变换
→ “方向保持不变”的逐步动画
→ narrated slides
→ 预测哪个向量方向不变的正式检查
```

演示重点：用户修改矩阵后，图形、动画状态和题目参数共同更新；用户在图形任务失败后，后续相关块出现待确认的空间解释候选。

### 14.2 历史：验证证据驱动、多视角与生成视频边界

**主题**：工业革命中的城市化。

```text
史料 EvidenceUnit
→ 时间线 + 地图 + 数据图
→ 工人、工厂主、城市管理者多角色对谈
→ 有来源的历史图像标注
→ 可选情境短片（明确为生成式重建）
→ 来源辨别与因果解释任务
```

演示重点：写实视频只能承担情境引入，事实主张仍由史料、地图与数据承载；角色观点必须与来源绑定并标注推断。

### 14.3 编程：验证代码真源与执行轨迹

**主题**：快速排序。

```text
代码块
→ AST 与运行 trace
→ 指针、pivot、数组状态动画
→ 可调输入的 runnable sandbox
→ 错误实现对比
→ debug task + 正式测试
```

演示重点：动画由真实运行轨迹产生，不由视频模型想象；修改代码后，trace、动画和测试结果精准失效重算。

### 14.4 外语：验证语音、角色对话与个体反馈

**主题**：英语学术讨论中的礼貌反驳。

```text
表达模板与语用目标
→ 多角色示范音频
→ 字幕与语调标记
→ AI 角色对话
→ 口语转写与 rubric 反馈
→ 相同意图的迁移情境
```

演示重点：学习目标不是“把视频看完”，而是能在新情境中完成礼貌反驳；声音、口音和角色可替换，rubric 与目标保持不变。

### 14.5 物理：验证模拟优先于自由视频

**主题**：简谐振动。

```text
方程与变量
→ 可调质量、弹性系数、阻尼的模拟
→ 位移/速度/能量同步图表
→ 预测-操作-解释任务
→ 关键状态动画
→ 实验视频作为真实现象补充
```

演示重点：学生改变参数时图表、动画和问题共同响应；系统检查物理不变量和数值结果，自由生成视频不承担定量关系。

---

## 15. 灵知与启智的未来打通：先留协议，不在本阶段改启智

用户已经确定当前优先把灵知学生端的 AI 能力做完整，因此本阶段不直接修改启智。但多模态实体和权限应从第一天为未来打通留出边界。

### 15.1 未来三域

| 权限域 | 拥有什么 | 可以流向哪里 |
| --- | --- | --- |
| 启智教师公共课程域 | 教师创建/审核的课程、表示、模板和发布策略 | 可发布为班级课程基线 |
| 灵知学生个人课程域 | 个体候选、个人表达选择、笔记、问答和学习证据 | 只在学生授权与隐私聚合后输出改进信号 |
| 正式知识与公共资产域 | 学科知识、经治理的通用表达模板和高质量资产 | 为启智和灵知共同引用 |

### 15.2 推荐的未来闭环

```text
教师在启智生成/审核公共 CourseDocument 与 RepresentationSet
→ 发布到班级
→ 学生在灵知获得个人运行时与个人生长候选
→ 灵知只聚合“哪些知识、哪些表达、哪类错误”的去身份化效果信号
→ 教师在启智看到课程质量候选
→ 教师确认后修改公共课程
→ 新修订重新发布，学生个人层做影响映射
```

严禁把学生原始对话、私人笔记、声音、错题全文或个人媒体直接回传教师公共域。启智得到的是经过权限、阈值和匿名化处理的课程效果证据。

### 15.3 对世界人工智能大会展示的启发

若启智在 7 月中旬需要展示，可以先演示“教师端同源课程资产”：同一章节生成可编辑 PPT、讲解场景和学生学习版本，教师修改语义后显示影响范围。但底层协议应与灵知目标一致，避免为了大会临时另造一条 PPT/视频生产链。当前文档只提出接口方向，不授权直接修改启智项目。

---

## 16. 实施路线：按依赖关系完整建设，不按媒体按钮逐个堆功能

> 本路线不做工期估计，重点是先后依赖和完成门禁。该变更涉及核心实体、生成契约与学习运行时，实施前应扩展现有 OpenSpec 或建立覆盖多模态教学表达的正式 OpenSpec，不能直接从 UI 按钮开始。

### 阶段 A：多模态语义底座

**目标**：让课程拥有可追溯的替代表示，而不改变唯一真源。

- 定义 `TeachingRepresentation / RepresentationSet / RepresentationPlan`。
- 为 `CourseBlock` 增加表示引用，不复制正文。
- 扩展 `MediaAsset` 的来源、字幕、alt、许可、provider 和修订字段。
- 建立 derivation fingerprint、fresh/stale 状态与依赖传播。
- 复用 `GenerationJob` 和现有发布/恢复协议。

**验收**：修改一个源块只使相关表示失效；主题变化只重渲染；删除表示不删除课程语义；媒体失败不阻断正文。

### 阶段 B：结构化图解与知识图投影

**目标**：以最低成本建立第一个真正同源的多模态闭环。

- `DiagramSpec`、Mermaid/ECharts/Excalidraw renderer。
- 定义、流程、比较、知识路径的路由规则。
- 解析、渲染、安全 sandbox、alt text 和静态降级。
- 正文现场生成、预览、接受、拒绝与重生成。

**验收**：图形与 block/objective/concept/evidence 同源；节点关系错误能被质量门拦截；键盘与屏幕阅读替代可用。

### 阶段 C：可编辑幻灯与音频

**目标**：实现最具展示力、又仍保持结构化可控的课程表达。

- `SlideDeckSpec + NarrationSpec`。
- HTML slides 与可编辑 PPTX 双输出。
- TTS、术语读法、字幕/讲稿、时间同步。
- 对象级 source metadata、PPT diff 与语义回流候选。
- narrated slides 播放器和静态 PDF 降级。

**验收**：正文改动精准更新相关页；PPT 语义改动形成可确认 `ChangeOperation`；表现改动不污染课程；音频和字幕与当前修订一致。

### 阶段 D：结构化动画与交互模拟

**目标**：把最难讲清的过程、空间和因果变成可操作表达。

- 引入 OpenMAIC 风格 `SceneSpec / Action DSL`。
- 接入 Manim/Motion Canvas；建立代码沙箱、静态验证与局部修复。
- `InteractionSpec / SimulationSpec` 与 HTML widget sandbox。
- 暂停点、理解检查和正式 `PracticeTask` 绑定。

**验收**：至少在线性代数、编程、物理三个样板中完成“源语义 → spec → 交互/动画 → 正式检查 → 效果证据”的闭环。

### 阶段 E：证据驱动的表达选择与未来章节预调

**目标**：让多模态真正进入个体化生长，而不是停留在生成工具。

- 从现有学习事件投影表达暴露与效果信号。
- 建立可解释路由和反证机制。
- 支持当前块、后续小节、目录框选范围的表达候选。
- 支持未确认高亮、部分接受、撤销和效果复验。

**验收**：系统能说明为什么为这个学生、这个知识、这个位置建议该表达；单次点击不形成稳定偏好；后续正式证据能提高、降低或撤销建议。

### 阶段 F：生成式视频、数字人与高级媒体

**目标**：在已有语义、spec、质量、成本和降级体系上接入高成本能力。

- 统一图片/视频/avatar provider adapters。
- storyboard、shot list、首尾帧与素材复用。
- 异步成本、预算、取消、失败恢复和提供方切换。
- 生成式重建标识、人物/声音授权、来源与安全检查。

**验收**：高成本媒体不是唯一表达；关键知识错误可拦截；provider 替换不改课程数据；生成失败自动回退到结构化表示。

### 阶段 G：启智协议与教师审核

**目标**：在灵知主链稳定后打通教师公共课程与学生个体课程。

- 公共 `RepresentationSet` 发布协议。
- 教师审核、班级模板和学校主题。
- 去身份化效果聚合与课程质量候选。
- 权限、撤回、修订和个人层影响映射。

**验收**：个人变化不能自动写回公共课程；教师发布新修订不覆盖学生私有记录；公共资产可被多名学生复用而不泄露个人证据。

---

## 17. 技术任务拆解：可直接交给开发负责人

### Epic 1：表达领域模型

- 新增表示、表示集、表示计划、typed spec 与派生关系 schema。
- 设计 repository、revision、command、receipt 和 migration。
- 扩展 `CourseBlock` 正式引用规则。
- 定义删除、归档、陈旧、重建与冲突状态。

### Epic 2：表达规划与路由

- 建立 knowledge shape classifier。
- 建立 `kind × role × objective × evidence` 的候选规则。
- 加入成本、延迟、设备、语言与可访问性约束。
- 输出推荐、拒绝原因、降级链和质量要求。

### Epic 3：结构化渲染平台

- renderer registry 与统一输入/输出。
- Mermaid/ECharts/Excalidraw/slide/audio 首批适配器。
- Manim/Motion Canvas/HTML simulation 第二批适配器。
- 沙箱、资源限制、日志、缩略图与预览。

### Epic 4：统一生成任务

- 扩展现有 `GenerationJob` 类型与阶段。
- provider registry、估价、预算、限流、轮询、取消、重试。
- spec 缓存、asset 缓存与 derivation fingerprint。
- 任务恢复、幂等发布和失败降级。

### Epic 5：多模态质量平台

- schema/AST/运行/布局/字幕/可访问性确定性检查。
- 语义忠实与跨模态一致性 rubric。
- 样板课程 golden cases 和 regression suite。
- 人工抽检工作台与质量报告。

### Epic 6：学习现场与审核交互

- 正文中的表达入口、状态和预览。
- 表示面板、默认/替代/降级视图。
- AI 候选高亮、理由、范围、成本和影响。
- 接受、拒绝、部分接受、重生成、撤销与目录框选。
- 移动端、键盘、屏幕阅读与减少动态。

### Epic 7：双向编辑与依赖传播

- slide/object 元数据与外部导入 diff。
- 表现变化、语义变化和模糊变化分类。
- 语义 diff → `ChangeOperation`。
- 三方合并、修订冲突和依赖失效。
- 局部重编译与 representation-specific override。

### Epic 8：效果证据与个体化选择

- 表达曝光、播放、交互和反馈事件。
- 与正式练习、诊断和延迟复验对齐。
- 作用域、置信度、新鲜度与反证投影。
- 当前块与未来章节的候选生成。
- 成本效果和简单替代对照。

### Epic 9：合规、许可与治理

- 模型、素材、声音、人物和生成产物 provenance。
- 提供方条款与开源依赖 SBOM。
- 学生个人资产隔离、保留和删除。
- 生成式内容标识、教师公共发布审核。
- 安全事件、版权投诉和资产撤回机制。

---

## 18. 优先级结论与明确不做的事

### 18.1 推荐顺序

```text
同源表示模型
→ 图解/图表
→ 可编辑 PPT + TTS
→ 结构化动画/模拟
→ 证据驱动选择
→ 自由视频/数字人
→ 启智公共课程打通
```

这个顺序不是因为视频不重要，而是因为前四层决定视频最终是“课程的一部分”还是“又一个无法维护的文件”。

### 18.2 明确不做

- 不在首页堆“生成图片 / 音频 / 视频 / PPT”四个互不相干的入口。
- 不为每种模态复制课程目录、正文、知识和学习状态。
- 不把自由生成视频用在需要精确数量、公式、方向和步骤的唯一讲解上。
- 不在课程创建时生成全套高成本媒体。
- 不把观看完成、播放时长或一次点赞直接当作掌握和稳定偏好。
- 不使用固定学习风格标签决定内容。
- 不让某个闭源 provider 的请求结构渗透到课程领域。
- 不让媒体编辑静默覆盖课程语义。
- 不因为动画、视频或数字人失败而阻断基础课程。
- 不在当前阶段借多模态之名同时重构启智；只保留未来协议。

### 18.3 最终产品判断

如果灵知只接入图片、语音和视频模型，它会快速得到演示效果，也会快速陷入产物失控、成本失控和课程不一致。真正值得建设的是一条新的核心能力：

> **教学内容不是固定页面，而是一组有共同语义来源、可选择、可编译、可验证、会随学习证据演化的教学表达。**

灵知此前建立的结构化同源和个体化生长不是多模态之前的另一套工作，而正是多模态能够成立的前提。多模态使“结构化同源”从文字扩展到所有表达，使“个体化生长”从增删正文扩展到选择怎样讲、何时讲、讲到什么粒度。二者结合后，灵知才会从“一句话生成课程”进一步变成：

> **一句话生成一门能够换形态、会理解学生、也会持续长大的课程。**

---

## 19. 主要资料与进一步阅读

### 原生多模态课程与产品

- [Google Research：Learn Your Way](https://research.google/blog/learn-your-way-reimagining-textbooks-with-generative-ai/)
- [Learn Your Way 论文](https://arxiv.org/abs/2509.13348)
- [NotebookLM 移动端与 Studio 功能](https://support.google.com/notebooklm/answer/16296687)
- [NotebookLM Slide Decks 与修订边界](https://support.google.com/notebooklm/answer/16757456?hl=en)
- [Oboe 产品介绍](https://oboe.com/blog/introducing-the-all-new-oboe)
- [Oboe 自身课程示例](https://oboe.com/learn/landing-a-job-at-oboe-ehcsrx)
- [Coursebox](https://www.coursebox.ai/)
- [Mindsmith](https://www.mindsmith.ai/)
- [Mindsmith Lesson Editor](https://help.mindsmith.ai/en/articles/12037477-the-lesson-editor)
- [Articulate Rise](https://www.articulate.com/360/rise/)
- [Sana：Generate from file](https://help.sana.ai/en/articles/104553-generate-from-file)
- [Sana：Adaptive learning](https://help.sana.ai/en/articles/7485-adaptive-learning)

### 开源课程、动画与渲染

- [OpenMAIC](https://github.com/THU-MAIC/OpenMAIC)
- [ClassBuild](https://github.com/jtangen/classbuild)
- [Code2Video](https://github.com/showlab/Code2Video)
- [Math-To-Manim](https://github.com/HarleyCoops/Math-To-Manim)
- [Manim Community](https://github.com/ManimCommunity/manim)
- [Motion Canvas](https://github.com/motion-canvas/motion-canvas)
- [Mermaid](https://github.com/mermaid-js/mermaid)
- [Excalidraw](https://github.com/excalidraw/excalidraw)
- [Vega-Lite](https://github.com/vega/vega-lite)
- [Apache ECharts](https://github.com/apache/echarts)
- [Three.js](https://github.com/mrdoob/three.js)
- [H5P PHP Library](https://github.com/h5p/h5p-php-library)

### 模型与商业 API

- [CosyVoice](https://github.com/FunAudioLLM/CosyVoice)
- [Wan2.2](https://github.com/Wan-Video/Wan2.2)
- [LTX-2](https://github.com/Lightricks/LTX-2)
- [HunyuanVideo](https://github.com/Tencent-Hunyuan/HunyuanVideo)
- [Remotion License](https://www.remotion.dev/license)
- [OpenAI Image Generation](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI Video Generation](https://developers.openai.com/api/docs/guides/video-generation)
- [OpenAI Text-to-Speech](https://developers.openai.com/api/docs/guides/text-to-speech)
- [Google Veo](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/overview)
- [Runway API Pricing](https://docs.dev.runwayml.com/guides/pricing/)
- [Adobe Firefly Services](https://developer.adobe.com/firefly-services/docs/firefly-api/api/)
- [ElevenLabs Dubbing](https://elevenlabs.io/docs/overview/capabilities/dubbing)
- [HeyGen Avatar API](https://developers.heygen.com/reference/create-avatar)

### 教学效果、评测与无障碍

- [Multimedia Learning 原则综述章节](https://doi.org/10.1017/CBO9781139547369.015)
- [Learning Styles: Concepts and Evidence](https://doi.org/10.1111/j.1539-6053.2009.01038.x)
- [EduVideoBench](https://arxiv.org/abs/2605.26918)
- [PhyEduVideo](https://arxiv.org/abs/2601.00943)
- [Equation-to-Visual Generation for Early Arithmetic](https://arxiv.org/abs/2605.31212)
- [AI-generated and human-made instructional video comparison](https://doi.org/10.1016/j.compedu.2024.105164)
- [AI avatar video pilot study](https://doi.org/10.2196/89277)
- [W3C Audio and Video Media Accessibility](https://www.w3.org/WAI/media/av/)

> 注：开源许可证、商业 API 能力和价格均可能变化。本文记录的是 2026-07-15 调研时点的判断；进入实现和发布前必须重新核验具体版本、依赖树和服务条款。
