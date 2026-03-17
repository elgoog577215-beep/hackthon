## 1. Reproduce and isolate the renderer defect

- [x] 1.1 Add or update a regression test in `frontend/src/__tests__/utils/markdown.test.ts` for a multiline `$$ ... $$` block that currently leaks delimiters or falls into inline error rendering.
- [x] 1.2 Add a regression test using a prose-plus-formula pattern derived from imported course content in `backend/data/courses/d71acaff-0f7f-4fff-911c-f027b2a834b5.json`.
- [x] 1.3 Preserve coverage for existing supported math forms, including `$...$` and `\[ ... \]`, so the bug fix can be validated against regressions.

## 2. Fix display-math parsing behavior

- [x] 2.1 Update the custom math parsing logic in `frontend/src/utils/markdown.ts` so valid multiline `$$ ... $$` content is handled as block math rather than partially consumed by inline parsing.
- [x] 2.2 Adjust preprocessing or delimiter masking only as needed so already-valid display-math blocks reach the renderer without delimiter splitting.
- [x] 2.3 Verify the renderer still produces sanitized output and preserves current Mermaid and non-math Markdown behavior.

## 3. Validate with imported content

- [x] 3.1 Run the markdown renderer test suite and confirm the new regression cases pass.
- [x] 3.2 Manually validate the fix against the imported course sample containing multiline formulas to confirm no leaked `$$` delimiters remain.
- [x] 3.3 Document any follow-up issue discovered during validation, such as search-highlighting interference with rendered KaTeX, without expanding this bug fix scope unless necessary.
