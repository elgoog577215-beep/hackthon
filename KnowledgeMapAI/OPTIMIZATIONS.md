# Optimization Log

Target: 100 Optimizations.

## Categories
- **[FIX]**: Bug fixes
- **[UI]**: UI/UX improvements
- **[CODE]**: Code quality, refactoring, cleanup
- **[PERF]**: Performance improvements
- **[SEC]**: Security improvements

## List

1. [FIX] Backend: Fix `NameError: LocateNodeRequest` in `main.py` by ensuring correct import.
2. [CODE] Backend: Switch from wildcard import `from models import *` to explicit imports in `main.py` for better readability and static analysis.
3. [UI] Frontend: Remove "Coming Soon" tooltip from Export button in `ContentArea.vue` (feature is implemented).
4. [CODE] Backend: Add `LocateNodeRequest` to `models.py` (Completed in previous turn, verified).
5. [CODE] Frontend: Remove debug `console.log` from `main.ts`.
6. [CODE] Frontend: Clean up commented-out dead code in `markdown.ts`.
7. [CODE] Frontend: Improve type safety for `typingInterval` in `course.ts` (replace `any` with `number | null`).
8. [CODE] Backend: Replace `print` with `logger.warning` in `ai_service.py` for proper logging.
9. [UI] Frontend: Replace hardcoded colors with Tailwind theme values in `ContentArea.vue`.
10. [CODE] Backend: Replace `print` with `logger.warning` in `storage.py`.
11. [CODE] Backend: Replace bare `except:` with `except Exception:` in `storage.py` to avoid catching system exit signals.
12. [UI] Frontend: Add clear button transition and logic in `CourseTree.vue`.
13. [CODE] Frontend: Add `AIContent` and `ChatMessage` interfaces to `course.ts` for type safety.
14. [CODE] Frontend: Improve `addMessage` function type safety in `course.ts`.
15. [CODE] Frontend: Replace `Math.random().toString(36)` with `crypto.randomUUID()` for queue item UUID generation in `course.ts`.
16. [CODE] Frontend: Improve error handling in `processQueue` function in `course.ts`.
17. [CODE] Frontend: Improve `saveAnnotation` function type safety and ID generation in `course.ts`.
18. [CODE] Frontend: Improve AI message placeholder type safety and ID generation in `course.ts`.
19. [CODE] Frontend: Replace `Date.now()` with `crypto.randomUUID()` for note ID generation in `ChatPanel.vue`.
20. [CODE] Frontend: Replace `console.error` with `console.warn` for Markdown render errors in `ChatPanel.vue`.
21. [CODE] Backend: Define `AddNodeRequest` Pydantic model in `models.py` and use it in `main.py`.
22. [CODE] Backend: Define `SaveAnnotationRequest` Pydantic model in `models.py` and use it in `main.py`.
23. [CODE] Backend: Define `UpdateNodeRequest` Pydantic model in `models.py` and use it in `main.py`.
24. [CODE] Backend: Use `ExtendContentRequest` Pydantic model in `main.py` instead of raw dict.
25. [UI] Frontend: Replace hardcoded `purple` colors with `primary` theme colors in `ContentArea.vue` and `ChatPanel.vue` for consistency.
26. [CODE] Frontend: Add comment to `buildTree` in `course.ts` to clarify reactive mutation intent.
27. [CODE] Backend: Update `AskQuestionRequest` in `models.py` to include `history`, `selection`, and `user_persona`.
28. [FIX] Backend: Fix method name mismatch in `main.py` calling `redefine_node_content` instead of `redefine_content_stream`.
29. [FIX] Backend: Pass `original_content` to `redefine_node_content` in `main.py` to match signature.
30. [CODE] Backend: Improve error logging in `storage.py` (replace swallow exceptions with `logger.warning`).
31. [FIX] Backend: Implement upsert logic in `save_annotation` in `storage.py` to prevent duplicates.
32. [UI] Frontend: Remove intrusive debug error handlers (red overlays) from `main.ts` for cleaner production UI.
33. [CODE] Backend: Update `ai_service.redefine_content` and `redefine_node` endpoint to support full context (original content, course context) for better generation quality.
34. [CODE] Frontend: Extract option label generation logic (`getOptionLabel`) in `ChatPanel.vue` for cleaner template.
35. [CODE] Frontend: Improve type safety in `course.ts` by replacing `any[]` with `unknown[]` for `detail_answer`.
36. [FIX] Backend: Fix `IndentationError` in `storage.py` that caused server crash and data loss appearance.
