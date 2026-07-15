## 1. 规格

- [x] 1.1 写明问答协议、用户身份、学习上下文、质量反馈和任务管理边界

## 2. 问答协议

- [x] 2.1 将前端 `askQuestion` 默认请求切到 `/api/ask_events`
- [x] 2.2 前端按 `answer`、`final_answer`、`metadata` 事件更新正文、最终答案和 AI 笔记
- [x] 2.3 保留 `/api/ask` 兼容行为

## 3. 用户身份

- [x] 3.1 新增最小 `X-User-Id` 读取函数
- [x] 3.2 问答事件、回答完成事件和 AI Learning Context 使用同一 `user_id`
- [x] 3.3 未传用户时继续回退默认用户

## 4. 质量反馈

- [x] 4.1 聚合 `ai_output_quality_assessed` 学习事件
- [x] 4.2 将弱节点、质量概览和推荐修复动作写入 `GenerationQualityReport`

## 5. 任务管理

- [x] 5.1 从 `TaskManager._process_node` 抽出节点内容落盘 helper
- [x] 5.2 从 `TaskManager._process_node` 抽出节点完成推送 helper
- [x] 5.3 保持调度、重试、WebSocket payload 和落盘行为不变

## 6. 模型路由

- [x] 6.1 对课程大纲、弱点补救和质量修复保留强模型选择入口
- [x] 6.2 普通正文生成继续使用当前低延迟路径

## 7. 验证

- [x] 7.1 补后端测试：`/api/ask_events`、`X-User-Id`、质量事件回流、TaskManager helper
- [x] 7.2 跑相关后端测试
- [x] 7.3 跑前端构建
- [x] 7.4 跑 `openspec validate --all`
- [x] 7.5 完成后归档 OpenSpec change
