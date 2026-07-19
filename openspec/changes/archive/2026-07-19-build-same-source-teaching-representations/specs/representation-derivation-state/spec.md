## ADDED Requirements

### Requirement: 每次正式课程变化必须产生可重放修订事件

课程首次发布和每次正式课程命令 MUST 持久化新旧修订向量、变化源键、受影响块和命令身份。派生服务不可用时，课程提交 MAY 先成功，但系统 MUST 能从课程操作日志重放尚未消费的修订事件。

#### Scenario: 派生服务在课程提交时不可用

- **WHEN** 正式课程命令已经通过预检并提交
- **THEN** 课程操作日志 MUST 保存完整修订变化事件
- **AND** 后续对账 MUST 能重新执行陈旧传播

### Requirement: 派生产物必须被精准标记为过期

系统 MUST 根据来源绑定和派生依赖图标记受影响表达。局部块变化 MUST NOT 默认使无关块表达过期；课程级绑定表达 MUST 在任一课程语义变化后过期。

#### Scenario: 一个课程块内容变化

- **WHEN** `block:A` 的修订变化而 `block:B` 保持不变
- **THEN** 依赖 `block:A` 的表达 MUST 标记为 `stale`
- **AND** 只依赖 `block:B` 的表达 MUST 保持原状态

#### Scenario: 来源块被删除

- **WHEN** 一个来源绑定指向的课程块从当前修订中删除
- **THEN** 相关表达 MUST 标记为 `stale`
- **AND** 陈旧原因 MUST 记录来源已移除

### Requirement: 陈旧传播必须幂等且跨课程隔离

同一修订事件重复消费 MUST 返回同一注册表状态；课程 A 的事件 MUST NOT 改变课程 B 的表达。

#### Scenario: 重放已消费事件

- **WHEN** 对账任务再次提交相同事件 ID
- **THEN** 系统 MUST NOT 重复增加陈旧原因或注册表修订

#### Scenario: 错误课程事件

- **WHEN** 课程 A 的事件被提交到课程 B 的注册表
- **THEN** 系统 MUST 拒绝操作
