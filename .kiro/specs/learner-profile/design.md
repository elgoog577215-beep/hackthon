# Design Document: 学习者画像 (Learner Profile)

## Overview

本功能为平台新增 AI 驱动的学习者画像系统。系统收集错题、笔记、聊天记录等学习数据，通过 LLM 生成结构化的学习者分析画像，并将画像注入到后续 AI 交互（出题、问答等）的 prompt 上下文中，实现个性化学习体验。

## Architecture

### 数据流

```
┌─────────────┐  ┌──────────────┐  ┌──────────────┐
│ Review Store │  │  Note Store   │  │ Course Store  │
│ (错题记录)    │  │  (笔记)       │  │ (聊天历史)    │
└──────┬───────┘  └──────┬────────┘  └──────┬────────┘
       │                 │                   │
       └─────────────────┼───────────────────┘
                         │ 收集学习数据
                         ▼
              ┌─────────────────────┐
              │   Profile Store     │
              │  (前端状态管理)      │
              │  - 防抖/队列控制     │
              │  - localStorage     │
              └──────────┬──────────┘
                         │ HTTP POST
                         ▼
              ┌─────────────────────┐
              │  /api/profile/*     │
              │  (后端路由)          │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ AIProfileService    │
              │  - generate_profile │
              │  - update_profile   │
              │  - generate_comment │
              └──────────┬──────────┘
                         │ LLM 调用
                         ▼
              ┌─────────────────────┐
              │    Qwen LLM API     │
              └─────────────────────┘
```

### 新增文件

| 文件 | 类型 | 职责 |
|------|------|------|
| `frontend/src/stores/profile.ts` | Pinia Store | 画像状态管理、防抖、持久化 |
| `frontend/src/components/LearnerProfile.vue` | Vue 组件 | 画像展示 UI |
| `backend/ai_profile_service.py` | AI 服务 | 画像生成/更新的 LLM 调用逻辑 |
| `backend/routers/profile.py` | FastAPI 路由 | 画像相关 API 端点 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `backend/ai_service.py` | 添加 `AIProfileService` 到多继承链 |
| `backend/main.py` | 注册 profile 路由 |
| `frontend/src/components/SideAIPanel.vue` | 底部嵌入 `LearnerProfile` 组件 |
| `frontend/src/stores/course.ts` | `userPersona` getter 改为从 profile store 读取 |

---

## Data Models

### 后端 Pydantic 模型 (`backend/models.py`)

```python
class GenerateProfileRequest(BaseModel):
    wrong_answers: List[dict] = []        # 错题列表
    notes: List[dict] = []                # 笔记列表
    chat_summary: str = ""                # 聊天摘要（前端截取最近N条）
    self_evaluation: str = ""             # 用户自评
    current_profile: Optional[str] = None # 当前画像（增量更新时传入）
    mode: str = "full"                    # "full" | "incremental"
    new_content: Optional[str] = None     # 增量更新时的新增内容描述

class ProfileResponse(BaseModel):
    ai_profile: str          # AI 生成的画像分析（markdown 格式）
    agent_commentary: str    # Agent 独立评论（markdown 格式）
    persona_summary: str     # 精简版画像（用于注入 prompt，<200字）
```

### 前端 Profile Store 状态

```typescript
interface ProfileState {
  aiProfile: string           // AI 画像分析 markdown
  agentCommentary: string     // Agent 独立评论 markdown
  personaSummary: string      // 精简版（注入 prompt 用）
  selfEvaluation: string      // 用户自评文本
  isGenerating: boolean       // 生成中状态
  lastUpdated: number | null  // 最后更新时间戳
  pendingUpdate: boolean      // 是否有待处理的增量更新
}
```

---

## Component Design

### LearnerProfile.vue

放置在 `SideAIPanel.vue` 底部，包含：

1. **折叠/展开区域**：默认折叠，标题显示"学习者画像"和最后更新时间
2. **AI 分析区块**：用 `MarkdownRenderer` 渲染 `aiProfile`
3. **Agent 评论区块**：视觉上与 AI 分析区分（不同背景色/边框），渲染 `agentCommentary`
4. **自评输入区**：`<el-input type="textarea">` + 提交按钮
5. **操作按钮**：
   - "重新生成"按钮（带确认弹窗警告 token 消耗）
   - 自评提交按钮（无警告）
6. **空状态**：无画像时显示"开始学习后将自动生成画像"提示

### SideAIPanel.vue 修改

在现有内容底部添加：
```vue
<LearnerProfile />
```

---

## API Design

### POST `/api/profile/generate`

全量生成或增量更新画像。

**Request**: `GenerateProfileRequest`
**Response**: `ProfileResponse`

路由处理逻辑：
1. 根据 `mode` 选择全量或增量 prompt
2. 调用 `ai_profile_service.generate_profile()` 生成 AI 画像
3. 调用 `ai_profile_service.generate_commentary()` 生成 Agent 评论
4. 调用 `ai_profile_service.generate_persona_summary()` 生成精简版
5. 返回三部分结果

---

## AI Service Design (`ai_profile_service.py`)

继承 `AIBase`，提供三个核心方法：

### `generate_profile(data, mode, current_profile)`

- **全量模式**：将所有错题（题目+正确答案+用户答案）、笔记内容、聊天摘要、自评打包发给 LLM
- **增量模式**：将当前画像 + 新增内容 + 自评发给 LLM，要求在现有画像基础上更新
- **输出**：markdown 格式的分析文本，包含薄弱领域、未掌握知识点、综合评价
- **使用 fast model**（`use_fast_model=True`），因为画像生成不需要最高质量

### `generate_commentary(ai_profile)`

- 基于 AI 画像内容，生成系统独立建议
- 侧重可操作的学习建议
- 使用 fast model

### `generate_persona_summary(ai_profile, self_evaluation)`

- 将完整画像压缩为 <200 字的精简描述
- 格式适合直接注入 prompt 的 `user_persona` 参数
- 使用 fast model

---

## Incremental Update Mechanism

### 触发时机

Profile Store 监听以下事件：
1. `reviewStore.wrongAnswers` 长度变化（新增错题）
2. `noteStore.notes` 长度变化（新增笔记）
3. `courseStore.chatHistory` 长度变化（新增对话，仅计 user+ai 对）

### 防抖策略

- 使用 `setTimeout` 防抖，延迟 30 秒
- 30 秒内的多次触发合并为一次请求
- 请求进行中时，新触发排队等待，完成后批量处理

### 实现方式

```typescript
// profile.ts store 中
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function scheduleUpdate(newContentDesc: string) {
  if (this.isGenerating) {
    this.pendingUpdate = true
    return
  }
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    this.incrementalUpdate(newContentDesc)
  }, 30000)
}
```

### Watch 设置

在 `SideAIPanel.vue` 或 `LearnerProfile.vue` 的 `onMounted` 中设置 watch：

```typescript
watch(() => reviewStore.wrongAnswers.length, (newLen, oldLen) => {
  if (newLen > oldLen && profileStore.aiProfile) {
    profileStore.scheduleUpdate('新增错题记录')
  }
})
// 类似 watch noteStore.notes.length 和 chatHistory.length
```

---

## Prompt 上下文注入 (Requirement 7)

### 修改 `course.ts`

将 `userPersona` 的读取逻辑改为优先从 profile store 获取：

```typescript
get effectivePersona(): string {
  const profileStore = useProfileStore()
  return profileStore.personaSummary || this.userPersona
}
```

所有使用 `this.userPersona` 的地方改为 `this.effectivePersona`：
- `generateQuiz()` 中的 `user_persona` 参数
- `askQuestion()` 中的 `user_persona` 参数
- `quickSummarize()` 中的 `user_persona` 参数
- `summarizeChat()` 中的 `user_persona` 参数

---

## Persistence (Requirement 8)

Profile Store 使用 localStorage：

```typescript
const STORAGE_KEYS = {
  profile: 'learner_profile',
  commentary: 'learner_commentary',
  persona: 'learner_persona_summary',
  selfEval: 'learner_self_evaluation',
  lastUpdated: 'learner_profile_updated'
}
```

- 每次生成/更新后自动写入
- 初始化时从 localStorage 恢复
- JSON.parse 失败时清空并 log warning

---

## Prompt Templates (`prompts.py`)

新增两个 prompt 模板：

### GENERATE_LEARNER_PROFILE

System prompt 要求 LLM 扮演教育分析师，基于学习数据生成结构化画像。输出 markdown 格式，包含：
- 薄弱领域分析（按知识点分类）
- 未掌握知识点列表
- 学习习惯观察
- 综合评价

### GENERATE_AGENT_COMMENTARY

System prompt 要求 LLM 基于画像给出独立的学习建议，语气友好、可操作，与画像分析风格区分。

---

## Tasks

### Task 1: 后端 AI 服务和路由
- 新建 `backend/ai_profile_service.py`（继承 AIBase，3 个方法）
- 在 `backend/prompts.py` 添加 2 个 prompt 模板
- 在 `backend/models.py` 添加 `GenerateProfileRequest` 和 `ProfileResponse`
- 新建 `backend/routers/profile.py`（1 个 POST 端点）
- 修改 `backend/ai_service.py` 添加 AIProfileService 到继承链
- 修改 `backend/main.py` 注册路由
- **Covers**: Req 1, Req 2

### Task 2: 前端 Profile Store
- 新建 `frontend/src/stores/profile.ts`
- 实现状态定义、generate/update actions、localStorage 持久化
- 实现防抖和队列机制
- **Covers**: Req 6, Req 8

### Task 3: 前端 LearnerProfile 组件
- 新建 `frontend/src/components/LearnerProfile.vue`
- 实现画像展示（AI 分析 + Agent 评论两个区块）
- 实现自评输入区和提交
- 实现重新生成按钮（带确认弹窗）
- 实现空状态和加载状态
- 修改 `SideAIPanel.vue` 嵌入组件
- **Covers**: Req 3, Req 4, Req 5

### Task 4: 增量自动更新 Watch
- 在 LearnerProfile.vue 中设置 watch 监听错题/笔记/聊天变化
- 触发 profile store 的 scheduleUpdate
- **Covers**: Req 6

### Task 5: Prompt 上下文注入
- 修改 `course.ts` 添加 `effectivePersona` getter
- 替换所有 `this.userPersona` 为 `this.effectivePersona`
- **Covers**: Req 7
