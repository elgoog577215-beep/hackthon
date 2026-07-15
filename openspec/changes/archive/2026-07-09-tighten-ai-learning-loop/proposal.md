## Why

当前 AI 能力已经有资料增强课程生成、学习事件账本、学习者状态、教学决策和结构化问答事件流，但这些能力还没有形成稳定闭环。前端问答仍主要调用旧文本流 `/api/ask` 并手动解析 `---METADATA---`，课程质量事件没有回流到课程报告，用户身份仍大量落到默认用户，`TaskManager._process_node` 也继续承担过多职责。

本变更要把现有能力收口成最小闭环：资料增强课程生成产生课程，学习行为进入事件账本，事件聚合为学习状态和教学决策，AI 老师读取统一上下文，AI 输出质量再回流到课程迭代信号。实现上不新增大 Agent、向量库、平行画像或第二套课程生成服务。

## What Changes

- 前端默认问答协议切换到 `/api/ask_events`，正文、最终答案和 metadata 分事件处理。
- 后端引入最小 `X-User-Id` 读取能力，让问答、学习事件和 AI Learning Context 使用同一用户标识。
- 课程质量报告读取已有 `ai_output_quality_assessed` 事件，输出弱节点、质量概览和推荐修复动作。
- 继续把 `build_ai_learning_context` 作为 AI 老师统一上下文入口，不新增平行用户画像或记忆系统。
- 局部瘦身 `TaskManager._process_node`，抽出节点落盘和完成事件推送，不改变任务协议。
- 保留 `/api/ask` 兼容接口和 `/api/course-generation/generate` 唯一课程生成入口。

## Impact

- 影响前端问答 store、后端问答路由、学习事件记录、课程质量报告、任务管理和少量测试。
- 不改变课程生成主入口，不恢复旧 `/api/generate_course`。
- 不引入新依赖，不新增用户表、登录系统或新编排框架。
