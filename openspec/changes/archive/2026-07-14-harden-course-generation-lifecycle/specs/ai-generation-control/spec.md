## ADDED Requirements

### Requirement: 课程生成任务必须拥有可补偿的完整生命周期

课程生成 MUST 将任务、运行协程、生成工作区、候选版本和未发布课程外壳作为同一生命周期管理。创建中途失败或用户取消时，系统 MUST 清理本次任务拥有的临时对象；已正式发布的课程文档 MUST NOT 因任务清理而删除。

#### Scenario: 创建任务中途失败

- **WHEN** 工作区创建后，课程外壳创建、任务持久化或任务入队任一步失败
- **THEN** 系统 MUST 按相反顺序补偿本次已经创建的对象
- **AND** MUST NOT 留下没有对应任务的工作区或 0 节点课程外壳

#### Scenario: 取消尚未发布的新课程

- **WHEN** 用户取消仍在生成且尚未正式发布的初始课程任务
- **THEN** 系统 MUST 先阻止新的后台写入并等待关联协程结束
- **AND** MUST 删除任务工作区、候选版本、蓝图草稿和任务记录
- **AND** MUST 删除由该任务创建的未发布课程外壳

#### Scenario: 清理已发布课程的任务记录

- **WHEN** 用户清理一个已经正式发布课程的终态任务
- **THEN** 系统 MUST 删除任务及其临时生成状态
- **AND** MUST 保留正式 CourseDocument 及其可学习内容

### Requirement: 删除课程必须先终止关联生成任务

课程删除 MUST 通过统一后端生命周期先终止并清理关联生成任务，再删除正式课程对象。后台生成协程 MUST NOT 在课程删除成功后继续写入或重新创建该课程。

#### Scenario: 删除正在生成的课程

- **WHEN** 用户删除具有关联活动 GenerationJob 的课程
- **THEN** 系统 MUST 将任务标记为取消并等待后台协程结束
- **AND** MUST 清理任务工作区、候选版本和任务记录
- **AND** MUST 最后删除正式课程对象

#### Scenario: 删除没有活动任务的课程

- **WHEN** 用户删除只包含历史终态任务或不包含任务的课程
- **THEN** 系统 MUST 幂等清理关联生成状态
- **AND** MUST 删除课程并返回真实结果

### Requirement: 任务控制接口必须返回真实状态机结果

暂停、恢复、节点控制、删除任务和失败任务清理 MUST 校验任务是否存在以及当前状态是否允许操作。成功响应 MUST 表示操作已经发生；不存在对象 MUST 返回 404，状态冲突 MUST 返回 409。

#### Scenario: 暂停不存在或已结束的任务

- **WHEN** 客户端暂停不存在的任务
- **THEN** 服务端 MUST 返回 404
- **WHEN** 客户端暂停已完成、已取消或不可暂停的任务
- **THEN** 服务端 MUST 返回 409 并说明当前状态

#### Scenario: 对终态任务执行节点控制

- **WHEN** 客户端对没有活动任务的课程执行节点跳过、重试、停止或附加指令
- **THEN** 服务端 MUST 返回 404 或 409
- **AND** MUST NOT 修改历史终态任务

#### Scenario: 清理失败任务

- **WHEN** 客户端批量清理失败任务
- **THEN** 系统 MUST 复用单任务生命周期清理逻辑
- **AND** MUST NOT 只删除任务索引而留下工作区或未发布课程外壳

### Requirement: 课程生成输入必须在持久化前规范化

课程主题 MUST 在创建工作区、课程外壳或任务前去除首尾空白并完成非空校验。

#### Scenario: 提交空白课程主题

- **WHEN** 客户端提交只包含空白字符的课程主题
- **THEN** 服务端 MUST 返回 422
- **AND** MUST NOT 创建任务、工作区或课程外壳

### Requirement: 首次课程创建必须按请求号幂等

首次课程创建 MUST 接受稳定的客户端请求号，并 MUST 保证同一请求号只对应一个 `GenerationJob`、一个生成工作区和一门课程。该关系 MUST 随任务持久化，因此服务重启后重复请求仍能返回原任务。

#### Scenario: 同一创建请求并发到达

- **WHEN** 客户端因重复点击、网络重试或响应丢失，使用同一请求号重复提交课程创建
- **THEN** 服务端 MUST 返回第一次创建的 `job_id` 和 `course_id`
- **AND** MUST NOT 创建第二个工作区、课程外壳或任务

#### Scenario: 用户重新发起独立创建

- **WHEN** 用户关闭上一次创建会话后重新提交相同课程参数
- **AND** 客户端使用新的请求号
- **THEN** 服务端 MAY 创建新的独立课程任务

### Requirement: 前端课程列表与生成任务必须持续对账

前端 MUST 以服务端 GenerationJob 和正式 CourseDocument 为真源。取消、删除或发现其他标签页创建的新任务后，前端 MUST 对账任务投影、生成进度和课程列表。

#### Scenario: 取消未发布课程任务

- **WHEN** 服务端确认取消成功
- **THEN** 前端 MUST 移除对应任务和生成进度
- **AND** MUST 重新读取课程列表以移除未发布课程外壳

#### Scenario: 发现本地未知的服务端任务

- **WHEN** 任务轮询发现本地没有记录的新 GenerationJob
- **THEN** 前端 MUST 接纳该任务作为真实状态
- **AND** SHOULD 重新读取课程列表以显示其课程外壳

#### Scenario: 进度样本不足

- **WHEN** 前端没有足够的连续有效样本计算剩余时间
- **THEN** 前端 MUST 显示计算中或不展示估算
- **AND** MUST NOT 根据单次并发跳变展示虚假精确时间

#### Scenario: 历史未发布外壳失去任务

- **WHEN** 课程存储中存在带生成任务号、尚未发布，但任务索引中已无对应任务的历史外壳
- **THEN** 课程列表 MUST NOT 将其展示为可学习课程
- **AND** 系统 MUST 保留原文件用于审计，除非用户执行显式清理

#### Scenario: 已发布课程带有质量建议

- **WHEN** 任务状态为 `completed_with_warnings` 且 `publication_allowed=true`
- **THEN** 前端 MUST 将课程显示为可学习并保留优化建议
- **AND** MUST NOT 把它计入活动或阻断任务数量

### Requirement: 模型调用必须有唯一且有限的重试边界

模型 SDK MUST 使用明确的连接与读取超时，并 MUST NOT 在业务层之外暗中执行额外重试。业务层 MUST 只在有限预算内重试可恢复错误；普通网络错误 MUST NOT 触发对全部模型候选的长时间遍历。

#### Scenario: provider 长时间没有返回数据

- **WHEN** 单次模型请求超过配置的读取等待上限
- **THEN** 请求 MUST 以可恢复错误结束
- **AND** 节点生成 MUST 进入既有有限重试或失败恢复
- **AND** MUST 保留已经保存的节点草稿

#### Scenario: 流式模型请求失败

- **WHEN** provider 返回超时、连接错误、空流或无可用模型
- **THEN** AI 调用层 MUST 抛出结构化错误
- **AND** MUST NOT 把 `[Error: ...]` 或类似错误文本作为课程正文 chunk

#### Scenario: 当前候选模型明确不可用

- **WHEN** provider 明确返回当前模型不受支持、配额不足或模型级限流
- **THEN** AI 调用层 MAY 切换到下一个候选模型
- **AND** 整个请求仍 MUST 受统一尝试预算和超时约束

### Requirement: 质量闸门必须区分发布阻断与优化建议

最终课程质量报告 MUST 分别表达严格质量状态和发布许可。少量非关键质量建议 MUST NOT 阻止完整课程进入正式 CourseDocument；关键内容、资料和资产缺陷 MUST 继续阻断发布并保留生成工作区。

#### Scenario: 完整课程只有少量难度建议

- **WHEN** 所有学习节点生成完成且节点质量通过
- **AND** 只有少量 major 难度或迁移建议，没有 critical 问题、必用资料缺失或资产阻断项
- **THEN** 质量报告 MUST 返回 `final_status=completed_with_warnings`
- **AND** MUST 返回 `publication_allowed=true`
- **AND** 系统 MUST 发布正式课程文档并保留质量警告

#### Scenario: 课程存在关键缺陷

- **WHEN** 任一学习节点为空、生成失败、含 critical 内容问题、使用无效证据、遗漏必用资料或学习资产包含 blocking issue
- **THEN** 质量报告 MUST 返回 `publication_allowed=false`
- **AND** 系统 MUST NOT 发布当前工作区
- **AND** MUST 保留工作区、失败节点和定点修复依据

#### Scenario: 服务发现旧的质量阻塞任务现在允许发布

- **WHEN** 服务启动时读取一个 `quality_failed` 工作区
- **AND** 按当前质量分级重新计算得到 `publication_allowed=true`
- **THEN** 系统 MUST 直接完成质量对账和正式发布
- **AND** MUST NOT 重新调用模型生成已经完成的正文
