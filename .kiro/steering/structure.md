# Project Structure

```
├── backend/                    # FastAPI backend (Python)
│   ├── main.py                # App entry, all API route definitions
│   ├── models.py              # Pydantic request/response models
│   ├── ai_service.py          # LLM interaction layer (course gen, quiz, Q&A, knowledge graph)
│   ├── prompts.py             # Prompt templates for LLM calls
│   ├── storage.py             # File-based JSON storage with in-memory cache
│   ├── task_manager.py        # Background task queue for course generation
│   ├── memory.py              # Long-term memory / session memory
│   ├── tutor_service.py       # Socratic tutor logic
│   ├── agent.py               # Agent orchestration
│   ├── api_response.py        # Response formatting helpers
│   ├── requirements.txt       # Python dependencies
│   ├── start.sh               # Docker entrypoint script
│   ├── data/                  # Runtime data (JSON files, not in git ideally)
│   │   ├── courses/           # One JSON file per course (keyed by UUID)
│   │   ├── knowledge_graphs/  # Cached knowledge graphs per course
│   │   └── annotations.json   # All annotations in a single file
│   └── static/                # Production frontend build output (served by FastAPI)
│
├── frontend/                   # Vue 3 + Vite frontend (TypeScript)
│   ├── src/
│   │   ├── main.ts            # App bootstrap
│   │   ├── App.vue            # Root component
│   │   ├── views/             # Page-level components (CourseView.vue)
│   │   ├── components/        # Reusable UI components
│   │   ├── stores/            # Pinia stores (course.ts, tutor.ts)
│   │   ├── composables/       # Vue composables (useKeyboardShortcuts, useMermaid, etc.)
│   │   ├── api/               # API client modules
│   │   ├── utils/             # Utility modules (apiClient, http, markdown, security, cache, logger)
│   │   ├── router/            # Vue Router config
│   │   ├── types/             # TypeScript type declarations
│   │   ├── styles/            # Global CSS / design system
│   │   ├── shared/            # Shared config mirrored from root shared/
│   │   ├── data/              # Static data (course templates)
│   │   └── tests/             # Vitest test files
│   ├── vite.config.ts         # Vite config (proxy, aliases, chunking)
│   ├── tailwind.config.js     # Tailwind theme customization
│   └── tsconfig.json          # TypeScript project references
│
├── shared/                     # Cross-stack shared config
│   ├── prompt_config.py       # Python: enums, constants, validation
│   └── prompt-config.ts       # TypeScript: mirrored enums and rules
│
├── tests/                      # Backend integration/property tests
│   └── test_course_generation_robustness.py
│
├── docs/                       # Project documentation
│   ├── coding-standards.md    # Code style and naming conventions
│   └── prompt-system.md       # Prompt engineering documentation
│
├── dev.sh / dev.bat           # Dev environment launcher scripts
├── Dockerfile                 # Multi-stage build (Node frontend → Python backend)
└── .env                       # Environment variables (API keys)
```

## Architecture Notes
- Single-page app: the frontend has one main view (`CourseView.vue`) with route params for course selection
- All API routes are defined in `backend/main.py` (monolithic, not split into routers)
- Storage is file-based JSON with an in-memory cache layer and background git auto-sync
- Course generation uses a task queue with WebSocket progress broadcasting
- The `shared/` directory keeps frontend and backend in sync on enums and validation rules — changes must be mirrored in both files
