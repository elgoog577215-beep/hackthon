## 1. 现状扫描

- [x] 1.1 扫描 `LearningStats`、`LearnerProfile`、`TutorActionCard`、`SideAIPanel`、`tutorStore`、`profileStore`、`learningStore` 的职责重叠。
- [x] 1.2 明确合并原则：`TeachingDecision` 负责下一步建议，统计负责轨迹，画像负责解释，AI 助手负责对话。

## 2. 统一学习洞察模型

- [x] 2.1 新增轻量前端组合模块，统一产出行动、状态摘要、证据、轨迹提示。
- [x] 2.2 在 `tutorStore` 中暴露统一洞察 computed，避免组件各自解析后端状态。

## 3. 组件收敛

- [x] 3.1 改造 `TutorActionCard`，优先使用统一洞察的主行动。
- [x] 3.2 改造 `LearnerProfile`，展示长期画像、动态证据和判断依据，不承担主行动入口。
- [x] 3.3 改造 `LearningStats`，保留轨迹数据，移除本地规则式建议主导权。
- [x] 3.4 改造 `SideAIPanel`，使用轻量状态摘要替代完整画像嵌入。

## 4. 验证与提交

- [x] 4.1 补充或更新前端测试，覆盖统一洞察模型。
- [x] 4.2 运行前端测试、构建、OpenSpec 校验、后端相关测试和 `git diff --check`。
- [x] 4.3 提交功能改动，完成后归档 OpenSpec 并单独提交归档。
