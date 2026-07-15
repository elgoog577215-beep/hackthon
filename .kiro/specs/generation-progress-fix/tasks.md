# 实现计划：课程生成进度显示修复

## 概述

修复三处联动缺陷：后端不存储节点计数、WebSocket 广播消息类型错误、前端模板读取 store 引用不清晰。

## 任务

- [x] 1. 修复后端节点计数存储（`backend/task_manager.py`）
  - 在 `_update_task_status` 方法签名中增加可选参数 `completed_nodes: int = None` 和 `total_nodes: int = None`
  - 在方法体内，当参数不为 None 时写入 `task["completed_nodes"]` 和 `task["total_nodes"]`
  - 在 `_process_task` 中，每次调用 `_execute_batch_actions` 前，从 `progress_info` 取 `completed`/`total` 并传入 `_update_task_status`
  - _需求：后端 task dict 必须持有最新节点计数，供广播器读取_

- [x] 2. 修复 WebSocket 广播消息类型及 payload（`backend/main.py`）
  - 找到 `task_update_broadcaster` 函数中的 `broadcast_task_update` 调用
  - 将消息类型从 `"task_update"` 改为 `"progress_update"`
  - 在 payload 中补充 `"completedNodes": task.get("completed_nodes", 0)` 和 `"totalNodes": task.get("total_nodes", 0)`
  - _需求：前端 `handleProgressUpdate` 只处理 `progress_update` 类型；payload 必须含节点计数字段_

  - [x]* 2.1 为广播 payload 写属性测试
    - **属性 1：completedNodes ≤ totalNodes 始终成立**
    - **验证：正确性属性第 1 条**

- [x] 3. 修复前端模板 store 引用（`frontend/src/components/CourseTree.vue`）
  - 找到显示节点计数的模板行（读 `courseStore.taskProgress[...]`）
  - 改为直接读 `genStore.taskProgress[courseStore.currentCourseId]`
  - 确认 `genStore` 已在该组件中 import（设计文档确认已 import）
  - _需求：消除通过 getter 代理的间接引用，使数据来源清晰可追踪_

- [x] 4. 清理死代码
  - 删除 `frontend/src/components/StatusBar.vue`（孤儿组件，无任何 import）
  - 删除 `frontend/src/stores/generation.ts` 中的 `pauseBackendTask` 和 `resumeBackendTask` 方法（调用不存在的 REST 端点）
  - 修改 `pauseTask` 方法：移除 `if (task.backendTaskId) { this.pauseBackendTask(courseId); return }` 分支
  - 修改 `startTask` 方法：移除 `if (task.backendTaskId) { this.resumeBackendTask(courseId); return }` 分支
  - _需求：消除死代码路径，避免未来误触发 404_

- [x] 5. 最终检查点
  - 确认所有改动均已落地，前端无类型错误，如有疑问请告知用户。

## 备注

- 标有 `*` 的子任务为可选项，可跳过以加快交付
