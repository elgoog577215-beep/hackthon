---
title: Knowledge Map AI
emoji: 🧠
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# Knowledge Map AI (知识图谱 AI 助手)

这是一个基于 AI 的交互式知识图谱生成与学习平台。

## 功能特点
- **智能课程生成**：输入关键词，自动生成完整的课程大纲和知识结构。
- **动态内容生成**：点击节点，实时生成详细的教学内容。
- **知识图谱可视化**：使用 Mermaid 和交互式图表展示知识关联。
- **AI 苏格拉底导师**：内置 AI 助手，通过追问引导深度思考。
- **测验与复习**：自动生成测验题目，并根据艾宾浩斯遗忘曲线安排复习。

## 技术栈
- **Frontend**: Vue 3, Vite, TailwindCSS, Mermaid.js
- **Backend**: FastAPI, Python 3.10
- **AI Model**: ModelScope API (Qwen/Qwen2.5)

## 本地运行
1. 克隆仓库
2. `cd frontend && npm install && npm run dev`
3. `cd backend && pip install -r requirements.txt && python -m uvicorn main:app --reload`

## 部署
本项目已配置 Dockerfile，可直接部署到 ModelScope 创空间或 Docker 环境。
