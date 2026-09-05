## Why

Mermaid diagrams in imported Markdown are currently rendered inconsistently: some diagrams show raw Markdown headings, some node labels are clipped for Chinese and mixed-width text, and some math labels are rewritten into visually incorrect quoted forms. This is happening now because the app has two Mermaid rendering paths with different cleanup and SVG post-processing behavior, while backend prompt guidance still encourages label patterns that the frontend later mutates.

## What Changes

- Unify Mermaid sanitization and rendering behavior so all Markdown-rendered diagrams use the same cleanup rules, rendering configuration, and post-processing safeguards.
- Preserve surrounding Markdown structure when Mermaid blocks are rendered so headings and prose continue to be parsed as Markdown rather than leaking raw source text into the UI.
- Improve Mermaid SVG sizing and overflow handling for Chinese text, mixed Chinese/Latin labels, and longer node content so labels are not clipped at the right edge.
- Replace destructive quote-rewrite behavior with syntax repair that keeps mathematical expressions visually correct whenever possible.
- Tighten Mermaid generation guidance on the backend so LLM-produced diagram labels avoid ambiguous quoting patterns that trigger frontend repair work.
- Add regression coverage for the known imported test document and representative Mermaid label edge cases.

## Capabilities

### New Capabilities
- `mermaid-rendering-pipeline`: Define a consistent Mermaid rendering pipeline for imported Markdown, including Markdown preservation, syntax repair, SVG safety adjustments, and regression handling for multilingual labels and formula-heavy diagrams.

### Modified Capabilities

## Impact

- Affected frontend code in `frontend/src/components/MarkdownRenderer.vue`, `frontend/src/composables/useMermaid.ts`, and shared Markdown rendering utilities if Mermaid logic is extracted.
- Affected backend prompt rules in `backend/prompts.py` for Mermaid generation standards.
- Affected regression coverage in `frontend/src/__tests__/utils/markdown.test.ts` and potentially additional import/render integration tests using `tests/test_md_import.md`.
- User-visible impact in note rendering, AI-generated explanations, and imported Markdown documents that contain Mermaid diagrams.
