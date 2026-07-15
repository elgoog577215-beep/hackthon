# 设计：统一恢复契约与故障矩阵

## 一、统一判断模型

恢复不是新的业务主链，而是对现有真源做对账：

```text
首次生成：GenerationJob + GenerationWorkspace + CourseDocument 外壳/发布回执
块级改写：BlockRegenerationCandidate + 当前 CourseDocument/CourseBlock 修订
```

前端不根据一个笼统的 `failed` 自行猜测动作。后端为生成任务返回 `recovery`：

```text
state: none | auto_resuming | manual_resume | quality_blocked | conflict | unavailable | completed
can_resume: boolean
reason: 用户可解释原因
checkpoint:
  phase
  completed_nodes / total_nodes
  draft_node_ids
  workspace_status
  updated_at
```

任务原有 `status / phase / progress` 继续表达执行状态，`recovery` 只表达恢复判断，不建立第二状态机。

## 二、首次生成恢复

### 重启对账顺序

1. 正式课程已经存在 `publish-generation:{job_id}` 回执：任务直接修正为完成，不再重新生成或发布。
2. 任务需要工作区但工作区缺失：标记为不可恢复，禁止显示无效重试。
3. 工作区存在且任务原状态为 `pending / running`：把中断中的节点恢复为 `pending`，保留 `node_content_draft` 与已完成节点，工作区和课程外壳改为恢复中，再重新入队。
4. `paused / failed / completed_with_warnings` 不自动入队；由恢复描述决定是否允许用户继续。

### 手动继续

- 重复点击继续必须幂等；已经排队或运行时只返回当前恢复状态。
- 继续时只重置 `generating / error` 且正文未完成的节点，保留完成节点和草稿。
- 工作区状态切回 `active`，课程外壳清理旧运行错误并标记 `resuming`。
- 如果只有确定性质量门未通过且没有失败节点，返回 `quality_blocked`，不做无意义的相同重放。

## 三、块候选恢复

### 调用模型前落盘

候选先以 `generating` 写入，记录目标修订、原块载荷、指令、动作、进程所有者和恢复信息，然后才调用模型。这样浏览器超时或进程终止后仍有可查询对象。

### 并发与重放

- `course_id + block_id + request_id` 仍决定唯一候选 ID。
- 第一个请求原子创建候选并获得生成权；并发重复请求只返回同一 `generating` 候选，不再调用模型。
- 模型异常写为 `generation_failed`；正式课程保持不变。
- 候选处于 `generating` 但所有者不是当前服务进程时，读取时修正为中断失败，允许显式重试。
- 重试沿用同一候选、指令与目标修订；若课程修订已变化，则转为 `stale`，不得再次生成或应用。

### 浏览器恢复

右侧 AI 老师打开目标块时读取该块当前修订上的最近候选：

- `ready / quality_failed / applied`：恢复预览和原状态。
- `generating`：显示生成中并短轮询。
- `generation_failed`：显示失败原因和“从此处重试”。
- `stale / rejected`：不冒充可继续候选，用户可发起新请求。

## 四、故障矩阵

| 故障 | 正式课程 | 隔离状态 | 用户动作 |
|---|---|---|---|
| 蓝图或正文模型异常 | 空外壳不变 | 工作区保留检查点 | 从原任务继续 |
| 服务在正文流中终止 | 空外壳不变 | 草稿保留，中断节点回到待生成 | 重启后自动恢复 |
| 发布后、任务终态前终止 | 已发布课程不变 | 发布回执存在 | 重启对账为完成 |
| 仅质量门失败 | 空外壳不变 | 工作区和报告保留 | 进入第 10 项优化，不盲目重放 |
| 块候选模型异常 | 当前块不变 | `generation_failed` 候选保留 | 右栏原位重试 |
| 同一块候选并发请求 | 当前块不变 | 只有一个候选获得生成权 | 其他请求复用状态 |
| 候选生成后课程变化 | 新课程内容不变 | 候选转为 `stale` | 重新基于当前块生成 |
| 浏览器断网或刷新 | 服务端状态不变 | 任务/候选可重新读取 | 联网后自动刷新 |

## 五、验收边界

- 自动化覆盖重启对账、草稿保留、重复继续、工作区丢失、质量阻塞、候选并发去重、中断找回和重试。
- 前端覆盖任务恢复描述、无效重试隐藏、候选刷新恢复和失败重试。
- 真实验收至少执行一次后端进程强制终止与重启，并确认同一任务 ID、同一课程 ID、无半成品发布。
- 浏览器验收断网/恢复后任务中心和右侧候选状态能够重新读取，页面不新增独立恢复入口。
