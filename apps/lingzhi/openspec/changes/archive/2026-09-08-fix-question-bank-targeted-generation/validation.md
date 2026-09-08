## Validation

### Automated checks

- Backend targeted regression: 173 passed, 2 xfailed, 1 xpassed.
- Frontend question-bank regression: 25 passed.
- Frontend production build: passed.
- Ruff on all changed Python files: passed.
- `openspec validate fix-question-bank-targeted-generation --strict`: passed.
- Python dependency consistency (`pip check`): passed.
- Chinese and English locale JSON parsing: passed.
- `git diff --check`: passed.

The first full GitHub Actions run exposed six compatibility failures in comprehensive assessments, high-consequence medical questions, learning-asset compilation and student practice projection. The implementation now keeps the existing confirmation gate for comprehensive and high-consequence questions, and rebuilds stored formal-task identities with their private solution envelope after policy application. All six failed tests pass locally before the replacement release run.

The replacement run passed backend tests, compatibility checks and lint, then exposed four stale assertions in the recently rebuilt lesson inline-AI flow. The release repair attaches that integration test to the DOM, submits through the new inline form, checks the inline diff surface, retires the previous candidate before a follow-up, and restores course-plan routing for structural or cross-asset instructions. The affected integration file and the new inline-action suites pass locally before the next release run.

### TDD evidence

- RED: targeted backend tests failed because item-scope resolution, settled-slot extraction and field-level repair guards did not exist.
- RED: the frontend regeneration test proved the current question was rejected before the replacement task started.
- GREEN: item regeneration now requests only the selected `practice_level`; successful replacements keep the stable `item_id`; failed replacements leave the published revision unchanged.
- GREEN: a chapter with two settled questions and one failed question publishes the two successful slots and resumes only the missing slot.
- GREEN: repair output is filtered through issue-specific field paths and unrelated changes are restored before validation.

### Dependency audit

`npm audit --omit=dev` reached the official npm registry and reported 18 existing dependency findings (8 high, 10 moderate), including one `markdown-it-katex` issue without an available fix. No dependency versions changed in this work, and no automatic audit fix was applied.

### Not run

- No production course task was started, stopped or modified.
- No real provider generation or production deployment was performed in this change.
