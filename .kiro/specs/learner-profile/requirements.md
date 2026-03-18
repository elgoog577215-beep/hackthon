# Requirements Document

## Introduction

学习者画像（Learner Profile）功能为 Knowledge Map AI 平台新增 AI 驱动的学习者分析能力。系统基于学习者的错题记录、笔记内容和问答聊天历史，由 AI 生成综合性的学习者画像，分析薄弱领域、未掌握知识点和整体学习表现。画像展示在侧边栏底部，支持全量重新生成、增量自动更新、用户自评上传，并作为 AI 生成测验等内容时的 prompt 上下文，实现个性化学习体验。

## Glossary

- **Profile_Service**: 后端负责学习者画像生成与更新的 AI 服务模块
- **Profile_Store**: 前端 Pinia store，管理学习者画像状态、自评文本和更新逻辑
- **Learner_Profile**: AI 生成的学习者画像数据对象，包含薄弱领域分析、知识点掌握度和综合评价
- **Agent_Commentary**: 系统（Kiro/Agent）基于 AI 画像额外给出的独立建议和观点
- **Self_Evaluation**: 用户自行撰写或上传的自我评价文本
- **Incremental_Update**: 基于当前画像 + 新增内容 + 自评生成更新画像的增量更新方式
- **Full_Regeneration**: 重新收集所有错题、笔记、聊天历史，从零生成完整画像的全量重建方式
- **Review_Store**: 前端管理错题记录和测验历史的 Pinia store（`review.ts`）
- **Note_Store**: 前端管理笔记 CRUD 的 Pinia store（`notes.ts`）
- **Course_Store**: 前端管理课程状态和聊天历史的 Pinia store（`course.ts`）
- **SideAIPanel**: 侧边 AI 面板组件（`SideAIPanel.vue`），画像展示区域的宿主组件

## Requirements

### Requirement 1: AI 画像生成

**User Story:** As a learner, I want the AI to analyze my wrong answers, notes, and chat history to generate a learner profile, so that I can understand my strengths and weaknesses.

#### Acceptance Criteria

1. WHEN the learner requests a full profile generation, THE Profile_Service SHALL collect all wrong answers from Review_Store, all notes from Note_Store, and all chat messages from Course_Store, and send the combined data to the LLM to generate a Learner_Profile.
2. THE Learner_Profile SHALL contain three sections: a list of weak areas with specific knowledge points, a list of insufficiently mastered knowledge points with related node references, and an overall learning performance summary.
3. WHEN the LLM returns the generated profile, THE Profile_Service SHALL return the Learner_Profile as a structured JSON response containing `weak_areas`, `unmastered_points`, and `overall_summary` fields.
4. IF the LLM call fails or times out, THEN THE Profile_Service SHALL return an error response with a descriptive message and THE Profile_Store SHALL display the error to the learner.
5. IF no learning data exists (zero wrong answers, zero notes, and zero chat messages), THEN THE Profile_Service SHALL return a response indicating insufficient data and THE Profile_Store SHALL display a message explaining that more learning activity is needed before a profile can be generated.

### Requirement 2: Agent 独立评论

**User Story:** As a learner, I want to see the system's own perspective and suggestions alongside the AI profile, so that I can get additional actionable guidance.

#### Acceptance Criteria

1. WHEN a Learner_Profile is generated or updated, THE Profile_Service SHALL generate an Agent_Commentary as a separate LLM call that provides the system's own suggestions and perspective based on the Learner_Profile content.
2. THE Agent_Commentary SHALL be displayed in a visually distinct section, separate from the Learner_Profile analysis section.
3. THE Agent_Commentary SHALL include specific, actionable learning suggestions tailored to the identified weak areas.

### Requirement 3: 画像展示

**User Story:** As a learner, I want to see my learner profile at the bottom of the side panel, so that I can quickly review my learning analysis.

#### Acceptance Criteria

1. THE Profile_Store SHALL render the Learner_Profile display area at the bottom of the SideAIPanel component.
2. THE Learner_Profile display SHALL show the AI analysis section (weak areas, unmastered points, overall summary) and the Agent_Commentary section as two visually separated blocks.
3. WHILE no Learner_Profile has been generated, THE Profile_Store SHALL display a placeholder prompting the learner to generate a profile.

### Requirement 4: 全量重新生成

**User Story:** As a learner, I want to regenerate my profile from scratch, so that I can get a fresh analysis when I feel the current one is outdated.

#### Acceptance Criteria

1. THE SideAIPanel SHALL provide a "重新生成" (Regenerate) button in the profile display area.
2. WHEN the learner clicks the Regenerate button, THE Profile_Store SHALL display a confirmation dialog warning that full regeneration may take significant time and consume API tokens, and advising against frequent regeneration.
3. WHEN the learner confirms regeneration, THE Profile_Service SHALL perform a Full_Regeneration by re-collecting all current learning data and generating a new Learner_Profile from scratch.
4. WHILE a Full_Regeneration is in progress, THE SideAIPanel SHALL display a loading indicator and disable the Regenerate button.

### Requirement 5: 用户自评上传

**User Story:** As a learner, I want to write and submit my own self-evaluation, so that the AI can incorporate my self-awareness into the profile.

#### Acceptance Criteria

1. THE SideAIPanel SHALL provide a text input area where the learner can write or paste a Self_Evaluation.
2. WHEN the learner submits a Self_Evaluation, THE Profile_Service SHALL combine the current Learner_Profile, the Self_Evaluation text, and existing learning data to generate an updated Learner_Profile via the LLM.
3. THE Profile_Store SHALL persist the Self_Evaluation text so it is available for future profile updates.
4. THE Self_Evaluation submission SHALL NOT display any token consumption warning, allowing unrestricted submissions.

### Requirement 6: 增量自动更新

**User Story:** As a learner, I want my profile to automatically update when I add new learning content, so that the profile stays current without manual intervention.

#### Acceptance Criteria

1. WHEN a new wrong answer is recorded in Review_Store, THE Profile_Store SHALL trigger an Incremental_Update.
2. WHEN a new note is created in Note_Store, THE Profile_Store SHALL trigger an Incremental_Update.
3. WHEN a new chat message exchange (user question + AI response pair) is completed in Course_Store, THE Profile_Store SHALL trigger an Incremental_Update.
4. WHEN an Incremental_Update is triggered, THE Profile_Service SHALL receive the current Learner_Profile, the new content that triggered the update, and the current Self_Evaluation, and generate an updated Learner_Profile.
5. THE Profile_Store SHALL debounce Incremental_Update triggers so that rapid successive events (e.g., multiple notes created in quick succession) result in a single update request containing all new content.
6. WHILE an Incremental_Update is in progress, THE Profile_Store SHALL queue subsequent triggers and process them as a single batch after the current update completes.
7. IF an Incremental_Update fails, THEN THE Profile_Store SHALL retain the previous Learner_Profile and log the error without disrupting the learner's workflow.

### Requirement 7: 画像作为 Prompt 上下文

**User Story:** As a learner, I want the AI to use my profile when generating quizzes and other content, so that the content adapts to my level and weaknesses.

#### Acceptance Criteria

1. WHEN a quiz is generated via Course_Store, THE Course_Store SHALL include the current Learner_Profile summary in the `user_persona` parameter sent to the backend.
2. WHEN an AI Q&A request is made via Course_Store, THE Course_Store SHALL include the current Learner_Profile summary in the `user_persona` parameter sent to the backend.
3. THE Profile_Store SHALL provide a computed getter that formats the Learner_Profile into a concise text summary suitable for use as a `user_persona` prompt parameter.
4. WHILE no Learner_Profile exists, THE Course_Store SHALL continue to use the existing `userPersona` value from localStorage as fallback.

### Requirement 8: 画像数据持久化

**User Story:** As a learner, I want my profile to persist across browser sessions, so that I don't lose my analysis when I close the browser.

#### Acceptance Criteria

1. WHEN a Learner_Profile is generated or updated, THE Profile_Store SHALL persist the Learner_Profile, Agent_Commentary, and Self_Evaluation to localStorage.
2. WHEN the application initializes, THE Profile_Store SHALL restore the persisted Learner_Profile, Agent_Commentary, and Self_Evaluation from localStorage.
3. IF the persisted data is corrupted or unparseable, THEN THE Profile_Store SHALL discard the corrupted data, initialize with an empty state, and log a warning.
