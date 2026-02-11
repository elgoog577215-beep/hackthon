---
title: KnowledgeMap AI
emoji: 🧠
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
license: apache-2.0
---

# 🧠 KnowledgeMap AI - 智能知识图谱学习平台

> **让 AI 为你构建专属的知识宇宙。**
> 
> *An AI-powered personalized learning platform that transforms keywords into comprehensive knowledge maps.*

![Vue.js](https://img.shields.io/badge/vue-%2335495e.svg?style=flat&logo=vuedotjs&logoColor=%234FC08D)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=flat&logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)
![Python](https://img.shields.io/badge/python-3670A0?style=flat&logo=python&logoColor=ffdd54)
![ModelScope](https://img.shields.io/badge/ModelScope-Supported-blue)

## 📖 项目简介 (Introduction)

**KnowledgeMap AI** 是一个基于生成式 AI 的交互式学习平台。它打破了传统线性学习的束缚，允许用户仅通过输入一个**关键词**（如“量子力学”、“深度学习”），即可自动生成结构化的课程大纲、详细的学习内容以及可视化的知识图谱。

本项目旨在利用大模型（LLM）的推理与生成能力，解决碎片化知识难以体系化的问题，为终身学习者提供一个**结构化、可视化、个性化**的学习环境。

## ✨ 核心功能 (Key Features)

### 1. 🚀 AI 智能课程生成
- **一键生成**：输入感兴趣的主题，AI 自动规划从入门到精通的学习路径。
- **动态大纲**：生成树状课程结构，支持无限层级的子节点扩展。
- **流式响应**：采用打字机效果实时呈现 AI 生成的内容，减少等待焦虑。

### 2. 🕸️ 交互式知识图谱
- **可视化关联**：基于 Mermaid.js 自动构建概念间的关联图谱。
- **动态导航**：点击图谱节点即可直接跳转到对应的学习章节。
- **全景视角**：帮助学习者从宏观角度俯瞰知识体系，理清逻辑脉络。

### 3. 📝 沉浸式笔记与标注
- **富文本支持**：完美支持 Markdown、LaTeX 数学公式、代码高亮。
- **智能标注**：支持高亮、下划线、波浪线等多种文本标记方式。
- **自动保存**：所有学习进度、笔记和标注均自动持久化保存。

### 4. 🤖 智能助教与问答
- **上下文感知**：AI 助教了解当前课程内容，提供精准的答疑解惑。
- **划词提问**：选中不懂的文本直接向 AI 提问，获取深度解析。
- **角色扮演**：支持切换 AI 教学风格（如苏格拉底式引导、费曼技巧简化等）。

### 5. 📊 学习追踪与测验
- **智能出题**：根据当前章节内容，AI 自动生成单选、多选测验题。
- **错题本**：自动记录错题，支持针对薄弱环节的针对性复习。
- **学习统计**：可视化展示学习时长、阅读进度和知识点掌握情况。

## 🛠️ 技术栈 (Tech Stack)

### 前端 (Frontend)
- **核心框架**: Vue 3 + TypeScript + Vite
- **UI 组件库**: Element Plus
- **样式**: TailwindCSS
- **可视化**: Mermaid.js (图谱), Highlight.js (代码), KaTeX (公式)
- **状态管理**: Pinia (持久化存储)

### 后端 (Backend)
- **框架**: FastAPI (Python)
- **AI 引擎**: ModelScope API / OpenAI Compatible API
- **任务队列**: 自研异步任务管理器 (Task Manager)
- **数据存储**: 本地文件系统 / OSS (适配 ModelScope 环境)

## 🚀 快速开始 (Quick Start)

### 方式一：Docker 部署 (推荐)

本项目已针对 ModelScope 环境优化，支持一键 Docker 部署。

```bash
# 构建镜像
docker build -t knowledge-map-ai .

# 运行容器
docker run -d -p 7860:7860 \
  -e AI_API_KEY="your_api_key" \
  knowledge-map-ai
```

### 方式二：本地开发

1. **克隆项目**
   ```bash
   git clone https://github.com/your-repo/knowledge-map.git
   cd knowledge-map
   ```

2. **后端启动**
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --host 0.0.0.0 --port 7860 --reload
   ```

3. **前端启动**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## 📸 项目截图 (Screenshots)

| 课程大纲生成 | 知识图谱可视化 |
|:---:|:---:|
| *(此处可放置生成界面的截图)* | *(此处可放置图谱界面的截图)* |

| 沉浸式阅读与笔记 | 智能问答助手 |
|:---:|:---:|
| *(此处可放置阅读器截图)* | *(此处可放置聊天窗口截图)* |

## 🤝 贡献与支持

欢迎提交 Issue 和 Pull Request！如果你喜欢这个项目，请给它一个 ⭐️ Star！

---

*Made with ❤️ for the Hackathon 2026*
