# Implementation Plan: Side AI Panel (右侧滑出式 AI 面板)

## Overview

Replace the floating AI assistant with a right-side sliding panel. Implementation proceeds bottom-up: create the new SideAIPanel component, integrate it into CourseView with layout management, modify ContentArea to emit quote-ask events and lift state, then remove the old FloatingAIAssistant. Each step builds on the previous one, ending with wiring and cleanup.

## Tasks

- [x] 1. Create SideAIPanel component with core UI structure
  - [x] 1.1 Create `frontend/src/components/SideAIPanel.vue` with props (`visible`, `quoteText`, `quoteNodeId`), emits (`close`, `update:visible`), and the basic panel layout: header with title and close button, scrollable chat area, bottom input section with QuoteCard, SuggestionButtons, and text input with send button
    - Panel header: "AI 助手" title + close button (X icon from lucide-vue-next)
    - Chat area: scrollable div bound to `courseStore.chatHistory`, render messages with markdown-it + KaTeX (reuse existing markdown pipeline)
    - QuoteCard: single-line truncated quote text with left border accent, subtle background, and dismiss button (↩ icon). Visible only when `showQuoteCard` is true
    - SuggestionButtons: three pill-shaped buttons ("解释一下 →", "详细展开 →", "深入研究 →"), visible only when `showSuggestions` is true and `showQuoteCard` is true
    - Input area: textarea with send button, Enter to send, Shift+Enter for newline
    - Internal state: `showQuoteCard`, `showSuggestions`, `inputMessage` refs
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.4, 4.1, 5.1_

  - [x] 1.2 Implement chat interaction logic in SideAIPanel
    - Send message via `courseStore.sendMessage()` on Enter or send button click
    - Compose prompt for suggestion buttons: combine quote text + suggestion keyword, call `courseStore.sendMessage()`
    - Hide suggestions after any suggestion button click (`showSuggestions = false`)
    - Dismiss QuoteCard: set `showQuoteCard = false` and `showSuggestions = false`, panel stays open
    - Disable send button when input is empty/whitespace-only OR `courseStore.chatLoading` is true
    - Show loading indicator and cancel/stop button when `courseStore.chatLoading` is true
    - Auto-scroll to latest message on chatHistory changes
    - Support streaming responses (already handled by courseStore, just render reactively)
    - _Requirements: 3.2, 3.3, 2.4, 4.2, 4.3, 4.4, 4.5, 5.2, 5.3, 5.4, 5.5_

  - [x] 1.3 Implement responsive layout in SideAIPanel
    - Computed `isOverlayMode`: `window.innerWidth < 1024`
    - Listen to `resize` events to update overlay mode reactively
    - Desktop (≥1024px): flex child, `w-1/3` with min 320px, max 480px
    - Mobile (<1024px): fixed overlay, `inset-y-0 right-0 w-full`, with semi-transparent backdrop
    - Backdrop click closes panel in overlay mode
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 1.4 Implement re-quote behavior: watch `quoteText` prop changes, reset `showQuoteCard = true` and `showSuggestions = true` when quote text changes to a new non-empty value
    - _Requirements: 7.2_

- [x] 2. Integrate SideAIPanel into CourseView and manage layout state
  - [x] 2.1 Add SideAIPanel state and layout snapshot/restore logic to `frontend/src/views/CourseView.vue`
    - Add refs: `sideAIPanelVisible`, `sideAIQuoteText`, `sideAIQuoteNodeId`, `layoutBeforePanel`
    - Implement `openSideAIPanel({ text, nodeId })`: save current `leftVisible` and `notesCollapsed` into `layoutBeforePanel`, set `leftVisible = false`, `notesCollapsed = true`, populate quote state, set `sideAIPanelVisible = true`
    - Implement `closeSideAIPanel()`: set `sideAIPanelVisible = false`, restore `leftVisible` and `notesCollapsed` from `layoutBeforePanel`, clear snapshot
    - _Requirements: 1.2, 1.3, 6.2, 6.3_

  - [x] 2.2 Add SideAIPanel to CourseView template with slide-in transition
    - Import and render `SideAIPanel` inside `main-content-wrapper`, after ContentArea
    - Wrap in `<Transition name="slide-in-right">` with `v-if="sideAIPanelVisible"`
    - Pass props: `visible`, `quote-text`, `quote-node-id`
    - Handle `@close` → `closeSideAIPanel()`
    - Add CSS transition: slide-in-from-right 300ms on enter, slide-out-to-right 250ms on leave
    - _Requirements: 1.4, 1.5, 6.5_

  - [x] 2.3 Add Escape key handling for SideAIPanel in CourseView
    - In existing `handleKeydown` or new keydown listener: when `sideAIPanelVisible` is true and Escape is pressed, call `closeSideAIPanel()`
    - _Requirements: 6.4_

  - [x] 2.4 Lift `isNotesCollapsed` from ContentArea to CourseView via v-model
    - Add `notesCollapsed` ref in CourseView
    - Pass to ContentArea as `v-model:notes-collapsed`
    - Wire `openSideAIPanel` and `closeSideAIPanel` to use this lifted state
    - _Requirements: 1.2, 6.2_

- [x] 3. Modify ContentArea to emit quote-ask event and accept lifted notesCollapsed
  - [x] 3.1 Refactor `isNotesCollapsed` in `frontend/src/components/ContentArea.vue` from internal ref to v-model prop
    - Add prop `notesCollapsed: boolean` and emit `update:notesCollapsed`
    - Replace all internal reads of `isNotesCollapsed` with `props.notesCollapsed`
    - Replace all internal writes with `emit('update:notesCollapsed', value)`
    - _Requirements: 1.2, 6.2_

  - [x] 3.2 Change `handleAsk` in ContentArea to emit `quoteAsk` event instead of calling `courseStore.setPendingChatInput()`
    - Add emit `quoteAsk` with payload `{ text: string; nodeId: string }`
    - Detect nodeId from DOM: find closest `[id^="node-"]` ancestor of selection range
    - Emit event and hide selection menu
    - _Requirements: 1.1, 7.1_

  - [x] 3.3 Wire ContentArea's `@quote-ask` event to `openSideAIPanel` in CourseView template
    - Add `@quote-ask="openSideAIPanel"` on the ContentArea element in CourseView
    - _Requirements: 1.1_

- [x] 4. Checkpoint - Verify core panel flow
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Remove FloatingAIAssistant and clean up dead code
  - [x] 5.1 Remove `FloatingAIAssistant.vue` component and its import/usage from `frontend/src/App.vue`
    - Delete `frontend/src/components/FloatingAIAssistant.vue`
    - Remove import and `<FloatingAIAssistant>` tag from App.vue
    - _Requirements: Design decision 3_

  - [x] 5.2 Clean up `showFloatingAI` state from `frontend/src/stores/course.ts`
    - Remove `showFloatingAI` ref and any related methods (e.g., `toggleFloatingAI`, `setPendingChatInput` if no longer used)
    - Verify no other components reference these before removing
    - _Requirements: Design decision 3_

  - [x] 5.3 Add auto-close watcher in SideAIPanel: watch for course/route changes and close panel automatically to prevent stale context
    - _Requirements: Error handling - 面板打开时课程切换_

- [x] 6. Checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ]* 7. Property-based tests
  - [ ]* 7.1 Write property test for quote-ask trigger initialization
    - **Property 1: Quote-ask trigger correctly initializes panel state**
    - Generate random non-empty strings and node IDs, call `openSideAIPanel`, assert `visible === true`, `quoteText` matches, `quoteNodeId` matches
    - **Validates: Requirements 1.1, 7.1**

  - [ ]* 7.2 Write property test for layout state round-trip
    - **Property 2: Layout state round-trip on panel open/close**
    - Generate random boolean pairs `(leftVisible, notesCollapsed)`, execute open → close, assert both restored to original values
    - **Validates: Requirements 1.2, 6.2**

  - [ ]* 7.3 Write property test for quote dismissal
    - **Property 3: Quote dismissal hides card and suggestions without closing panel**
    - Generate random quote text, open panel, dismiss quote, assert `showQuoteCard === false`, `showSuggestions === false`, `visible === true`
    - **Validates: Requirements 2.4**

  - [ ]* 7.4 Write property test for suggestion prompt composition
    - **Property 4: Suggestion button composes correct prompt**
    - Generate random quote text × 3 suggestion types, assert composed prompt contains both quote text and suggestion keyword
    - **Validates: Requirements 3.2**

  - [ ]* 7.5 Write property test for suggestions hidden after click
    - **Property 5: Suggestion buttons hidden after click**
    - For each of 3 button types, click and assert `showSuggestions === false`
    - **Validates: Requirements 3.3**

  - [ ]* 7.6 Write property test for Enter key sends non-empty input
    - **Property 6: Enter key sends non-empty input**
    - Generate random non-empty non-whitespace strings, simulate Enter, assert `sendMessage` called with that input
    - **Validates: Requirements 5.2**

  - [ ]* 7.7 Write property test for send button disabled state
    - **Property 7: Send button disabled state**
    - Generate random `(inputText, chatLoading)` combinations, assert disabled iff input is empty/whitespace OR chatLoading is true
    - **Validates: Requirements 5.4, 5.5**

  - [ ]* 7.8 Write property test for re-quote replacement
    - **Property 8: Re-quote replaces current quote and resets suggestions**
    - Generate two random strings, open with text₁ then text₂, assert quoteText === text₂ and showSuggestions === true
    - **Validates: Requirements 7.2**

  - [ ]* 7.9 Write property test for conversation history accumulation
    - **Property 9: Conversation history accumulates messages**
    - Generate random-length message sequences, send sequentially, assert chatHistory length is monotonically non-decreasing
    - **Validates: Requirements 7.3**

  - [ ]* 7.10 Write property test for viewport-based display mode
    - **Property 10: Panel display mode determined by viewport width**
    - Generate random viewport widths (500-2000), assert `isOverlayMode === (width < 1024)`
    - **Validates: Requirements 8.1, 8.2, 8.3**

- [ ]* 8. Unit tests for edge cases and specific behaviors
  - [ ]* 8.1 Write unit tests in `frontend/src/tests/side-ai-panel.test.ts`
    - Test Escape key closes panel (Requirements 6.4)
    - Test Shift+Enter inserts newline without sending (Requirements 5.3)
    - Test suggestion buttons visible when quoteText is non-empty (Requirements 3.1)
    - Test cancel button visible when chatLoading is true (Requirements 4.5)
    - Test close button exists in panel header (Requirements 6.1)
    - Test panel auto-closes on course/route change (Error handling)
    - _Requirements: 5.3, 6.1, 6.4, 3.1, 4.5_

- [ ] 9. Final checkpoint - All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests cover edge cases and specific UI behaviors not covered by property tests
- The design explicitly reuses `courseStore` chat infrastructure — no new store or backend endpoints needed
