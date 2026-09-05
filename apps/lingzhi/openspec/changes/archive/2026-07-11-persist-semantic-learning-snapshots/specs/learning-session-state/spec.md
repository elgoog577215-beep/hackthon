# learning-session-state Specification

## Purpose

定义课程阅读的版本化语义锚点、服务端学习现场、跨设备并发、离线缓存和恢复行为，使后续学习记录、练习草稿、问题和补救共享同一状态底座。

## ADDED Requirements

### Requirement: 内容块必须拥有稳定身份和不可变修订

系统 MUST 为可学习内容块提供稳定 `block_id`、内容指纹和不可变 `block_revision_id`。课程读取响应与前端 DOM MUST 暴露相同元数据，历史快照不得只依赖标题或滚动距离定位。

#### Scenario: 同一内容块正文发生变化

- **WHEN** 一个已有 block_id 的标题、类型、父块或正文发生变化
- **THEN** block_id MUST 保持不变
- **AND** block_revision_id MUST 变化
- **AND** 新旧修订 MUST 可以被区分

### Requirement: 学习现场必须与历史事件分离

系统 MUST 使用可覆盖的 `LearningSnapshot` 保存当前恢复现场，并继续使用追加式 `LearningEvent` 保存历史事实。高频滚动 MUST NOT 逐条写入事件账本。

#### Scenario: 用户连续滚动正文

- **WHEN** 当前语义位置多次变化
- **THEN** 系统 MUST 更新同一当前快照修订
- **AND** MUST NOT 为每次滚动追加 LearningEvent

### Requirement: 服务端快照必须是跨设备真源

系统 MUST 按用户与课程隔离服务端快照，本地缓存 MUST 只承担快速恢复和离线保护。快照 MUST 保存课程版本、节点、内容锚点、会话和受限任务状态。

#### Scenario: 用户在另一设备打开课程

- **WHEN** 服务端存在该用户课程的学习快照
- **THEN** 新设备 MUST 加载服务端快照
- **AND** MUST 恢复到解析后的语义位置
- **AND** MUST NOT 仅使用新设备本地滚动值

### Requirement: 并发更新必须使用乐观修订保护

更新快照 MUST 携带 `expected_revision`。修订不匹配时系统 MUST 返回 409 和当前服务端快照，不得静默覆盖。

#### Scenario: 两个设备同时更新同一课程

- **GIVEN** 两个设备都读取 revision 4
- **WHEN** 设备 A 先写入 revision 5，设备 B 仍使用 expected_revision 4
- **THEN** 设备 B MUST 收到冲突和 revision 5 的当前快照
- **AND** 服务端 MUST 保留设备 A 的数据

### Requirement: 课程版本变化后必须确定性解析锚点

系统 MUST 依次使用相同修订、相同块、内容指纹、节点和课程回退解析历史锚点，并返回明确状态。无法精确恢复时 MUST NOT 随机跳转或伪装成精确匹配。

#### Scenario: 内容块修订已经更新

- **WHEN** 历史快照的 block_id 仍存在但 block_revision_id 已变化
- **THEN** 系统 MUST 返回 updated_block
- **AND** MUST 标记内容发生变化
- **AND** 前端 MUST 恢复到该逻辑块而不是旧全局像素位置

#### Scenario: 原节点已经删除

- **WHEN** block、指纹和 node_id 都无法匹配
- **THEN** 系统 MUST 返回 course_fallback
- **AND** MUST 提供一个明确的当前课程起点

### Requirement: 离线状态必须先本地保存并在恢复网络后补传

前端 MUST 在服务端保存前立即更新本地缓存。网络失败时 MUST 保留待同步状态；后续恢复网络或再次打开课程时 MUST 尝试补传。

#### Scenario: 滚动后立即断网并关闭页面

- **WHEN** 服务端请求尚未成功
- **THEN** 最新语义位置 MUST 留在本地缓存
- **AND** 界面 MUST 显示尚未同步状态
- **AND** 下次联网打开时 MUST 尝试同步

### Requirement: 旧滚动状态只能幂等迁移一次

只有在服务端和本地都没有新快照时，前端 MAY 读取旧 `lastReadPosition` 或 `scroll-pos-*` 创建迁移快照。新快照成功建立后，旧状态 MUST NOT 继续参与实时选择。

#### Scenario: 用户升级后第一次打开旧课程

- **WHEN** 没有新格式快照但存在旧节点或滚动位置
- **THEN** 前端 MUST 创建标记 legacy_migration 的新快照
- **AND** 后续打开 MUST 使用新快照
- **AND** 重复迁移 MUST NOT 创建多个服务端状态
