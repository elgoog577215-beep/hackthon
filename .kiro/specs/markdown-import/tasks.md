# Implementation Plan: Markdown Import

## Overview

Implement a Markdown-to-course import pipeline: a pure Python parser module, a thin FastAPI route, and a Vue 3 frontend component with a Pinia store action. The parser is independently testable with no I/O; storage interaction is limited to a single `storage.save_course()` call.

## Tasks

- [x] 1. Add `ImportMarkdownResponse` Pydantic model to `backend/models.py`
  - Add `ImportMarkdownResponse(BaseModel)` with fields `course_id: str` and `course_name: str`
  - _Requirements: 4.3_

- [x] 2. Implement `backend/markdown_parser.py` — core parsing logic
  - [x] 2.1 Implement internal helpers: `_detect_min_depth`, `_parse_heading`, `_compute_level`, `_find_parent`, `_process_image`, `_process_body`
    - `_detect_min_depth(lines)` scans all ATX headings and returns the smallest depth
    - `_parse_heading(line)` returns `(depth, text)` or `None`
    - `_compute_level(depth, min_depth)` returns `clamp(depth - min_depth + 1, 1, 3)`
    - `_find_parent(stack, level)` returns `node_id` of nearest ancestor at `level - 1`, or `"root"`
    - `_process_image(alt, url)` preserves external URLs, replaces local paths with `[图片: {alt}]` or `[图片]`
    - `_process_body(raw)` applies `_process_image` substitution via `IMAGE_RE` regex, handles caption detection
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4, 3.1, 3.2, 3.3_

  - [x] 2.2 Implement `parse_markdown_to_nodes(text, filename) -> tuple[list[dict], str]`
    - Scan for `min_depth`, walk lines with ancestor stack, finalize nodes, handle pre-heading text as synthetic root node
    - Raise `ValueError` if no ATX headings found
    - Each node dict must include all fields: `node_id` (UUID), `parent_node_id`, `node_name`, `node_level`, `node_content`, `node_type="original"`, `is_read=False`, `quiz_score=None`, `create_time` (ISO 8601 UTC)
    - `course_name` derived from first level-1 heading, or `filename` as fallback
    - _Requirements: 1.1–1.7, 2.1–2.4, 3.1–3.3_

  - [x] 2.3 Implement `pretty_print(nodes: list[dict]) -> str`
    - `node_level 1` → `#`, `2` → `##`, `3` → `###`
    - Blank line between heading and `node_content`; blank line before next heading
    - _Requirements: 7.1, 7.2_

  - [ ]* 2.4 Write property test for relative heading level mapping (Property 1)
    - **Property 1: Relative heading level mapping**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5**
    - Use Hypothesis `@composite` `heading_strategy` to generate lists of `(depth, text)` pairs; build a Markdown string; assert every node's `node_level == clamp(depth - min_depth + 1, 1, 3)`
    - File: `tests/test_markdown_import.py`

  - [ ]* 2.5 Write property test for parent chain invariant (Property 2)
    - **Property 2: Parent chain invariant**
    - **Validates: Requirements 1.2, 1.4**
    - Use `markdown_document_strategy()`; assert every node with `node_level > 1` has a `parent_node_id` pointing to a node with `node_level == current - 1`; level-1 nodes have `parent_node_id == "root"`
    - File: `tests/test_markdown_import.py`

  - [ ]* 2.6 Write property test for node fields invariant (Property 3)
    - **Property 3: Node fields invariant**
    - **Validates: Requirements 1.6, 1.7**
    - Assert all `node_id` values are distinct valid UUIDs and every node has `node_type == "original"`
    - File: `tests/test_markdown_import.py`

  - [ ]* 2.7 Write property test for body content assignment (Property 4)
    - **Property 4: Body content assignment**
    - **Validates: Requirements 2.1, 2.3**
    - Use `markdown_with_bodies_strategy()`; assert `node_content` equals the stripped text between consecutive headings; empty body → `""`
    - File: `tests/test_markdown_import.py`

  - [ ]* 2.8 Write property test for inline formatting preservation (Property 5)
    - **Property 5: Inline formatting preservation**
    - **Validates: Requirements 2.4**
    - Use `content_with_formatting_strategy()` to generate content with bold, italic, inline code, strikethrough, highlight, and link spans; assert spans appear verbatim in `node_content`
    - File: `tests/test_markdown_import.py`

  - [ ]* 2.9 Write property test for image handling (Property 6)
    - **Property 6: Image handling**
    - **Validates: Requirements 3.1, 3.2**
    - Use `markdown_with_images_strategy()`; assert external images are preserved as-is; local paths are replaced with `[图片: {alt}]` or `[图片]`
    - File: `tests/test_markdown_import.py`

  - [ ]* 2.10 Write property test for parse → print → parse round-trip (Property 8)
    - **Property 8: Parse → print → parse round-trip**
    - **Validates: Requirements 7.1, 7.2, 7.3**
    - Use `markdown_document_strategy(max_depth=3)` (headings only at levels 1–3); parse → `pretty_print` → parse again; assert identical `node_name`, `node_content`, `node_level`, `parent_node_id` (exclude `node_id` from comparison)
    - File: `tests/test_markdown_import.py`

- [x] 3. Checkpoint — parser unit tests
  - Write concrete unit tests in `tests/test_markdown_import.py` covering:
    - Pre-heading text creates synthetic root node named after filename
    - Document with only `##` headings maps all to `node_level = 1`
    - `####` headings in a `#`-rooted doc flatten to `node_level = 3`
    - Local image replaced; external URL preserved; empty alt → `[图片]`
    - Empty body between consecutive headings → `node_content = ""`
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 1.1–1.7, 2.1–2.4, 3.1–3.2_

- [x] 4. Implement `POST /api/import_markdown` route in `backend/main.py`
  - [x] 4.1 Add the route handler (thin — delegate to parser and storage)
    - Read file bytes once; check size ≤ 20 MB (HTTP 413) and non-empty (HTTP 400)
    - Check MIME type in `{"text/markdown", "text/plain", "application/octet-stream"}` (HTTP 415)
    - Decode bytes as UTF-8; raise HTTP 422 on `UnicodeDecodeError`
    - Call `parse_markdown_to_nodes(text, stem)`; catch `ValueError` → HTTP 422 with heading-missing message
    - Build `course_tree` dict (see design Data Models section); call `storage.save_course(course_id, course_tree)`
    - Return `ImportMarkdownResponse(course_id=..., course_name=...)`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3_

  - [ ]* 4.2 Write unit tests for the route handler error paths
    - Test HTTP 400 on empty file, 413 on >20 MB, 415 on wrong MIME, 422 on non-UTF-8, 422 on no headings
    - Use FastAPI `TestClient`
    - _Requirements: 4.4, 4.5, 5.1, 5.2, 5.3_

  - [ ]* 4.3 Write property test for storage round-trip (Property 7)
    - **Property 7: Storage round-trip**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - Use `markdown_document_strategy()`; call the route via `TestClient`; assert `course_id` is loadable via `storage.load_course` and the returned tree has matching `course_name` and node count
    - File: `tests/test_markdown_import.py`

- [x] 5. Checkpoint — backend integration
  - Ensure all backend tests pass, ask the user if questions arise.

- [x] 6. Add `hypothesis` to `backend/requirements.txt`
  - Append `hypothesis` (latest compatible version) to `backend/requirements.txt`
  - _Requirements: (testing infrastructure)_

- [x] 7. Implement `importMarkdown` action in `frontend/src/stores/course.ts`
  - Add `async importMarkdown(file: File): Promise<{ course_id: string; course_name: string }>` to the store
  - Build a `FormData` with the file; POST to `/api/import_markdown` using the existing `http` utility (same pattern as `createCourse`)
  - On success: call `fetchCourseList()` then `loadCourse(course_id)`
  - On error: propagate the server error message for the component to display
  - _Requirements: 6.4_

- [x] 8. Implement `frontend/src/components/MarkdownImport.vue`
  - [x] 8.1 Build the component UI
    - Element Plus dialog or drawer with a file input accepting `.md,.txt`
    - Display selected filename and file size after selection
    - "上传" confirm button (disabled while `uploading`) and a cancel button
    - Loading indicator (`v-loading` or `ElLoading`) while upload is in progress
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

  - [x] 8.2 Wire upload logic
    - On confirm: call `courseStore.importMarkdown(file)`; on success navigate to the new course (router push to course route with `course_id`)
    - On error: display server error message via `ElNotification`
    - _Requirements: 6.4, 6.5_

  - [ ]* 8.3 Write unit tests for `MarkdownImport.vue`
    - Test that the upload button is disabled while `uploading = true`
    - Test that filename and size are displayed after file selection
    - Test that `ElNotification` is called with the error message on failure
    - File: `frontend/src/tests/MarkdownImport.spec.ts`
    - _Requirements: 6.2, 6.3, 6.5, 6.6_

- [x] 9. Integrate `MarkdownImport.vue` into the course list area
  - Import and register `MarkdownImport.vue` in the appropriate parent component (likely `CourseView.vue` or the sidebar/course-list area)
  - Add a trigger button (e.g., "导入 Markdown") that opens the dialog
  - _Requirements: 6.1_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Run `cd frontend && npm run test` and `cd tests && python -m pytest test_markdown_import.py`
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- `markdown_parser.py` must have zero imports from `storage.py` or any other backend module — pure functions only
- All storage interaction goes through `storage.save_course()` exclusively
- Property tests use Hypothesis; add `hypothesis` to `backend/requirements.txt` before running them
- The `importMarkdown` store action must use the `http` utility (not `apiClient`) to match the existing pattern in `course.ts`
