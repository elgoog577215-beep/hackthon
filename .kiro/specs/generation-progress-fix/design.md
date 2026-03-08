# 课程生成进度显示修复 — 技术设计

## 问题诊断

### Bug 1：节点计数始终 0/0

**位置**：`frontend/src/components/CourseTree.vue` 第 327 行

```html
{{ courseStore.taskProgress[courseId]?.completedNodes || 0 }}
/
{{ courseStore.taskProgress[courseId]?.totalNodes || 0 }} 节点
```

**根因**：`taskProgress` 定义在 `generation.ts` 的 `useGenerationStore` 里，但模板读的是 `courseStore.taskProgress`。`courseStore` 通过 getter 代理了这个字段（`course.ts` 第 998 行），所以引用本身不报错，但 `taskProgress[courseId]` 永远是 `undefined`——因为后端 WebSocket 广播的 `task_update` 消息从不包含 `completedNodes`/`totalNodes` 字段，`handleProgressUpdate` 从未被触发过。

**百分比能显示的原因**：进度条读的是 `genStore.getTask(courseId)?.progress`，这个值通过 `handleTaskUpdate` 从 `task_update` 消息的 `progress` 字段更新，路径不同，所以有值。

### Bug 2：无"当前正在生成节点"文字

`task_update` 消息里有 `currentNodeName` 字段，`handleTaskUpdate` 也会把它写入 `task.currentStep`，但 `CourseTree` 里的进度面板显示的是 `task.currentStep`，这部分实际上已经在工作——只是 `completedNodes/totalNodes` 的缺失让整体进度信息不完整。

---

## 数据流现状

```
TaskManager._update_task_status()
    存储字段: status, progress, message, current_node_name
    ❌ 未存储: completed_nodes, total_nodes

task_update_broadcaster() [每 0.5s 轮询]
    广播类型: "task_update"
    payload: { taskId, courseId, status, progress, currentNodeName, message }
    ❌ 缺失: completedNodes, totalNodes
    ❌ 类型错误: 应为 "progress_update" 才能触发前端 handleProgressUpdate

前端 useTaskWebSocket.handleProgressUpdate()
    接收: completedNodes, totalNodes → 写入 genStore.taskProgress[courseId]
    ✅ 逻辑已就位，但从未被触发

CourseTree.vue 进度面板
    读取: courseStore.taskProgress[courseId]  ← 代理到 genStore.taskProgress
    ✅ 引用路径正确（通过 getter 代理）
    ❌ 数据永远为空，因为上游从不填充
```

---

## 修复方案

### 原则

- 后端是数据权威：`TaskManager` 已知道精确的 `completed`/`total` 节点数，应由后端推送
- 前端接收逻辑已就位，只需后端补发字段
- 最小改动：不引入新接口，复用现有 WebSocket 消息类型

### 改动点

#### 1. `backend/task_manager.py` — 在 task dict 中存储节点计数

`_update_task_status` 方法增加可选参数 `completed_nodes` 和 `total_nodes`：

```python
def _update_task_status(self, task_id: str, status: str,
                        message: str = None, progress: int = None,
                        current_node_name: str = None,
                        completed_nodes: int = None,   # 新增
                        total_nodes: int = None):       # 新增
    with self.lock:
        task = self.tasks.get(task_id)
        if not task:
            return
        task["status"] = status
        task["updated_at"] = datetime.now().isoformat()
        if message is not None:
            task["message"] = message
        if progress is not None:
            task["progress"] = progress
        if current_node_name is not None:
            task["current_node_name"] = current_node_name
        if completed_nodes is not None:         # 新增
            task["completed_nodes"] = completed_nodes
        if total_nodes is not None:             # 新增
            task["total_nodes"] = total_nodes
        self.save_tasks()
```

在 `_process_task` 调用 `_execute_batch_actions` 之前，用 `progress_info` 更新节点计数：

```python
# _process_task 中，execute_batch_actions 之前
self._update_task_status(
    task_id, "running",
    completed_nodes=progress_info["completed"],
    total_nodes=progress_info["total"]
)
```

#### 2. `backend/main.py` — 广播时携带节点计数，使用正确消息类型

`task_update_broadcaster` 中，将广播类型从 `"task_update"` 改为 `"progress_update"`，并补充节点计数字段：

```python
await ws_manager.broadcast_task_update(
    task_id, "progress_update",          # 改为 progress_update
    {
        "taskId": task_id,
        "courseId": task.get("course_id"),
        "status": task.get("status"),
        "progress": task.get("progress"),
        "currentNodeName": task.get("current_node_name"),
        "completedNodes": task.get("completed_nodes", 0),   # 新增
        "totalNodes": task.get("total_nodes", 0),           # 新增
        "message": task.get("message")
    }
)
```

> 注意：`progress_update` 类型会触发前端 `handleProgressUpdate`，它同时更新 `task.progress`、`task.currentStep` 和 `genStore.taskProgress[courseId]`，覆盖了原来 `handleTaskUpdate` 的功能，所以可以安全替换。

#### 3. `frontend/src/components/CourseTree.vue` — 确认 store 引用正确

第 327 行当前读 `courseStore.taskProgress`，通过 getter 代理到 `genStore.taskProgress`，引用路径实际上是正确的。但为了代码清晰，建议直接读 `genStore.taskProgress`（CourseTree 已经 import 了 `genStore`）：

```html
<!-- 修改前 -->
{{ courseStore.taskProgress[courseStore.currentCourseId]?.completedNodes || 0 }}
/{{ courseStore.taskProgress[courseStore.currentCourseId]?.totalNodes || 0 }} 节点

<!-- 修改后 -->
{{ genStore.taskProgress[courseStore.currentCourseId]?.completedNodes || 0 }}
/{{ genStore.taskProgress[courseStore.currentCourseId]?.totalNodes || 0 }} 节点
```

---

## 完整数据流（修复后）

```
TaskManager._analyze_course_structure()
    → 返回 progress_info = { completed: N, total: M, phase: "..." }

TaskManager._process_task()
    → _update_task_status(..., completed_nodes=N, total_nodes=M,
                           current_node_name="正在生成: 1.2 核心原理")
    → task dict: { progress: 45, completed_nodes: 9, total_nodes: 20,
                   current_node_name: "1.2 核心原理" }

task_update_broadcaster() [每 0.5s]
    → 检测到状态变化
    → broadcast "progress_update" {
        progress: 45,
        completedNodes: 9,
        totalNodes: 20,
        currentNodeName: "1.2 核心原理"
      }

useTaskWebSocket.handleProgressUpdate()
    → task.progress = 45
    → task.currentStep = "1.2 核心原理"
    → genStore.taskProgress[courseId] = {
        percentage: 45,
        completedNodes: 9,
        totalNodes: 20,
        currentNodeName: "1.2 核心原理"
      }

CourseTree.vue 进度面板
    → 进度条宽度: 45%
    → 节点计数: "9/20 节点"
    → 当前节点: "1.2 核心原理"  ← task.currentStep
```

---

## 不在本次范围内

- 旧的前端队列系统（`processQueue` / `addToQueue` 等）保持现状，不删除也不修改
- `StatusBar.vue` 的队列显示逻辑不变（它显示的是旧队列的 `QueueItem`，与本次修复无关）
- `TaskManagerPanel.vue` 的进度条已经正确读取 `task.progress`，不需要改动

---

## 正确性属性

- 节点计数 `completedNodes ≤ totalNodes` 始终成立（由 `_analyze_course_structure` 保证）
- 任务完成时 `progress = 100`，`completedNodes = totalNodes`
- 任务暂停/取消时，最后一次广播的节点计数保持不变（不归零）


---

## 暂停按钮现状分析

### 有效路径（TaskManagerPanel）

`TaskManagerPanel.vue` → `handlePause(courseId)` → `wsPauseTask(courseId)` → WebSocket `pause_task` 命令 → `main.py` → `task_manager.pause_task(task_id)` → task status 改为 `"paused"`

这条路径**可以工作**。

### 死代码路径（StatusBar）

`StatusBar.vue` 定义了 `toggle-pause` emit，但该组件**没有任何地方 import 或使用**，是孤儿组件。不需要修复，也不需要删除（超出本次范围）。

### 双路径冲突（generation.ts pauseBackendTask）

`generation.ts` 的 `pauseTask` 在有 `backendTaskId` 时走 `pauseBackendTask`，后者调用 `http.post('/api/tasks/{id}/pause')`，但 `main.py` 里**不存在这个 REST 端点**，会 404。

然而 `TaskManagerPanel` 直接调用 `wsPauseTask`（绕过了 `generation.ts` 的 `pauseTask`），所以实际使用中不会触发这个死路径。

### 暂停中断粒度问题（已知限制，不在本次修复范围）

`_process_task` 只在 `_execute_batch_actions` 调用前检查一次暂停状态。一旦进入 `asyncio.gather`，已经发出的 LLM 请求无法被中断，需要等当前 batch 完成后下一轮才会生效。这是已知的设计限制，不在本次修复范围内。

### resume 后状态短暂显示 pending

`resume_task` 将 task status 改为 `"pending"`，前端收到 `task_update` 后 `task.status = 'pending'`，进度条可能短暂消失（因为 `TaskProgressBar` 只对 `running`/`paused` 显示进度）。这是轻微 UX 问题，不在本次修复范围内。
