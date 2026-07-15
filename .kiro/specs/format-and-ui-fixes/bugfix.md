# Bugfix Requirements Document

## Introduction

本文档涵盖四个相关的 UI 和格式化 bug，均涉及前端组件 `CourseView.vue`、`ContentArea.vue` 和 `SmartBar.vue` 中的显示与交互问题：

1. AI 助手浮动按钮被底部 SmartBar 遮挡，无法完整显示
2. 高亮操作可多次叠加，缺少 toggle/替换逻辑和清除格式按钮
3. 划线（underline）和加粗（bold）的 DOM 渲染效果被 `.highlight-marker` 基础 CSS 样式污染，显示为高亮背景而非纯文本装饰
4. 格式化操作（`sourceType === 'format'`）被计入 SmartBar 笔记数，导致笔记计数虚高

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the AI assistant floating button is rendered in `CourseView.vue` with `bottom-6` positioning AND the SmartBar bottom navigation bar is visible THEN the system displays the button partially hidden behind the SmartBar

1.2 WHEN a user selects already-highlighted text and clicks the same highlight color THEN the system creates an additional overlapping highlight note instead of toggling it off

1.3 WHEN a user selects already-highlighted text and clicks a different highlight color THEN the system creates a second highlight note on top of the existing one instead of replacing the color

1.4 WHEN a user wants to remove all formatting (highlight/underline/bold/wavy) from selected text THEN the system provides no "clear all formats" button in the selection menu

1.5 WHEN a format note with `style: 'solid'` (underline) or `style: 'bold'` is rendered as a `<span>` with class `highlight-marker` THEN the system applies the `.highlight-marker` base CSS (yellow background, bottom border, mix-blend-mode) to the span, making underline and bold text look like highlighted text instead of clean text decorations

1.6 WHEN format notes (`sourceType === 'format'`) exist THEN the system counts them in `notesCount` computed property (`noteStore.notes?.length`), inflating the SmartBar badge number with formatting operations that are not user-authored notes

### Expected Behavior (Correct)

2.1 WHEN the AI assistant floating button is rendered AND the SmartBar is visible THEN the system SHALL position the button high enough (e.g. `bottom-20` or equivalent) so it is fully visible above the SmartBar

2.2 WHEN a user selects already-highlighted text and clicks the same highlight color THEN the system SHALL remove the existing highlight note and unwrap the DOM span (toggle off)

2.3 WHEN a user selects already-highlighted text and clicks a different highlight color THEN the system SHALL delete the old highlight note, remove its DOM span, and create a new highlight note with the new color (replace, not stack)

2.4 WHEN a user selects formatted text THEN the selection menu SHALL include a "清除格式" (clear formatting) button that removes all format notes (`sourceType === 'format'`) matching the selected text and node, and unwraps their DOM spans

2.5 WHEN a format note with `style: 'solid'`, `style: 'bold'`, or `style: 'wavy'` is rendered THEN the system SHALL NOT apply the `.highlight-marker` base background/border CSS to those spans; only highlight-type formats (`color !== 'transparent'`) SHALL receive the highlight background styling

2.6 WHEN computing `notesCount` for the SmartBar badge THEN the system SHALL exclude notes where `sourceType === 'format'`, counting only user-authored, AI, and wrong-answer notes

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the SmartBar is hidden (focus mode) THEN the system SHALL CONTINUE TO position the AI floating button at its current location without adjustment

3.2 WHEN a user selects unhighlighted text and clicks a highlight color THEN the system SHALL CONTINUE TO create a new highlight note and wrap the text in a colored span

3.3 WHEN a user applies bold, underline, or wavy formatting to unhighlighted text THEN the system SHALL CONTINUE TO create a format note and apply the corresponding DOM decoration

3.4 WHEN a user toggles bold/underline/wavy on already-formatted text (non-highlight) THEN the system SHALL CONTINUE TO toggle the format off as currently implemented

3.5 WHEN highlight-type format notes (`color !== 'transparent'`) are rendered THEN the system SHALL CONTINUE TO display them with the colored background highlight effect

3.6 WHEN user-authored notes (`sourceType === 'user'`), AI notes (`sourceType === 'ai'`), or wrong-answer notes (`sourceType === 'wrong'`) exist THEN the system SHALL CONTINUE TO count them in the SmartBar badge

3.7 WHEN exporting notes to markdown THEN the system SHALL CONTINUE TO exclude format notes from the export count as already implemented in `course.ts`
