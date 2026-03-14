# Implementation Plan

## Bug 4: 文字格式化 Toggle (Property-Based Testable)

- [x] 1. Write bug condition exploration test for format toggle
  - **Property 1: Bug Condition** — Format Toggle Creates Duplicate Notes
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate `applyFormat` creates duplicate notes instead of toggling
  - **Scoped PBT Approach**: For each format style (bold/underline/wavy), create a format note for a text selection, then call `applyFormat` again with the same style and selection — assert the note is removed (toggle) rather than a second note being created
  - Test file: `frontend/src/tests/applyFormat.toggle.spec.ts`
  - Generate inputs: `{ style: oneOf('bold', 'underline', 'wavy'), quote: arbitraryString, nodeId: arbitraryNodeId }`
  - Bug condition from design: `isBugCondition_Bug4(input)` — existing format note matches `sourceType === 'format'` AND same `nodeId`, `quote`, and style
  - Assert expected behavior: after second `applyFormat` call, `noteStore.notes.length` decreases by 1 (note deleted, not duplicated)
  - Run test on UNFIXED code — expect FAILURE (confirms bug: notes.length increases instead)
  - Document counterexamples found
  - _Requirements: 2.7, 2.8_

- [x] 2. Write bug condition exploration test for chapter_id matching
  - **Property 1: Bug Condition** — Substring Matching Produces Incorrect chapter_id
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples where substring matching maps to wrong course nodes
  - **Scoped PBT Approach**: Construct graph nodes with ambiguous labels (e.g., "基础") and multiple course nodes containing that substring — assert the matched `chapter_id` corresponds to the most relevant (highest similarity) course node, not just the first substring match
  - Test file: `tests/test_chapter_id_matching.py`
  - Generate inputs: graph node labels and course node lists where `chapter_id` is invalid and no exact label match exists (triggers Priority 2 substring matching)
  - Bug condition from design: `isBugCondition_Bug5(node, courseNodes)` — `chapter_id` not in `valid_chapter_ids` AND no exact label match
  - Assert expected behavior: matched `chapter_id` is the most similar course node by similarity score, not arbitrary first substring match
  - Run test on UNFIXED code — expect FAILURE (confirms bug: first substring match or fallback to `course_nodes[0]`)
  - Document counterexamples found
  - _Requirements: 2.9, 2.10_

- [x] 3. Write preservation property tests (BEFORE implementing fixes)
  - **Property 2: Preservation** — Existing Behaviors Unchanged
  - **IMPORTANT**: Follow observation-first methodology — observe behavior on UNFIXED code, then write tests asserting that behavior
  - **Sub-properties to test:**
  - **Bug 4 Preservation**: For highlight-type format operations (`style === 'highlight'`), `applyFormat` always creates a new note (never toggles). Generate random highlight inputs and verify `noteStore.notes.length` increases by 1. Also verify that deleting a format note via `noteStore.deleteNote()` works correctly.
  - **Bug 5 Preservation**: When `chapter_id` is already in `valid_chapter_ids`, `_validate_and_fix_knowledge_graph` does NOT modify it. Generate graph nodes with valid `chapter_id` values and verify they remain unchanged after validation.
  - Test files: `frontend/src/tests/applyFormat.preservation.spec.ts` and `tests/test_chapter_id_preservation.py`
  - Observe behavior on UNFIXED code for non-bug-condition cases
  - Write property-based tests capturing observed behavior patterns
  - Run tests on UNFIXED code — **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - _Requirements: 3.7, 3.8, 3.9, 3.10_

## Bug 1: AI 助手浮动图标

- [x] 4. Add floating AI assistant button in CourseView.vue
  - [x] 4.1 Add `openSideAIPanelDirect` function
    - Create function similar to `openSideAIPanel` but without setting `quoteText`/`quoteNodeId`
    - Set `sideAIPanelVisible = true` directly
    - Save layout state before opening (same as `openSideAIPanel`)
    - _Bug_Condition: state.textSelection IS EMPTY AND state.sideAIPanelVisible IS false_
    - _Expected_Behavior: clicking button opens SideAIPanel without quote card_
    - _Preservation: existing quote-ask flow via ContentArea unchanged_
    - _Requirements: 2.1, 2.2, 3.1, 3.2_
  - [x] 4.2 Add floating button template in CourseView.vue
    - Add a `position: fixed` button after `ContentArea` section, before `SideAIPanel`
    - Use `v-if="!sideAIPanelVisible && courseStore.currentCourseId"` for conditional rendering
    - Position: `bottom-6 right-6` (or adjust based on notes panel state)
    - Use Bot icon from lucide-vue-next
    - `@click="openSideAIPanelDirect"`
    - Add transition for smooth show/hide
    - _Requirements: 2.1, 2.2, 3.2_
  - [x] 4.3 Verify bug condition exploration test now passes (for Bug 1 component behavior)
    - Manually verify: open course page without text selection → floating button visible → click → SideAIPanel opens
    - Verify: when SideAIPanel is open, floating button is hidden
    - _Requirements: 2.1, 2.2, 3.2_

## Bug 2: 左侧目录宽度和分隔条

- [x] 5. Fix sidebar default width and resizer in CourseView.vue
  - [x] 5.1 Change default leftWidth from 300 to 250
    - In `loadSidebarState()` default object: change `leftWidth: 300` → `leftWidth: 250`
    - In `resetLeftSidebar()`: change `screenWidth >= SCREEN_XL ? 300 : 280` → `screenWidth >= SCREEN_XL ? 250 : 240`
    - _Bug_Condition: state.leftSidebarWidth == 300 on page load_
    - _Expected_Behavior: default leftWidth is 250_
    - _Preservation: double-click reset and mobile overlay behavior unchanged_
    - _Requirements: 2.3, 3.3, 3.4_
  - [x] 5.2 Widen resizer interactive area
    - Change resizer div from `w-1` (4px) to `w-2` (8px) base width
    - Add `hover:w-3` for expanded hover target
    - Ensure cursor and visual feedback remain correct
    - _Bug_Condition: resizerInteractiveWidth <= 4_
    - _Expected_Behavior: resizer width >= 8px, easily draggable_
    - _Requirements: 2.4_

## Bug 3: 回到顶部按钮定位

- [x] 6. Fix back-to-top button overlap with AI panel in ContentArea.vue
  - [x] 6.1 Pass `sideAIPanelVisible` prop from CourseView to ContentArea
    - Add `sideAiPanelVisible` prop (Boolean, default false) to ContentArea's `defineProps`
    - In CourseView.vue, bind `:side-ai-panel-visible="sideAIPanelVisible"` on the `<ContentArea>` component
    - _Requirements: 2.5, 2.6_
  - [x] 6.2 Adjust back-to-top button positioning based on AI panel state
    - Add dynamic style or class to the back-to-top button that increases `right` offset when `sideAiPanelVisible` is true
    - When AI panel is open: shift button left by panel width (min 320px, ~33vw)
    - Use computed property or inline `:style` binding for the `right` value
    - Keep existing media query offsets for notes panel as baseline
    - _Bug_Condition: sideAIPanelVisible IS true AND showBackToTop IS true_
    - _Expected_Behavior: button positioned in content area, not overlapping AI panel_
    - _Preservation: scroll threshold (500px) and smooth scroll behavior unchanged_
    - _Requirements: 2.5, 2.6, 3.5, 3.6_

## Bug 4: 文字格式化 Toggle (Implementation)

- [x] 7. Implement format toggle logic in ContentArea.vue
  - [x] 7.1 Add toggle check in `applyFormat` function
    - Before creating a new format note, search `noteStore.notes` for an existing note matching: `sourceType === 'format'` AND `nodeId` matches AND `quote` matches AND style matches (bold→bold, underline→solid, wavy→wavy)
    - If found: call `noteStore.deleteNote(existingNote.id)`, remove DOM highlight span (find by `highlightId`, unwrap inner text), then return early
    - If not found: proceed with existing create logic
    - Exclude `style === 'highlight'` from toggle logic — highlights always create new notes
    - _Bug_Condition: existingNote with same format exists for selection_
    - _Expected_Behavior: applyFormat removes the note (toggle off) instead of creating duplicate_
    - _Preservation: highlight color application unchanged, noteStore.deleteNote unchanged_
    - _Requirements: 2.7, 2.8, 3.7, 3.8_
  - [x] 7.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Format Toggle Removes Duplicate Notes
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (toggle removes note)
    - Run bug condition exploration test from task 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms format toggle bug is fixed)
    - _Requirements: 2.7, 2.8_
  - [x] 7.3 Verify preservation tests still pass
    - **Property 2: Preservation** — Highlight and Delete Behaviors Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 3 (Bug 4 preservation) — do NOT write new tests
    - Run preservation property tests for format operations
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in highlight/delete behavior)
    - _Requirements: 3.7, 3.8_

## Bug 5: 知识图谱 chapter_id 匹配 (Implementation)

- [x] 8. Improve chapter_id matching in ai_graph_service.py
  - [x] 8.1 Replace substring matching with similarity-scored matching
    - In `_validate_and_fix_knowledge_graph`, replace Priority 2 block (simple `in` substring check) with a scored matching approach
    - Compute character overlap ratio or longest common substring length between `node_label` and each `course_node.node_name`
    - Rank all candidates by score, select the highest-scoring match above a minimum threshold
    - Keep Priority 0 (chapter_id is node_name) and Priority 1 (exact label match) unchanged
    - _Bug_Condition: chapter_id invalid AND no exact label match → enters imprecise substring/fallback_
    - _Expected_Behavior: best similarity match selected instead of first substring hit_
    - _Preservation: valid chapter_ids and exact matches unchanged_
    - _Requirements: 2.9, 2.10, 3.9, 3.10_
  - [x] 8.2 Improve fallback strategy
    - When no match scores above threshold, prefer leaf nodes (higher `node_level`) over root chapters
    - Log a warning when falling back to indicate low-confidence match
    - Final fallback to `course_nodes[0]` only as last resort with explicit warning
    - _Requirements: 2.10_
  - [x] 8.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Similarity Matching Selects Best Node
    - **IMPORTANT**: Re-run the SAME test from task 2 — do NOT write a new test
    - The test from task 2 encodes the expected behavior (best similarity match)
    - Run bug condition exploration test from task 2
    - **EXPECTED OUTCOME**: Test PASSES (confirms matching accuracy improved)
    - _Requirements: 2.9, 2.10_
  - [x] 8.4 Verify preservation tests still pass
    - **Property 2: Preservation** — Valid chapter_ids Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 3 (Bug 5 preservation) — do NOT write new tests
    - Run preservation property tests for chapter_id validation
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions for valid chapter_ids)
    - _Requirements: 3.9, 3.10_

## Final Validation

- [x] 9. Checkpoint — Ensure all tests pass
  - Run all frontend tests: `cd frontend && npm run test`
  - Run all backend tests: `cd tests && python -m pytest test_chapter_id_matching.py test_chapter_id_preservation.py`
  - Verify no regressions in existing test suites
  - Ensure all 5 bugs are addressed and all property tests pass
  - Ask the user if questions arise
