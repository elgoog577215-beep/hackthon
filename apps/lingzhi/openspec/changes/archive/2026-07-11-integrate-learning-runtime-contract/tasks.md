# 任务

## 1. 共享契约与聚合投影

- [x] 1.1 定义 LearningContextRef、LearningTaskRef 和兼容归一化函数
- [x] 1.2 升级 LearningEvent V6 顶层任务与诊断引用
- [x] 1.3 实现无存储的 LearningRuntime 聚合投影与稳定修订向量
- [x] 1.4 新增运行时读取 API 并注册路由

## 2. 后端消费者统一

- [x] 2.1 让进度与连续性使用同一批聚合输入
- [x] 2.2 让掌握清单读取 LearningProgress criterion_states
- [x] 2.3 保留旧正式作答事件与 question_revision_id 只读兼容
- [x] 2.4 覆盖版本变化、活动任务、记录和诊断摘要测试

## 3. 前端运行时协调

- [x] 3.1 将 learningProgress Store 升级为带请求序号的 loadRuntime
- [x] 3.2 删除 CourseView 猜测式 watcher，改为领域写操作主动刷新
- [x] 3.3 升级 LearningSnapshot 任务引用并打通练习、诊断与阅读退回
- [x] 3.4 按 task_ref 精确恢复指定 Attempt 或诊断任务
- [x] 3.5 版本变化后统一刷新课程、快照和学习运行时

## 4. 清理与兼容

- [x] 4.1 前端正式练习类型以 task_revision_id 为主，question_revision_id 降为可选兼容
- [x] 4.2 删除 action_type.includes 推断式路由和重复 loadContinuation 调用
- [x] 4.3 保持历史快照、事件和旧课程读取兼容，不恢复旧真源

## 5. 验证与收束

- [x] 5.1 完成后端聚合、契约、版本与消费者测试
- [x] 5.2 完成前端运行时刷新、精确恢复和快照任务测试
- [x] 5.3 运行全量测试、构建、OpenSpec 严格校验和差异检查
- [x] 5.4 用真实课程验收阅读、记录、快照与章节动作，用契约测试覆盖练习、诊断恢复和版本变化
- [x] 5.5 更新产品蓝图和项目决策、归档 OpenSpec、提交并推送
