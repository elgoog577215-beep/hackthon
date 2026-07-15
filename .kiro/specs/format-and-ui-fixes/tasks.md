# Implementation Plan

- [x] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** — Format & UI Defects Exist on Unfixed Code
  - **CRITICAL**: These tests MUST FAIL on unfixed code — failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior — they will validate the fixes when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate all 4 bugs exist
  - Test file: `frontend/src/tests/formatAndUiFixes.bugCondition.spec.ts`
  - **Bug 1 — AI button occlusion**: Render `CourseView.vue` with `isFocusMode = false` and `sideAIPanelVisible = false`. Assert the AI floating button has class `bottom-20` (not `bottom-6`). On unfixed code this FAILS because button uses `bottom-6`.
  - **Bug 2 — Highlight stacking**: Create a format note with `style: 'highlight'`, `color: 'yellow'`, `quote: text`, `nodeId: id`. Call `applyFormat('highlight', 'yellow')` on the same selection. Assert `noteStore.notes` count for that quote decreases (toggle off). On unfixed code this FAILS because a second note is created.
  - **Bug 2 — Highlight replace**: Create a yellow highlight note. Call `applyFormat('highlight', 'green')` on the same selection. Assert the remaining note has `color: 'green'` and count is unchanged. On unfixed code this FAILS because both yellow and green notes exist.
  - **Bug 2 — Clear formats missing**: Assert the selection menu template contains a "清除格式" button or `clearFormats` function exists. On unfixed code this FAILS.
  - **Bug 3 — CSS pollution**: Call `wrapRange` with a note `{ sourceType: 'format', style: 'bold' }`. Assert the created span does NOT contain class `highlight-marker`. On unfixed code this FAILS because all spans get `highlight-marker`.
  - **Bug 3 — CSS pollution (solid/wavy)**: Call `wrapRange` with `style: 'solid'` and `style: 'wavy'`. Assert spans use `format-marker` not `highlight-marker`. On unfixed code this FAILS.
  - **Bug 4 — Badge inflation**: Create notes array with mix of `sourceType: 'user'`, `'ai'`, `'format'`. Compute `notesCount`. Assert it equals count of non-format notes only. On unfixed code this FAILS because `notes.length` includes format notes.
  - **Scoped PBT Approach**: For Bug 2, generate random highlight colors and text selections; for Bug 4, generate random note arrays with mixed sourceTypes
  - Run tests on UNFIXED code — expect FAILURE (confirms bugs exist)
  - Document counterexamples found
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Write preservation property tests (BEFORE implementing fixes)
  - **Property 2: Preservation** — Existing Non-Bug Behaviors Unchanged
  - **IMPORTANT**: Follow observation-first methodology — observe behavior on UNFIXED code, then write tests asserting that behavior
  - Test file: `frontend/src/tests/formatAndUiFixes.preservation.spec.ts`
  - **Bug 1 Preservation**: When `isFocusMode = true` (SmartBar hidden), the AI floating button positioning is unaffected by the fix. Verify button renders without `bottom-20` override in focus mode.
  - **Bug 2 Preservation — New highlight creation**: For unhighlighted text (no existing highlight note for that quote/nodeId), calling `applyFormat('highlight', color)` creates a new highlight note. Generate random colors and text — assert `noteStore.notes.length` increases by 1. Verify on UNFIXED code this PASSES.
  - **Bug 2 Preservation — Non-highlight toggle**: For already-formatted text with bold/solid/wavy, calling `applyFormat` with the same style toggles it off. This existing toggle logic must remain unchanged. Verify on UNFIXED code this PASSES.
  - **Bug 3 Preservation — Highlight spans keep styling**: For notes with `sourceType: 'format'` and `color !== 'transparent'` (highlight type), `wrapRange` still applies `highlight-marker` class and the corresponding color class. Verify on UNFIXED code this PASSES.
  - **Bug 4 Preservation — user/ai/wrong notes counted**: Generate random note arrays containing only `sourceType: 'user'`, `'ai'`, `'wrong'` (no format notes). Assert `notesCount` equals `notes.length`. Property-based: for all arrays of non-format notes, count equals array length. Verify on UNFIXED code this PASSES.
  - **Bug 4 Preservation — Export exclusion unchanged**: Verify that note export logic in `course.ts` continues to exclude format notes (already implemented).
  - Run tests on UNFIXED code — **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Fix Bug 1: AI 助手浮动按钮定位

  - [x] 3.1 Change button positioning from `bottom-6` to `bottom-20` in CourseView.vue
    - Locate the AI floating button template (line ~82) in `CourseView.vue`
    - Change Tailwind class `bottom-6` to `bottom-20` (= 5rem = 80px), placing button fully above SmartBar (56px) with 24px margin
    - _Bug_Condition: isBugCondition_Bug1(state) — SmartBar visible (isFocusMode === false), button uses bottom-6 (24px < 56px SmartBar height)_
    - _Expected_Behavior: button bottom >= 80px, fully visible above SmartBar_
    - _Preservation: focus mode (isFocusMode = true) positioning unchanged — SmartBar hidden, button still accessible_
    - _Requirements: 2.1, 3.1_

- [x] 4. Fix Bug 2: 高亮 toggle/替换逻辑 + 清除格式按钮

  - [x] 4.1 Extend `applyFormat` toggle logic to include highlight style
    - In `ContentArea.vue`, locate the toggle check in `applyFormat` (line ~1771): `if (style !== 'highlight' && nodeId)`
    - Change condition to `if (nodeId)` so highlight enters the toggle/replace path
    - For highlight style, match existing notes by `n.style === 'highlight'` (regardless of color)
    - If existing highlight found with same color → delete note + unwrap DOM span (toggle off), return early
    - If existing highlight found with different color → delete old note + unwrap old DOM span, then continue to create new note with new color (replace)
    - Keep bold/solid/wavy toggle logic unchanged (match by exact style)
    - _Bug_Condition: isBugCondition_Bug2(input) — existing highlight note for same quote/nodeId_
    - _Expected_Behavior: same color → toggle off; different color → replace_
    - _Preservation: unhighlighted text highlight creation unchanged; bold/solid/wavy toggle unchanged_
    - _Requirements: 2.2, 2.3, 3.2, 3.3, 3.4_

  - [x] 4.2 Add `clearFormats` function and "清除格式" button
    - Implement `clearFormats()` function: find all notes with `sourceType === 'format'` matching current selection's `nodeId` and `quote`, delete each note via `noteStore.deleteNote()`, and unwrap their DOM spans
    - Add a "清除格式" button in the selection menu template (around line 309, after existing format buttons)
    - Button calls `clearFormats()` on click
    - _Bug_Condition: user selects formatted text, no clear button exists_
    - _Expected_Behavior: button visible in menu, clicking removes all format notes for selection_
    - _Requirements: 2.4_

- [x] 5. Fix Bug 3: 非高亮格式 span CSS 类污染

  - [x] 5.1 Split `highlight-marker` into `format-marker` for non-highlight formats in `wrapRange`
    - In `ContentArea.vue`, locate `wrapRange` function (line ~1862)
    - Replace the unconditional `highlight-marker` base class with conditional logic:
      - For `sourceType === 'format'` with `style` in `['bold', 'solid', 'wavy']`: use `format-marker` class (no background, no border from CSS)
      - For `sourceType === 'format'` with highlight color (`color !== 'transparent'`): keep `highlight-marker` + color class
      - For non-format notes (ai, user, etc.): keep `highlight-marker` as before
    - _Bug_Condition: isBugCondition_Bug3(note) — format note with style bold/solid/wavy gets highlight-marker CSS_
    - _Expected_Behavior: bold/solid/wavy spans use format-marker (no yellow background/border)_
    - _Preservation: highlight spans and non-format note spans retain highlight-marker styling_
    - _Requirements: 2.5, 3.5_

  - [x] 5.2 Add `.format-marker` CSS rule
    - Add a `.format-marker` CSS rule in `ContentArea.vue` styles with only `transition: all 0.2s ease; cursor: pointer;` — no background-color, no border-bottom, no mix-blend-mode
    - _Requirements: 2.5_

- [x] 6. Fix Bug 4: SmartBar badge 排除 format 笔记

  - [x] 6.1 Filter `sourceType !== 'format'` in `notesCount` computed property
    - In `CourseView.vue` (line ~552), change:
      `const notesCount = computed(() => noteStore.notes?.length || 0)`
      to:
      `const notesCount = computed(() => noteStore.notes?.filter(n => n.sourceType !== 'format').length || 0)`
    - _Bug_Condition: isBugCondition_Bug4(notes) — format notes exist, inflating count_
    - _Expected_Behavior: notesCount === notes.filter(n => n.sourceType !== 'format').length_
    - _Preservation: user/ai/wrong notes still counted; export exclusion unchanged_
    - _Requirements: 2.6, 3.6, 3.7_

- [x] 7. Verify all bug condition exploration tests now pass

  - [x] 7.1 Verify Bug 1-4 exploration tests pass
    - **Property 1: Expected Behavior** — All 4 Bugs Fixed
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior for all 4 bugs
    - Run: `cd frontend && npx vitest run src/tests/formatAndUiFixes.bugCondition.spec.ts`
    - **EXPECTED OUTCOME**: All tests PASS (confirms all bugs are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 7.2 Verify preservation tests still pass
    - **Property 2: Preservation** — No Regressions
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run: `cd frontend && npx vitest run src/tests/formatAndUiFixes.preservation.spec.ts`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in existing behavior)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 8. Checkpoint — Ensure all tests pass
  - Run all frontend tests: `cd frontend && npm run test`
  - Verify no regressions in existing test suites
  - Ensure all 4 bugs are addressed and all property tests pass
  - Ask the user if questions arise
