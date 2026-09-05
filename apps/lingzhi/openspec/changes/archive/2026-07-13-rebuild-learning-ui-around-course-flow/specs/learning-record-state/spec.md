## MODIFIED Requirements

### Requirement: 记录必须绑定版本化语义位置

每条有原文来源的记录 MUST 保存课程版本、节点、目标修订、内容块修订和可用的语义文本范围；文本范围 SHOULD 包含字符位置以及 exact、prefix、suffix 引用。课程更新后 MUST 按确定性顺序解析锚点并返回迁移状态，不得删除历史记录、依赖像素坐标或随机跳转。

#### Scenario: 同一内容块重复出现相同句子

- **WHEN** 用户打开绑定 exact、prefix、suffix 和字符范围的记录
- **THEN** 系统 MUST 优先解析原始唯一文本范围
- **AND** 无法唯一定位时 MUST 降级到块级待确认而不是绑定第一次出现位置

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

## ADDED Requirements

### Requirement: 学习记录必须在正文与总览中共享同一真源

带可靠锚点的手写便签和 AI 问答摘要 MUST 可投影为正文内个人记录块；搜索、筛选和跨章节管理 MUST 通过按需打开的学习记录总览完成。两种界面 MUST 读取同一 `LearningRecord`，不得复制正文卡片状态。

#### Scenario: 用户编辑正文中的便签

- **WHEN** 行内便签保存成功
- **THEN** 学习记录总览 MUST 在统一刷新后显示相同修订内容
- **AND** 系统 MUST NOT 创建第二条记录或保存布局坐标
