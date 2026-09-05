# inquiry / exam 开放条件清单

> 文档状态：2026-08-05 启动材料，不是设计，也不是当前产品或实施真源<br>
> 当前产品事实：[产品状态](../产品状态.md)｜当前代码边界：[系统架构](../系统架构.md)<br>
> 上位规格：`build-structured-adaptive-course-ai`（活动 OpenSpec，未归档）

本文只回答一件事：**问题探究（inquiry）与考试冲刺（exam）在开放之前，必须先有什么。**
不写规划器怎么做——那是开放决策通过之后才动笔的设计。

## 1. 为什么现在不开放

2026-08-05 决策：**保持禁用**。理由三条：

1. 两种类型的字段、契约、前端表单类型都已就位，放开只需改一行
   `ENABLED_COURSE_TYPES`。但那样一来它们会直接复用 systematic 的通用规划器，
   正是现行规格点名禁止的"静默退化为系统课程"。
2. 这种缺陷是**用到一半才会发现**的：老师选了考试冲刺，拿到的却是普通系统课程，
   直到看目录才察觉。教师验收阶段不能带着这种缺陷进场。
3. 两个专用规划器连设计都不存在，是以周计的工作量，会直接挤掉教案生成与
   生成过程可视化的时间。

规格侧的原始约束（`build-structured-adaptive-course-ai.md:2387-2390`）：

> 第一期能力表 MUST 只将 `systematic` 和 `project` 标记为可用。`inquiry` 与 `exam`
> MUST 保留稳定枚举、类型化字段和规划器接口，但在专用规划器未完成前 MUST NOT
> 创建课程外壳、生成任务或普通系统课程替代品。

同文 `:2386`：「协议存在 MUST NOT 被解释为对应规划器已经开放。」

## 2. 现状盘点：已经有的，和缺的

**已就位**（所以不要重做）：

| 对象 | 位置 |
| --- | --- |
| 类型枚举与契约（planning_sequence / outline_requirements / completion_evidence） | `backend/course_type_contracts.py:67-88` |
| 意图模型 `InquiryCourseIntent` / `ExamCourseIntent` | `backend/models.py:191-206` |
| 按类型填默认值 | `backend/course_type_contracts.py:239-250` |
| 契约编译进生成 brief（四种类型共用一条链） | `backend/course_type_contracts.py:201-219` |
| 前端 TS 类型与表单类型定义 | `frontend/src/shared/prompt-config.ts:49-66` |
| 两道门禁 | `backend/routers/courses.py:148`（422）、`backend/task_manager.py:882`（`CourseTypeNotEnabled`） |

**缺的就是规划器本身**：目前只有 systematic 与 project 有真正改变目录组织方式的
规划路径；inquiry/exam 若放行，会落到通用路径上。

## 3. 开放前必须先有什么

### 3.1 两个专用规划器各自要覆盖的

判据统一为：**产出的目录必须无法用"把普通章节标题改写成该类型措辞"伪造出来。**

**问题探究（inquiry）** —— 契约已声明的推进顺序是
界定问题 → 拆解子问题 → 组织证据 → 检验解释 → 形成结论：

- 目录节点由核心问题与子问题推进，而不是带问号的普通章节
- 显式区分：已有认识 / 待验证假设 / 证据需求 / 阶段性结论
- 证据不足时能标注边界，而不是编一个确定结论
- 完成证据：学习者形成可追溯证据、能说明边界的结论

**考试冲刺（exam）** —— 契约已声明的推进顺序是
考试范围 → 当前准备度 → 薄弱点 → 复习优先级 → 模拟验证：

- 按考纲覆盖、剩余时间、薄弱程度决定优先级与配时
- **不得为形式完整而平均分配学习时间**（这是与 systematic 最容易混同之处）
- 每阶段含复习目标、典型任务、检查方式
- 完成证据：分阶段检查与模拟任务达到目标准备度

### 3.2 要一并解决的既有不一致

开放前必须先对齐，否则一放行就会暴露：

1. **必填口径前后端不一致**：TS 把 `core_question`、`exam_name` 定义为必填
   （`prompt-config.ts:52,61`），后端 Pydantic 两者都 `default=""`
   （`models.py:194,203`）。禁用状态下无人触发，开放即暴露。
2. **exam 少一个规格要求的字段**：规格要求 exam 含"考试名称、日期、考纲范围、
   当前准备度和**备考资料**"（`build-structured-adaptive-course-ai.md:2384`），
   `ExamCourseIntent` 目前只有前四个，缺备考资料。
3. **inquiry 的兼容回填指向 systematic**：
   `_TYPE_TO_PURPOSE[inquiry] = "systematic"`（`course_type_contracts.py:107`）。
   这是新类型→旧字段的历史兼容方向，但与"MUST NOT 静默改用 systematic"
   字面冲突，开放前需确认这个回填不会让 inquiry 走进 systematic 的分支。
4. **前端仍缺两种类型的意图表单**：`CourseGenerationDialog.vue` 目前只有
   systematic 与 project 两套表单分支，inquiry/exam 的字段无处填写。

### 3.3 要改的门禁与测试

放开时**这些必须同一次改完**，否则测试会以"必须禁用"的名义挡住：

| 位置 | 现在锁的是什么 | 开放时怎么办 |
| --- | --- | --- |
| `backend/course_type_contracts.py:25-28` | `ENABLED_COURSE_TYPES` 只含两种 | 按发布矩阵逐个加入，不要一次全开 |
| `backend/tests/test_course_type_contracts.py:168-184` | 参数化 inquiry/exam，断言 422 且不建任务 | 改为断言"未开放的那些类型"仍被拒；已开放的走正常路径 |
| `backend/tests/test_course_type_contracts.py:187-195` | `CourseTypeNotEnabled.code` | 同上 |
| `frontend/.../course-generation-dialog.test.ts:174-175` | 4 张卡、恰好 2 张 disabled | 数量随发布矩阵调整 |
| `frontend/src/components/CourseGenerationDialog.vue:419-448` | `available` 硬编码 | 建议改为读服务端发布矩阵，避免前后端各写一份 |

注：当前"已开放集合"在**后端集合、路由判断、前端 available 标记**三处各写一遍。
开放前把它收敛成一处服务端投影，可以少一类前后端不同步的缺陷。

### 3.4 需要的验收场景

现有场景全是**拒绝路径**（`build-structured-adaptive-course-ai.md:2405-2410`、
`:2497-2501`），开放前需要补正向场景，至少包括：

1. 选 inquiry 提交合法核心问题 → 目录由问题与子问题推进，且区分假设与结论
2. 选 exam 提交考纲与剩余时间 → 优先级与配时按薄弱程度倾斜，不平均分配
3. **反伪造**：同一主题分别用 systematic 与 inquiry/exam 生成 → 目录结构有实质
   差异，不能只是措辞不同（这是最关键的一条，直接对应本次不放开的理由）
4. 两种类型走完整链路：目录确认门、教案、正文、质量门、发布门均不被绕过
5. 失败恢复：中断后从检查点继续，不重做已完成单元
6. 中英文 × 桌面/移动的真实页面验收（含新增的意图表单）

## 4. 建议启动顺序

在 9.1 教师验收之后：

```text
对齐 3.2 的四处不一致（小，先做，能独立验证）
→ 收敛"已开放集合"为服务端投影（3.3 注）
→ 选一种类型做专用规划器（建议 exam：判据更客观，配时与优先级可量化）
→ 补 3.4 的正向与反伪造验收场景
→ 通过后再开第二种
```

不要两种类型同时开工：反伪造判据需要先在一种类型上验证有效，才谈得上复用。
