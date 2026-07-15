# Product Overview

Knowledge Map AI (知识图谱 AI 助手) is an AI-powered interactive knowledge graph generation and learning platform.

Users enter a topic keyword and the system generates a full course outline with a hierarchical node tree (Chapters → Sections → Subsections). Each node's content is generated on-demand by an LLM. The platform includes:

- AI course generation with configurable difficulty (beginner/intermediate/advanced) and teaching style (academic/industrial/socratic/humorous)
- Interactive knowledge graph visualization (Mermaid.js)
- Socratic AI tutor chatbot with streaming responses
- Quiz generation with adaptive difficulty and performance analysis
- Note-taking with highlights, tags, categories, and AI-generated summaries
- Spaced repetition review system (SM-2 algorithm)
- Learning statistics tracking (study time, streaks, mastery levels)
- Markdown/JSON export of notes

The primary language of the UI and generated content is Chinese (Simplified). Code comments and docstrings are also predominantly in Chinese.

The AI backend uses ModelScope API (Qwen models) via an OpenAI-compatible client. Model selection is configurable via environment variables (`AI_API_KEY`, `AI_API_BASE`, `AI_MODEL`, `AI_MODEL_FAST`).
