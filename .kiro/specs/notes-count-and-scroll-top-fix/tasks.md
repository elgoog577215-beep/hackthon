# Implementation Tasks

## Bug 1: SmartBar 笔记计数修复

- [x] 1.1 Fix notesCount computed property in CourseView.vue
  - [x] 1.1.1 Update the filter on line 552 to exclude both 'format' and 'wrong' sourceTypes: `noteStore.notes?.filter(n => n.sourceType !== 'format' && n.sourceType !== 'wrong').length || 0`

- [x] 1.2 Write exploratory bug condition test for notesCount
  - [x] 1.2.1 (PBT) Create `frontend/src/tests/notesCountBugCondition.spec.ts` — generate random note arrays with mixed sourceTypes including 'wrong', compute notesCount using the FIXED filter (`!== 'format' && !== 'wrong'`), assert it equals the count of notes where sourceType is 'user', 'ai', or undefined. **Property 1**

- [x] 1.3 Write preservation test for notesCount
  - [x] 1.3.1 (PBT) In the same test file, generate random note arrays with ONLY 'user'/'ai'/undefined sourceTypes (no 'wrong', no 'format'), verify notesCount equals array length (same as original behavior). **Property 2**

## Bug 2: 回到顶部按钮定位修复

- [x] 2.1 Fix back-to-top button positioning in ContentArea.vue
  - [x] 2.1.1 Change `.back-to-top` CSS `bottom` from `5.5rem` to `8.5rem` to position it above the AI assistant button (AI button is at `bottom: 5rem`, height ~3rem, plus 0.5rem gap)
  - [x] 2.1.2 Remove the `@media (min-width: 768px)` and `@media (min-width: 1280px)` CSS rules that shift `.back-to-top` right offset — these use screen width which doesn't match the actual notes column state
  - [x] 2.1.3 Update `backToTopStyle` computed property to dynamically set `right` based on `notesCollapsed` prop (matching AI button logic): collapsed → `right: 1.5rem`, expanded → `right: 340px`, AI panel open → `right: calc(33vw + 1rem)`
  - [x] 2.1.4 Update `.back-to-top` base CSS `right` from `1rem` to remove it (let `backToTopStyle` control it entirely), or set a default that `backToTopStyle` overrides

- [ ] 2.2 Verify button positioning does not regress
  - [ ] 2.2.1 Manually verify: scroll page > 500px, confirm back-to-top button appears above AI button with no overlap
  - [ ] 2.2.2 Manually verify: toggle notes column open/closed, confirm both buttons remain at consistent right position
  - [ ] 2.2.3 Manually verify: click AI assistant button, confirm panel opens normally

- [x] 2.3 Run existing tests to confirm no regressions
  - [x] 2.3.1 Run `cd frontend && npx vitest run` to verify all existing tests pass
