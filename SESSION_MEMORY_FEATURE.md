# 会话记忆增强功能文档

## 概述
已成功实现优化对话历史能力 - 增强上下文记忆功能，为AI导师系统添加了会话上下文感知能力。

## 实现内容

### 1. 后端模型更新 (models.py)
- 在 `AskQuestionRequest` 模型中新增两个字段：
  - `session_metrics`: 可选字典类型，包含会话统计信息
  - `enable_long_term_memory`: 可选布尔类型，默认False，控制是否启用长期记忆

### 2. AI服务层更新 (ai_service.py)
- 更新 `answer_question_stream` 方法签名，支持接收会话指标和长期记忆开关
- 在系统提示构建逻辑中添加会话上下文感知：
  - 当 `enable_long_term_memory=True` 时，将 `session_metrics` 信息注入系统提示
  - 会话上下文包含：总消息数、用户/AI消息数、会话时长、讨论主题、问题类型分布
- 在标准提示模板中添加 `{session_context}` 占位符

### 3. API端点更新 (main.py)
- 更新 `/ask` 端点，将前端传来的 `session_metrics` 和 `enable_long_term_memory` 传递给AI服务

### 4. 前端实现 (course.ts)
- 实现 `calculateSessionMetrics()` 方法，计算并返回会话指标：
  - 消息统计（总数、用户消息数、AI消息数）
  - 会话时长估算
  - 讨论主题提取（基于关键词匹配）
  - 问题类型分类（概念性、程序性、故障排除、探索性）
- 在 `askQuestion` 方法中调用会话指标计算并发送到后端
- 默认启用长期记忆 (`enable_long_term_memory: true`)
- 实现会话记忆本地存储管理方法：
  - `saveSessionMemory()`: 保存会话记忆到localStorage
  - `getSessionMemories()`: 获取历史会话记忆
  - `clearSessionMemories()`: 清除会话记忆

## 数据流

```
用户提问
    ↓
前端计算会话指标 (calculateSessionMetrics)
    ↓
发送请求到 /ask (包含 session_metrics 和 enable_long_term_memory)
    ↓
后端接收请求 (AskQuestionRequest)
    ↓
AI服务构建系统提示 (注入会话上下文)
    ↓
LLM生成带上下文的响应
    ↓
流式返回给前端
```

## 会话指标结构

```json
{
  "total_messages": 10,
  "user_messages": 5,
  "ai_messages": 5,
  "session_duration_minutes": 15,
  "topics_discussed": ["概念", "原理", "函数"],
  "question_types": {
    "conceptual": 3,
    "procedural": 1,
    "troubleshooting": 1,
    "exploratory": 0
  }
}
```

## 系统提示中的会话上下文示例

```
--- 会话上下文 ---
本会话已有 10 条消息（用户: 5, AI: 5）
已讨论主题: 概念, 原理, 函数
问题类型分布: 概念性(3), 程序性(1), 故障排除(1), 探索性(0)
------------------
```

## 测试验证

所有组件均已通过测试：
- ✅ 后端模型参数验证
- ✅ 前端会话指标计算
- ✅ 前后端数据流集成
- ✅ 系统提示构建逻辑

## 后续优化建议

1. **持久化存储**: 将重要的会话记忆持久化到数据库，而非仅依赖localStorage
2. **智能总结**: 实现对话内容的智能总结，提取关键学习点
3. **跨会话关联**: 分析不同会话间的主题关联，提供连贯的学习体验
4. **个性化推荐**: 基于会话历史推荐相关学习资源
