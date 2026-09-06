## Context

课程正文仍以完整 Markdown 为真源，但生成链已经保留 `content_blocks` 兼容结构。前端连续阅读使用虚拟窗口，当前只在全局 `scrollTop` 和当前节点之间切换。服务端有 `LearningEvent` 追加账本，但事件不适合承载每次滚动产生的可覆盖状态。

本变更把课程使用状态拆成三类：

```text
CourseVersion / ContentBlockRevision：当前可学习资产
LearningSnapshot：可覆盖的恢复现场
LearningEvent：不可改写的历史事实
```

## Goals / Non-Goals

### Goals

- 同一课程在刷新、关闭页面和更换设备后恢复到同一语义内容。
- 课程版本变化后确定性说明锚点是否精确、更新、重映射或只能回退到节点。
- 本地缓存承担断网保护，服务端承担跨设备真源。
- 并发更新不静默覆盖，旧位置可幂等迁移。
- 为后续答案草稿、笔记草稿、未解决问题和补救现场预留受约束状态槽。

### Non-Goals

- 不在本变更中实现章节完成、掌握状态、错因诊断、补救或复习计划。
- 不把滚动事件逐条写入学习事件账本。
- 不解决多人共用同一用户 ID 的权限与账户系统。
- 不把 Markdown 强制重构为固定内容块编辑器。

## Domain Model

`ContentBlockRevision` 使用稳定 `block_id` 表示逻辑内容块，使用内容、标题、类型和父块计算 `block_revision_id`，使用规范化正文计算 `content_fingerprint`。课程版本与快照同时保存这些值；相同内容可跨课程版本复用修订。

`LearningSnapshot` 使用 `(user_id, course_id)` 作为唯一当前现场，主要字段为：

- `snapshot_id`、`revision`、`schema_version`。
- `course_version_id`、`node_id`、`node_name`。
- `content_anchor`：块 ID、块修订、内容指纹、块类型、标题、块内比例和引用文本。
- `session`：会话 ID、开始时间、设备 ID。
- `task_state`：受限类型、对象 ID 和小型草稿元数据，暂不承载任意大对象。
- `interaction_state`：当前对话、问题或补救引用，首期可以为空。
- `fallback_scroll_top`、`activity_at`、`updated_at`。

仓库每个用户课程保存独立 JSON 文件，并使用进程锁、临时文件和 `os.replace` 原子写入。文件名只使用哈希键，避免用户或课程 ID 进入路径。

## API And Concurrency

- `GET /api/courses/{course_id}/learning-snapshot`：返回当前快照、当前课程版本和解析后的锚点；不存在时返回 `snapshot: null`。
- `PUT /api/courses/{course_id}/learning-snapshot`：请求携带 `expected_revision`。首次创建使用 0；已有修订不匹配时返回 409 和当前快照。
- `DELETE /api/courses/{course_id}/learning-snapshot`：显式清除当前现场，测试和用户重置使用；不删除历史事件。

前端收到 409 后比较 `activity_at`：远端更新较新则采用远端；本地活动较新则以新的远端 revision 重试一次。仍冲突时停止自动覆盖并保持本地缓存，等待下一次显式恢复或同步。

## Anchor Resolution

服务端对当前课程按以下顺序解析：

1. `block_id + block_revision_id` 同时匹配：`exact`。
2. `block_id` 匹配但修订变化：`updated_block`。
3. 内容指纹在同一节点或课程中唯一匹配：`fingerprint_remap`。
4. 节点仍存在：`node_fallback`。
5. 节点不存在：`course_fallback`，返回第一个可学习节点。

响应同时返回原锚点、解析锚点、当前课程版本和是否发生内容变化。前端不得自行使用标题模糊匹配冒充精确恢复。

## Frontend Flow

课程加载完成后，学习现场 store 先读取本地新缓存，再请求服务端。服务端快照存在时以并发规则合并；不存在时才读取旧 `learning_stats.lastReadPosition` 或 `scroll-pos-{courseId}` 建立迁移快照。

连续阅读滚动时，前端选择视口顶部最近的课程节点和带 `data-content-block-id` 的标题，计算当前块到下一块之间的相对比例。本地立即更新，服务端按防抖周期同步。`pagehide`、课程切换和页面进入后台时执行尽力刷新。

恢复时先扩展虚拟窗口并定位节点，再定位解析后的内容块，最后应用块内比例。没有块时回退节点；只有旧迁移位置时允许使用一次 `fallback_scroll_top`。

## Risks / Trade-offs

- 旧课程的内容块由 Markdown 标题投影，稳定性弱于原生块：通过稳定 block ID、内容指纹和明确回退状态降低风险，不宣称绝对精确。
- 文件仓库只支持单进程内强锁：原子文件和乐观 revision 可防止当前部署的并发覆盖；未来多进程部署需要替换仓库实现，但 API 契约保持不变。
- 高频滚动同步有写放大：本地即时、服务端防抖，只有语义锚点或块内比例明显变化时才写入。
- 浏览器退出请求不保证完成：本地缓存是最后防线，下一次进入后继续补传。
