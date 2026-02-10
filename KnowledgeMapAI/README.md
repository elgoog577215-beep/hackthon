# 灵知 (KnowledgeMap)

基于 Vue 3 + TypeScript + Vite + FastAPI + LLM 的智能课程生成与知识图谱系统。

## 功能特性

- **智能课程生成**：根据用户输入的主题，自动生成课程大纲和内容。
- **知识图谱**：自动提取课程核心概念，生成交互式知识图谱。
- **深度学习**：支持多层级章节学习，实时流式内容生成。
- **双模引擎**：支持快速模式（Fast）和深度模式（Smart）切换。

## 技术栈

- **Frontend**: Vue 3, TypeScript, TailwindCSS, Element Plus, D3.js (Force Graph)
- **Backend**: FastAPI, Python 3.10+, OpenAI/DeepSeek API
- **Storage**: JSON-based local storage (for portability)

## 快速开始

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```
