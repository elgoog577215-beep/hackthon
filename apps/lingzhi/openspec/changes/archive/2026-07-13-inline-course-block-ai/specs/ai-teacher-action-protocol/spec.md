## MODIFIED Requirements

### Requirement: 前端必须提供唯一 AI 老师工作区

结构化课程块的解释、举例、简化和提问 MUST 在来源块附近进入同一个行内 AI 结果块；继续追问 MUST 更新该块的当前表达，不得为同一轮连续问答重复生成多张卡片。全局 AI 工作区 MAY 保留为历史会话、跨块问题和低频兜底入口，但块级协作与全局入口 MUST 共用同一会话、上下文、提案和回执协议，不得建立平行 AI 状态。

#### Scenario: 用户请求解释当前课程块

- **WHEN** 用户在一个结构化课程块选择“解释”
- **THEN** 系统 MUST 在该块下方显示临时 AI 结果
- **AND** MUST NOT 要求用户先打开右栏或离开当前阅读位置

#### Scenario: 用户继续追问

- **WHEN** 当前块已经存在一次 AI 回答且用户选择“继续追问”
- **THEN** 系统 MUST 在同一个行内结果块接收并显示新回答
- **AND** 全局会话历史 MUST 保留完整消息顺序

#### Scenario: 用户查看全局 AI

- **WHEN** 用户从全局 AI 入口查看历史或提出跨块问题
- **THEN** 系统 MUST 读取与行内问答相同的会话状态
- **AND** MUST NOT 把行内回答复制成第二套会话记录

### Requirement: AI 对话不得自动成为学习记录或稳定画像

块级 AI 的解释、举例、简化和提问 MUST 默认保持临时状态；MUST NOT 自动创建笔记、问题、复习任务、薄弱点、掌握结论或正式课程改写。只有用户明确选择“保留为个人内容”，系统才 MAY 通过现有白名单提案和确认协议创建带稳定内容锚点的 `LearningRecord`。

#### Scenario: 行内回答完成

- **WHEN** AI 完成对课程块的解释、举例、简化或回答
- **THEN** 结果 MUST 继续作为可移除的临时个人内容显示
- **AND** MUST NOT 自动写入 `LearningRecord` 或 `CourseDocument`

#### Scenario: 用户保留回答

- **WHEN** 用户点击“保留为个人内容”
- **THEN** 系统 MUST 使用 `block_id` 与 `block_revision_id` 创建或确认个人学习记录
- **AND** 保存完成后 MUST 由正式学习记录投影回来源块附近

#### Scenario: 用户移除临时回答

- **WHEN** 用户点击“移除”
- **THEN** 系统 MUST 移除当前行内表达
- **AND** MUST NOT 修改正式课程或已经持久化的全局会话历史
