# learning-record-state Specification

## Purpose
TBD - created by archiving change unify-learning-records. Update Purpose after archive.
## Requirements
### Requirement: 四类记录必须拥有明确边界

系统 MUST 只用 note、issue、review_task 和 bookmark 表达用户主动保留的学习记录，正式错题与作答 MUST NOT 复制为新的记录真源。

#### Scenario: 学生答错正式题目

- **WHEN** 正式练习产生错误作答
- **THEN** 系统 MUST 保存作答事实
- **AND** 系统 MUST NOT 自动创建笔记或未解决问题

### Requirement: 记录必须绑定版本化语义位置

每条有原文来源的记录 MUST 保存课程版本、节点、目标修订、内容块修订和可用的语义文本范围；文本范围 SHOULD 包含字符位置以及 exact、prefix、suffix 引用。课程更新后 MUST 按确定性顺序解析锚点并返回迁移状态，不得删除历史记录、依赖像素坐标或随机跳转。

#### Scenario: 同一内容块重复出现相同句子

- **WHEN** 用户打开绑定 exact、prefix、suffix 和字符范围的记录
- **THEN** 系统 MUST 优先解析原始唯一文本范围
- **AND** 无法唯一定位时 MUST 降级到块级待确认而不是绑定第一次出现位置

### Requirement: 问题和复习任务必须具有生命周期

issue 与 review_task 的状态变化 MUST 被校验并追加事实事件；note 与 bookmark 的归档 MUST 保留历史而不是物理删除。

#### Scenario: 未解决问题被验证解决

- **WHEN** 用户把 awaiting_verification 问题标记为 resolved
- **THEN** 当前记录 MUST 更新状态与修订号
- **AND** 系统 MUST 追加 learning_record_status_changed 事件

### Requirement: AI 回答不得自动成为笔记

普通 AI 会话、无正文锚点提问、主动提醒和未完成输出 MUST 保持临时。用户从正文选区主动提问时，该动作视为对本次锚定问答摘要的明确授权；首个完整回答 MAY 幂等创建一条可撤销 note，后续追问 MUST 更新同一记录。

#### Scenario: AI 完成一次锚定正文解释

- **WHEN** 提问入口为 selection、内容锚点可靠且完整回答已经落库
- **THEN** 系统 MUST 幂等新增或更新一条来源为锚定 AI 问答的 note
- **AND** MUST NOT 保存流式中间态、全部聊天逐字稿或重复记录

#### Scenario: AI 完成一次普通聊天回答

- **WHEN** 提问没有可靠正文锚点
- **THEN** 系统 MUST NOT 自动写入学习记录
- **AND** 用户仍 MAY 通过明确保存动作创建 note

### Requirement: 旧注释迁移必须幂等且降级

旧 annotation MUST 按来源映射到新记录，迁移 MUST 幂等；旧错题注释最多成为低置信 review_task，不得证明当前掌握状态。

#### Scenario: 同一课程重复执行迁移

- **WHEN** 客户端再次提交旧注释迁移
- **THEN** 系统 MUST 返回零条重复创建
- **AND** 已迁移记录和事件 MUST 保持不变

### Requirement: 学习记录必须在正文与总览中共享同一真源

带可靠锚点的手写便签和 AI 问答摘要 MUST 可投影为正文内个人记录块；搜索、筛选和跨章节管理 MUST 通过按需打开的学习记录总览完成。两种界面 MUST 读取同一 `LearningRecord`，不得复制正文卡片状态。

#### Scenario: 用户编辑正文中的便签

- **WHEN** 行内便签保存成功
- **THEN** 学习记录总览 MUST 在统一刷新后显示相同修订内容
- **AND** 系统 MUST NOT 创建第二条记录或保存布局坐标

### Requirement: 旧 annotation 不得继续作为正式记录写入口

新笔记、问题、复习任务和书签 MUST 通过 LearningRecord 领域命令创建。旧 annotation 只允许幂等迁移或只读历史访问，不得为新用户动作继续保存第二份记录或以共享默认身份追加事件。

#### Scenario: 当前学习页保存一条笔记

- **WHEN** 用户从正文或 AI 老师明确保存笔记
- **THEN** 系统 MUST 创建或更新 LearningRecord 并追加关联事件
- **AND** MUST NOT 同时写入 annotation 存储
