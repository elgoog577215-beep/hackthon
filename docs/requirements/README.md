# 需求与领域合同入口

> 文档状态：当前领域合同索引<br>
> 上位产品真源：[产品总蓝图](../product-blueprint.md)<br>
> 当前实施状态：[产品状态板](../product-status.md)

本文只负责把产品语义路由到当前有效的领域合同，不重复字段、场景、任务和完成度。

## 1. 稳定需求基线

| 合同 | 唯一职责 | 不负责 |
| --- | --- | --- |
| [产品总蓝图](../product-blueprint.md) | 产品定义、领域真源、核心闭环与不可违反边界 | 当前实现、字段细节、实施任务 |
| [整体开发需求与依赖路线图](./灵知整体开发需求与依赖路线图.md) | `P0-P6` 建设依赖、完成门和治理门禁 | 当前进度、每日任务 |
| [课程知识库结构与关系网络设计](./灵知课程知识库结构与关系网络设计.md) | 单课程知识实体、关系、绑定、生成和质量设计 | 当前实现完成度 |
| [D-05 任务可观察性](./d05-task-observability.md) | 课程生成与导入任务的用户阶段、阻断和恢复语义 | 后端内部阶段实现 |
| [通用题目生成评测](../evals/universal-question-generation.md) | 题目生成、私有解答、质量门、Runner 与发布指标 | 整体课程状态 |

## 2. 当前活动领域规格

结构化课程、知识、证据与课程生长由 [`build-structured-adaptive-course-ai`](../../openspec/changes/build-structured-adaptive-course-ai/) 维护：

- [课程文档命令](../../openspec/changes/build-structured-adaptive-course-ai/specs/course-document-model/spec.md)
- [课程生成一致性](../../openspec/changes/build-structured-adaptive-course-ai/specs/course-generation-coherence/spec.md)
- [课程知识基础设施](../../openspec/changes/build-structured-adaptive-course-ai/specs/subject-knowledge-infrastructure/spec.md)
- [课程知识生长](../../openspec/changes/build-structured-adaptive-course-ai/specs/course-knowledge-growth/spec.md)
- [学习证据与适应判断](../../openspec/changes/build-structured-adaptive-course-ai/specs/learning-evidence-adaptation/spec.md)
- [个人课程生长](../../openspec/changes/build-structured-adaptive-course-ai/specs/personal-course-evolution/spec.md)
- [候选审阅](../../openspec/changes/build-structured-adaptive-course-ai/specs/adaptive-change-review/spec.md)
- [AI 老师动作](../../openspec/changes/build-structured-adaptive-course-ai/specs/ai-teacher-action-protocol/spec.md)
- [学习者模型](../../openspec/changes/build-structured-adaptive-course-ai/specs/learner-model-state/spec.md)

结构化教案编辑由 [`upgrade-teaching-plan-workbench`](../../openspec/changes/upgrade-teaching-plan-workbench/) 维护：

- [教案工作台正式规格](../../openspec/changes/upgrade-teaching-plan-workbench/specs/teaching-plan-workbench/spec.md)

活动规格尚未完成的任务只在各自 `tasks.md` 勾选；完成并归档后，持续有效的能力进入 [`openspec/specs/`](../../openspec/specs/)。

## 3. 历史交接稿

[2026-07-15 AI 课程智能体产品与技术交接稿](../archive/requirements/2026-07-15-ai-course-agent-handoff.md) 保存了结构化同源与课程生长最初的完整设计。它使用 `CourseChangeSet`、“未来 PPT”等当时术语，已经被当前蓝图、`CourseEvolutionPlan` 和活动 OpenSpec 接管，不再是现行领域合同。

历史交接稿只用于理解决策来源，不用于新增接口、字段、任务或判断当前完成度。

## 4. 维护规则

1. 跨领域稳定产品语义进入蓝图，不在本目录复制。
2. 单领域长期设计可以保留在 `requirements/`，但不得维护当前进度和实施任务。
3. 具体字段、状态机、接口和验收场景优先进入活动 OpenSpec 的 `spec.md`。
4. 会议需求、录屏分镜、验收矩阵和一次性交接稿任务结束后移入 `acceptance/` 或 `archive/`。
5. 当前状态变化只更新产品状态板；历史原因只更新项目决策。
