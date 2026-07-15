# Development Conventions & Code Quality

## Codebase Context

This project was developed without consistent context management, which means:
- Features may have been implemented multiple times in slightly different ways
- Dead code, unused state, and orphaned functions are likely present
- Some abstractions may be inconsistent or contradictory (e.g., two different HTTP utility wrappers, duplicate state management patterns)
- Backend routes in `main.py` are monolithic — some endpoints may be unused or superseded

## Code Exploration Guidelines

When exploring the codebase before making changes:
- **Don't assume code is used just because it exists.** Verify call sites before treating something as canonical.
- `frontend/src/stores/course.ts` is very large (~3000 lines) and contains both active logic and legacy/dead code. Read it critically.
- `backend/ai_service.py` is also large (~3000 lines). Focus on the specific method you need rather than reading the whole file.
- `backend/main.py` (~1800 lines) contains all routes. Some may be unused by the frontend — check `frontend/src/utils/http.ts` and `apiClient.ts` for actual call patterns.
- There are two HTTP utility files in the frontend: `utils/http.ts` and `utils/apiClient.ts`. Understand which one is actually used before adding new calls.
- `frontend/src/shared/` mirrors `shared/` at the root — don't edit one without updating the other.

## When Developing New Features

- **Prefer consolidation over addition.** If you find an existing pattern that partially solves the problem, extend it rather than creating a parallel implementation.
- **Remove dead code** encountered along the way — don't leave it "just in case."
- If you find duplicate logic (e.g., two functions doing the same thing), consolidate to one and update all call sites.
- Keep `backend/main.py` route handlers thin — business logic belongs in service modules (`ai_service.py`, `storage.py`, etc.).
- New Pinia state should go in the appropriate existing store unless there's a strong reason for a new one.

## Known Structural Debt

- The course generation queue exists both as a frontend-managed system (in `course.ts`) and a backend task manager (`task_manager.py`). These are partially synchronized via polling and WebSocket. Be careful not to trigger both paths for the same operation.
- `annotations` and `notes` are two overlapping concepts in the frontend store — `notes` is the newer system, `annotations` is legacy. New features should use `notes`.
- Some components may directly call `http` instead of going through the store — this is inconsistent and should be avoided in new code.


## Running Python Code in Shell

When you need to run a Python snippet to test or verify something, **never use `python -c '...'`** — heredoc quoting in bash is fragile and causes frequent parse errors.

Instead:
1. Write the snippet to a temporary file (e.g., `_tmp_check.py`)
2. Run it with `python _tmp_check.py`
3. Delete the file immediately after (`rm _tmp_check.py`)

This applies to any multi-line Python you'd otherwise inline into a shell command.
