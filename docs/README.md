# 灵知项目文档入口

本文只负责说明文档职责和阅读顺序，不保存产品进度或第二份项目真相。

## 1. 当前正式真源

- [产品总蓝图](./product-blueprint.md)：当前产品语义的最高优先级真源，也是唯一产品实施进度板。
- [课程生成与 AI 老师后端链路](./architecture/course-generation.md)：记录当前生产代码的真实链路；与蓝图冲突时，以蓝图的产品边界为准，以代码和真实验证判断实现状态。
- [`build-structured-adaptive-course-ai`](../openspec/changes/build-structured-adaptive-course-ai/)：当前仍在实施的结构化课程 OpenSpec。任务完成并通过验证后应归档，不在其他文档维护平行任务表。
- [`fix-mermaid-rendering-pipeline`](../openspec/changes/fix-mermaid-rendering-pipeline/)：Mermaid 渲染收束项。真实课程页仍存在旧导入标题标记泄漏，且缺少规格所述的导入回归用例，完成视觉门禁与回归补齐前不得归档。

## 2. 开发与验收入口

- [项目 README](../README.md)：本地安装、启动、AI 提供方配置和技术栈。
- [课程生成到学习闭环验收矩阵](./course-learning-full-chain-acceptance.md)：纵向链路验收记录；大型结构化课程 OpenSpec 收束后转入归档。
- [通用题目生成评测](./evals/universal-question-generation.md)：题目生成能力与回归指标。
- [外部 PPTX 再导入评估](./architecture/external-pptx-reimport-evaluation.md)：外部课件回导边界与实施门槛。

## 3. 专题需求、演示与研究

- `requirements/`：已确认的专题需求、交接基线和演示分镜。带日期的文件只代表当时需求，不自动成为当前产品真源。
- `research/`：外部调研、竞品分析和融合方案。研究结论必须回写产品蓝图或 OpenSpec 后，才会改变正式产品方向。
- [演示触发路径](./demo-path.md)：当前大会录制操作依据；录制结束后与对应分镜一起归档。

## 4. 历史归档

- `archive/`：已完成、被取代或只保留追溯价值的普通项目文档。
- `../openspec/changes/archive/`：已收束的 OpenSpec 历史记录，不属于当前待办。

归档文档保留原始事实和版本背景，但不得继续写“当前状态”或成为新实现依据。

## 5. 维护规则

1. 当前产品定义和整体进度只更新 `product-blueprint.md`。
2. 当前实现事实更新对应架构文档；高影响实施更新有效 OpenSpec。
3. 调研、验收、会议和 Design QA 使用独立专题文档，任务结束后归档。
4. 新文档必须说明状态、日期、上位真源和适用范围；无法说明职责时，优先修改现有文档。
5. 不在根目录追加临时报告，不用日期文档覆盖正式真源，不把聊天结论维护成第二份进度表。
