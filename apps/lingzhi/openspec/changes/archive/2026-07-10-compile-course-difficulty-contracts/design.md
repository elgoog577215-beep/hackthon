# 设计：课程难度编译与验证

## 核心模型

`DifficultyProfile` 不描述“写多长”，而是一份学习能力合同：

```text
DifficultyProfile
├─ EntryRequirement   进入课程前需要的知识、技能与独立性
├─ ChallengeProfile   抽象、推理、整合、任务复杂度与迁移距离
├─ SupportProfile     支架强度、节奏粒度和反馈频率
└─ MasteryContract    正确性、独立性、解释、执行与迁移标准
```

对外三等级不变：

| API 值 | 产品名 | 核心能力 |
|---|---|---|
| `beginner` | 入门 | 在明确支架下理解并完成标准任务 |
| `intermediate` | 进阶 | 独立分析并解决典型问题 |
| `advanced` | 高阶 | 处理开放约束、权衡与远迁移 |

## 共享维度与学科翻译

八种教学模式共享一组 1-5 级维度：

- 挑战维度：`prerequisite_load`、`abstraction`、`reasoning_depth`、`integration_scope`、`task_complexity`、`transfer_distance`。
- 支持维度：`scaffold_intensity`、`pacing_granularity`、`feedback_frequency`。
- 掌握维度：`accuracy`、`independence`、`explanation`、`execution`、`transfer`。

`SubjectDifficultyAdapter` 根据主教学模式将维度翻译为可观察任务。例如，高阶数学要求可包含带条件的证明和非例构造；高阶编程要求可包含多约束设计、故障定位和取舍说明。辅模式只能注入完成主任务必需的表现证据。

## 生成链路

```text
CourseGenerationRequest
  -> DifficultyCompiler
  -> DifficultyProfile
  -> SubjectDifficultyAdapter
  -> DifficultyGapAssessment
  -> AdaptationDecision
  -> CourseDifficultyCurve
  -> NodeDifficultyContract
  -> 蓝图 / 正文 / 练习
  -> DifficultyAlignmentReport
```

`CourseService` 继续是编排门面，`TaskManager` 只负责任务生命周期与调度。新模块 `course_difficulty.py` 是确定性领域逻辑，不调用大模型。

## 课程难度曲线

曲线使用锯齿型节奏，而非每节线性增难：

```text
桥接 -> 基础 -> 示范 -> 引导练习 -> 独立任务
     -> 整合 -> 迁移 -> 检查点 -> 综合成果
```

一般规则：

- 挑战总体上升，支架总体下降，掌握证据逐步加强。
- 相邻节点挑战级差默认不超过 2。
- 新概念负荷与任务复杂度不得在同一节同时跃升。
- 课程可以在新的能力波次里重新提高支架，所以曲线不是单调直线。

`NodeDifficultyContract` 至少保存节点角色、挑战维度、支持维度、掌握证据、学科任务、伪难度禁止项和契约版本。

## 就绪度差距

系统分开三个概念：当前就绪度、课程入口要求、目标难度。

- 差距 0：直接进入。
- 差距 1：节点内桥接。
- 差距 2：课程前置单元。
- 差距 3 以上：拆成基础课与目标课。
- 高于入口要求：压缩已知基础，保留检查点。
- 未知：保存 `diagnostic_required`，生成简短诊断或前置检查，不假定用户掌握度。

本次接口没有增加强制诊断表单，因此编译器仅使用明确说明的学习对象、用户要求和授权画像摘要。它不读取动态学习事件，也不静默改变目标难度。

## 质量闸门

难度验证分三层：

1. 确定性硬闸门：契约完整性、维度范围、曲线跳变、入口适配、任务与教学模式一致。
2. 内容对齐检查：正文是否包含契约要求的学习者行动、支架、反馈和掌握证据。
3. 跨等级基准：对同一主题和教学模式，校验 `beginner < intermediate < advanced` 的挑战与独立性，以及相反方向的支架强度。

硬失败不得被平均分掩盖。内容闸门需显式拒绝伪难度：只增加术语、长度、公式、代码、题量，或者只删除提示、跳过前置知识。

## 局部重写

用户重写已有节点时，默认继承持久化的 `NodeDifficultyContract`。只有用户明确选择新目标难度时才重编译新版本；不得因为请求字段缺失而默认为 `advanced`。
