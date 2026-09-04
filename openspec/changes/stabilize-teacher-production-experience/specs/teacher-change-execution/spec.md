## Purpose

让跨教案、讲义、PPT、题库和课程结构的修改在部分成功、进程中断与恢复后仍可精确对账、继续和撤销，并复用已有课程命令与定向重建能力。

## ADDED Requirements

### Requirement: 跨资产执行必须逐操作持久记录

系统 MUST 在每个资产操作执行前记录 `applying`，成功后立即记录结果修订和回执，失败后记录稳定错误与可重试性。总回执 MUST 由逐操作记录汇编，进程中断不得使已提交资产失去可追踪证据。

#### Scenario: 第三个资产提交后进程中断
- **WHEN** 前三个资产已经提交但总回执尚未保存时进程退出
- **THEN** 恢复 MUST 对账三个资产的当前修订并补齐回执
- **AND** MUST NOT 盲目重放已经提交的操作

### Requirement: 部分失败必须只续办失败操作

已有 `partial` 结果中的成功操作 MUST 保持已应用；重试 MUST 只处理失败或状态不确定且对账后确认未提交的操作。每个操作 MUST 使用稳定幂等身份。

#### Scenario: 五项修改中一项失败
- **WHEN** 四项已成功且一项失败后用户选择重试
- **THEN** 系统 MUST 只执行失败的 operation ID
- **AND** 四项成功资产的修订 MUST 保持不变

### Requirement: 定向重建必须复用唯一依赖图和执行器

教案、讲义块、V6 页面和题库最小合法单元 MUST 使用同一来源修订、稳定身份和依赖图确定影响范围。系统 MUST NOT 创建第二套重建器或把局部变化默认升级为整组重建。

#### Scenario: 一个教学块发生变化
- **WHEN** 教师修改一个教学块并确认重建
- **THEN** 系统 MUST 只重建绑定的讲义块、PPT 页面和必要题库单元
- **AND** 未受影响对象与最后可用版本 MUST 保持不变

### Requirement: 跨讲结构操作必须形成可恢复原子组

跨讲新增、删除、合并、移动与换位 MUST 使用稳定 ID、墓碑、引用迁移和依赖重算形成一个可预检、可部分选择、可原子应用和可撤销的操作组。

#### Scenario: 部分接受跨讲结构方案
- **WHEN** 教师只接受方案中的部分结构操作
- **THEN** 系统 MUST 重新计算剩余操作的依赖和合法性
- **AND** 应用后 MUST 无悬空引用、无环且可恢复原顺序

#### Scenario: 合并或拆分已有讲次
- **WHEN** 教师确认合并或拆分，且已有教案、讲义、PPT 或题库引用受影响 source ID
- **THEN** 合并 MUST 只保留 primary target ID，拆分 MUST 只让一个 primary target 继承 source ID
- **AND** 其他 source/target MUST 使用稳定新 ID或墓碑，显式依赖 MUST 迁到 primary target
- **AND** 系统 MUST 保留 last-good 内容，不拼接或复制正式内容，并将受影响资产标记为 `stale/rebuild_required`

#### Scenario: 结构引用重绑部分失败
- **WHEN** 教案/讲义、PPT 或题库的重绑与失效标记中有一项失败
- **THEN** 成功仓储的 operation journal 与 last-good MUST 保持不变
- **AND** 重试 MUST 只续办失败 operation ID，撤销 MUST 以 CAS 恢复各仓储修改前的引用和失效标记
