# Tech Stack & Build

## Backend
- Python 3.10, FastAPI, Uvicorn
- Pydantic for request/response models
- AsyncOpenAI client (openai SDK) for LLM calls
- File-based JSON storage (no database) in `backend/data/`
- WebSocket support for real-time task progress
- Background task manager with threading for course generation

## Frontend
- Vue 3 (Composition API, `<script setup>`)
- TypeScript ~5.7
- Vite 6 (build & dev server)
- Pinia for state management
- Element Plus UI component library
- TailwindCSS 4 with `@tailwindcss/typography` and `@tailwindcss/forms` plugins
- Mermaid.js for diagram rendering
- markdown-it + KaTeX for content rendering
- Axios for HTTP, lucide-vue-next for icons
- Vitest + jsdom for testing

## Shared
- `shared/prompt_config.py` (Python) and `shared/prompt-config.ts` (TypeScript) define shared enums and validation rules (difficulty levels, teaching styles, parameter ranges) used by both frontend and backend.

## Common Commands

```bash
# Full dev environment (starts both frontend and backend)
./dev.sh

# Backend only
cd backend
pip install -r requirements.txt
PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend only
cd frontend
npm install
npm run dev

# Frontend build (type-check + vite build)
cd frontend
npm run build

# Frontend tests
cd frontend
npm run test          # single run (vitest run)
npm run test:watch    # watch mode

# Docker build (production)
docker build -t knowledge-map-ai .
```

## Environment Variables
- `AI_API_KEY` — LLM API key (required)
- `AI_API_BASE` — LLM API base URL (default: ModelScope inference endpoint)
- `AI_MODEL` — Smart/primary model ID (default: `Qwen/Qwen3-32B`)
- `AI_MODEL_FAST` — Fast model for simple tasks (default: same as AI_MODEL)

## Key Conventions
- Backend uses `PYTHONPATH=..` so imports from `shared/` resolve correctly
- Vite proxies `/api`, `/courses`, `/generate_course`, `/ask`, `/ws`, and other backend routes to `localhost:8000` during development
- Frontend path alias: `@` → `frontend/src/`
- Production: frontend is built to `frontend/dist/`, copied into `backend/static/`, and served by FastAPI's `StaticFiles`
