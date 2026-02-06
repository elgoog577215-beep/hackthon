# KnowledgeMap AI 开发指南

本文档旨在帮助开发者快速理解 **KnowledgeMap AI** 的核心功能、架构设计及后续优化方向。本项目是一个基于 AI 的智能课程生成与交互式学习平台，致力于模拟“私人 AI 导师”的教学体验。

---

## 1. 技术栈概览

*   **前端 (Frontend)**
    *   **框架**: Vue 3 (Composition API) + Vite
    *   **状态管理**: Pinia
    *   **UI 组件库**: Element Plus
    *   **样式**: TailwindCSS (v4)
    *   **核心库**: `markdown-it` (渲染), `katex` (数学公式), `highlight.js` (代码高亮)

*   **后端 (Backend)**
    *   **框架**: FastAPI (Python 3.10+)
    *   **AI 服务**: 兼容 OpenAI 接口的模型服务 (默认配置: Qwen/Qwen2.5-72B-Instruct)
    *   **存储**: 本地 JSON 文件存储 (MVP 阶段，位于 `backend/data/`)

---

## 2. 核心功能模块

### 2.1 课程生成引擎 (Course Generation Engine)
*   **大纲生成**: 用户输入关键词，AI 自动生成包含两级目录（章、节）的结构化课程大纲。
*   **递归内容生成**: 支持逐级生成子节点内容，构建深度知识树。
*   **内容重构 (Redefine)**: 允许用户通过 Prompt 指令（如“通俗易懂”、“学术严谨”）重写特定章节内容。
*   **内容扩展 (Extend)**: 针对特定知识点生成延伸阅读材料。

### 2.2 智能交互教学系统 (AI Tutor)
这是本项目的核心差异化模块，旨在模拟真实的人类教师。

*   **双重记忆系统 (Dual Memory System)** (`backend/memory.py`)
    *   **Content Memory (内容记忆)**: 存储课程原文、知识图谱结构。
    *   **User Memory (用户记忆)**: 存储用户的笔记、错题、学习偏好。
    *   **控制器 (Controller)**: 动态分析用户状态（困惑/理解），调整 AI 的教学语气和策略。

*   **模拟教师行为 (Teacher Behavior)**
    *   **自动定位 (Auto-Locate)**: AI 回答问题时，自动在正文中找到依据段落。
    *   **划线高亮 (Highlight)**: 模拟老师用笔划线，前端自动滚动并高亮显示引用原文（紫色高亮）。
    *   **自动笔记 (Auto-Note)**: AI 讲完知识点后，自动在页边生成一条精简的总结笔记（紫色卡片）。

*   **智能上下文压缩 (Smart Context Compression)**
    *   采用 **滚动窗口 + 摘要 (Rolling Window with Summary)** 策略。
    *   保留最近 N 条完整对话，将久远的历史压缩为 System Prompt 摘要，平衡 Token 消耗与记忆长度。

### 2.3 笔记与标注系统 (Note & Annotation)
*   **多源笔记**:
    *   **用户笔记**: 手动划线（黄/绿/蓝等色）、加粗、下划线。
    *   **AI 笔记**: AI 自动生成的教学批注（专属紫色样式）。
*   **笔记交互**:
    *   支持点击笔记自动跳转回原文位置。
    *   支持笔记折叠/展开、编辑、删除。
*   **数据持久化**: 所有标注通过 `annotations` 接口同步至后端。

### 2.4 测评与反馈系统 (Assessment)
*   **智能出题**: 基于当前章节内容，AI 实时生成单选题。
    *   支持难度分级 (Easy/Medium/Hard)。
    *   支持风格切换 (标准/实战/创意)。
*   **错题记录**: 用户的错题会自动进入“用户记忆”，AI 在后续教学中会针对性提醒。

### 2.5 辅助学习工具
*   **专注模式 (Focus Mode)**: 隐藏侧边栏，提供沉浸式阅读体验。
*   **TTS 朗读**: 支持全文或分段朗读，带有阅读进度跟随高亮。
*   **导出功能**: 支持导出课程内容和笔记为 Markdown/JSON 格式。

---

## 3. 待优化与开发建议 (Optimization Roadmap)

为了将项目从 MVP 推向生产级应用，建议重点关注以下领域：

### 3.1 后端优化 (Backend)
1.  **向量检索升级 (RAG Upgrade)**
    *   **现状**: `KnowledgeMigrationManager` 目前使用简单的关键词匹配来查找相关知识点。
    *   **建议**: 引入向量数据库 (如 ChromaDB, Milvus) 和 Embedding 模型，实现基于语义的知识检索，提高“举一反三”的能力。
2.  **存储层迁移**
    *   **现状**: 使用 JSON 文件存储，并发性能差，无法扩展。
    *   **建议**: 迁移至关系型数据库 (PostgreSQL) 或 NoSQL (MongoDB)。
3.  **LLM 摘要增强**
    *   **现状**: `ContextCompressor` 使用启发式规则提取摘要。
    *   **建议**: 调用轻量级 LLM 对历史对话进行高质量摘要，减少信息丢失。

### 3.2 前端优化 (Frontend)
1.  **长列表性能**
    *   **现状**: 长篇幅课程一次性渲染所有 DOM 节点。
    *   **建议**: 引入虚拟滚动 (Virtual Scrolling) 或按需渲染机制，优化 `ContentArea` 的加载速度。
2.  **状态管理重构**
    *   **现状**: `course.ts` 承担了过多职责（API调用、UI状态、业务逻辑）。
    *   **建议**: 拆分为 `course-data.ts` (数据), `course-ui.ts` (界面), `ai-chat.ts` (对话) 等多个 Store。
3.  **移动端体验**
    *   **现状**: 基础适配。
    *   **建议**: 优化移动端的触摸交互，特别是划线操作和侧边栏手势。

### 3.3 工程化与测试
1.  **单元测试**: 后端 `memory.py` 和 `ai_service.py` 缺乏自动化测试，建议补充 Pytest 用例。
2.  **CI/CD**: 建立自动构建和部署流程。

---

## 4. 目录结构说明

```
KnowledgeMapAI/
├── backend/
│   ├── data/               # 本地存储数据
│   ├── ai_service.py       # AI 核心逻辑 (LLM调用, Prompt工程)
│   ├── memory.py           # 双重记忆系统与上下文压缩
│   ├── main.py             # FastAPI 入口
│   ├── models.py           # Pydantic 数据模型
│   └── storage.py          # 文件存储操作
├── frontend/
│   ├── src/
│   │   ├── components/     # Vue 组件 (ContentArea, ChatPanel等)
│   │   ├── stores/         # Pinia 状态管理
│   │   └── utils/          # 工具函数
│   └── index.html
└── DEVELOPMENT_GUIDE.md    # 本文档
```
