# 笔记计数与回到顶部按钮修复 设计文档

## Overview

本文档涉及两个独立的 UI 缺陷修复：

1. **笔记计数过滤不完整**：`CourseView.vue` 中的 `notesCount` 计算属性仅排除了 `sourceType === 'format'` 的笔记，但未排除 `sourceType === 'wrong'`（错题记录），导致 SmartBar 徽章数字大于笔记面板内实际笔记数。
2. **回到顶部按钮定位冲突**：`ContentArea.vue` 中的回到顶部按钮（`bottom: 5.5rem; right: 1rem`）与 `FloatingAIAssistant.vue` 中的 AI 助手按钮（`bottom-20 right-4`，即 `bottom: 5rem; right: 1rem`）在垂直和水平方向上重叠，且两者在笔记列展开/收起时的偏移逻辑不协调。

修复策略：Bug 1 是单行过滤条件修改；Bug 2 需要将回到顶部按钮的定位逻辑改为始终位于 AI 助手按钮正上方，并通过 props 或 store 状态同步笔记列的展开/收起状态。

## Glossary

- **Bug_Condition (C)**：触发缺陷的条件——C1: 笔记列表中存在 `sourceType === 'wrong'` 的记录时计数错误；C2: 回到顶部按钮可见时与 AI 助手按钮位置重叠
- **Property (P)**：期望行为——P1: `notesCount` 仅计算 `user`/`ai`/未定义类型的笔记；P2: 回到顶部按钮始终在 AI 助手按钮正上方且不重叠
- **Preservation**：不受修复影响的现有行为——纯用户笔记计数、错题徽章计数、滚动阈值判断、滚动到顶部功能、AI 助手按钮点击
- **notesCount**：`CourseView.vue` 第 552 行的 computed 属性，计算 SmartBar 笔记徽章显示的数字
- **isNotesCollapsed**：`ContentArea.vue` 中的 ref，控制右侧笔记列的展开/收起状态
- **FloatingAIAssistant**：`FloatingAIAssistant.vue` 中的全局浮动 AI 助手按钮组件，通过 `App.vue` 挂载

## Bug Details

### Bug Condition

**Bug 1 — 笔记计数**：当笔记列表中存在 `sourceType === 'wrong'` 的记录时，`notesCount` 计算属性的过滤条件 `n.sourceType !== 'format'` 未能排除错题，导致计数偏大。

**Bug 2 — 按钮重叠**：当页面滚动超过 500px 且回到顶部按钮可见时，该按钮的 CSS 定位（`bottom: 5.5rem; right: 1rem`）与 AI 助手按钮（`bottom: 5rem; right: 1rem`）几乎完全重叠（仅差 0.5rem ≈ 8px，不足以分开两个按钮）。此外，笔记列展开时两者的水平偏移量不同（back-to-top 用媒体查询 `right: 300px/320px`，AI 按钮无对应偏移），导致不同步。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug1(notes)
  INPUT: notes of type Note[]
  OUTPUT: boolean
  
  wrongNotes := notes.filter(n => n.sourceType === 'wrong')
  RETURN wrongNotes.length > 0
END FUNCTION

FUNCTION isBugCondition_Bug2(state)
  INPUT: state of type { scrollTop: number, isAIOpen: boolean }
  OUTPUT: boolean
  
  RETURN state.scrollTop > 500
         AND NOT state.isAIOpen
         // Both buttons visible and positioned with overlapping coordinates
END FUNCTION
```

### Examples

- **Bug 1 示例 1**：用户有 3 条 `user` 笔记 + 2 条 `wrong` 错题 → SmartBar 显示 5，笔记面板显示 3，数字不一致
- **Bug 1 示例 2**：用户有 1 条 `ai` 笔记 + 1 条 `format` 格式标记 + 4 条 `wrong` 错题 → SmartBar 显示 5（排除了 format），笔记面板显示 1
- **Bug 1 示例 3**：用户只有 `wrong` 错题没有普通笔记 → SmartBar 显示错题数量，但笔记面板显示 0 条
- **Bug 2 示例 1**：笔记列收起，页面滚动 > 500px → 回到顶部按钮和 AI 按钮都在右下角 `right: 1rem`，垂直间距仅 8px，视觉上重叠
- **Bug 2 示例 2**：笔记列展开 → 回到顶部按钮偏移到 `right: 300px`，AI 按钮仍在 `right: 1rem`，两者水平位置不同步

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 当用户只有 `user`/`ai` 类型笔记（无 `wrong`）时，SmartBar 笔记徽章数量应与当前行为一致
- `wrongAnswersCount` 计算属性（错题徽章）不受笔记计数修复影响
- 页面滚动未超过 500px 时，回到顶部按钮保持隐藏
- 点击回到顶部按钮后，页面平滑滚动到顶部的功能不变
- AI 助手按钮的点击行为（打开全屏 AI 面板）不受定位调整影响

**Scope:**
所有不涉及 `sourceType === 'wrong'` 笔记的计数场景，以及不涉及回到顶部按钮可见状态的 UI 交互，均不受本次修复影响。

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **笔记计数过滤条件不完整**：`CourseView.vue` 第 552 行的 `notesCount` 计算属性：
   ```typescript
   const notesCount = computed(() => noteStore.notes?.filter(n => n.sourceType !== 'format').length || 0)
   ```
   此前从 `noteStore.notes?.length` 修改为排除 `format`，但遗漏了 `wrong` 类型。笔记面板内部（`NotesPanel.vue`）将笔记分为 `user`/`ai`/`wrong`/`format` 四组，只展示 `user` 和 `ai` 作为"笔记"，`wrong` 作为"错题"单独展示。因此外层计数也应只计算 `user` 和 `ai`。

2. **回到顶部按钮定位硬编码且与 AI 按钮不协调**：
   - 回到顶部按钮在 `ContentArea.vue` 中使用固定 CSS（`bottom: 5.5rem; right: 1rem`）
   - AI 助手按钮在 `FloatingAIAssistant.vue` 中使用 Tailwind 类（`bottom-20 right-4`，即 `bottom: 5rem; right: 1rem`）
   - 两者的 `bottom` 值仅差 0.5rem（8px），按钮高度约 48px，严重重叠
   - 笔记列展开时，回到顶部按钮通过媒体查询偏移 `right`，但 AI 按钮没有对应的偏移逻辑
   - 两个按钮分属不同组件（ContentArea vs FloatingAIAssistant），没有共享定位状态

3. **缺少组件间定位协调机制**：回到顶部按钮通过 `<Teleport to="body">` 渲染到 body，AI 按钮也是 fixed 定位。两者独立定位，没有共享的布局上下文或 CSS 变量来协调位置。

## Correctness Properties

Property 1: Bug Condition — 笔记计数排除错题

_For any_ note array containing notes with mixed sourceTypes (including 'wrong'), the fixed `notesCount` computed property SHALL return the count of notes where `sourceType` is 'user', 'ai', or undefined, excluding both 'format' and 'wrong' types.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — 无错题时笔记计数不变

_For any_ note array containing only notes with sourceType 'user', 'ai', or undefined (no 'wrong' or 'format' notes), the fixed `notesCount` SHALL produce the same result as the original function, preserving the existing count behavior.

**Validates: Requirements 3.1, 3.2**

Property 3: Bug Condition — 回到顶部按钮不与 AI 按钮重叠

_For any_ UI state where both the back-to-top button and AI assistant button are visible, the back-to-top button SHALL be positioned directly above the AI assistant button with sufficient vertical gap, and both buttons SHALL share the same horizontal (`right`) offset.

**Validates: Requirements 2.3, 2.4**

Property 4: Preservation — 回到顶部按钮显示/隐藏阈值不变

_For any_ scroll position, the back-to-top button visibility SHALL continue to be determined by `scrollTop > 500`, preserving the existing scroll threshold behavior.

**Validates: Requirements 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `frontend/src/views/CourseView.vue`

**Function**: `notesCount` computed property (line 552)

**Specific Changes**:
1. **扩展过滤条件**：将 `n.sourceType !== 'format'` 改为同时排除 `'format'` 和 `'wrong'`：
   ```typescript
   const notesCount = computed(() => 
     noteStore.notes?.filter(n => n.sourceType !== 'format' && n.sourceType !== 'wrong').length || 0
   )
   ```

---

**File**: `frontend/src/components/ContentArea.vue`

**Changes**: 回到顶部按钮定位重构

**Specific Changes**:
1. **调整 bottom 值**：将回到顶部按钮的 CSS `bottom` 从 `5.5rem` 改为 `8.5rem`（AI 按钮 `bottom: 5rem` + 按钮高度 `3rem` + 间距 `0.5rem`），确保不重叠
2. **统一水平偏移逻辑**：AI 按钮通过 `notesCollapsed` 状态动态切换 `right-6`（笔记列收起）/ `right-[340px]`（笔记列展开）。回到顶部按钮当前使用媒体查询（`@media min-width`）来偏移 `right`，这与 AI 按钮的逻辑不同步。修复方案：
   - 移除 CSS 中的 `@media` 媒体查询偏移规则（这些基于屏幕宽度，不是基于笔记列状态）
   - 改为在 `backToTopStyle` computed 属性中根据 `notesCollapsed` prop 动态计算 `right` 值，与 AI 按钮保持一致：
     - 笔记列收起时：`right: 1.5rem`（= AI 按钮的 `right-6`）
     - 笔记列展开时：`right: 340px`（= AI 按钮的 `right-[340px]`）
     - AI 面板打开时：`right: calc(33vw + 1rem)`（保留现有逻辑）
3. **确保 z-index 协调**：回到顶部按钮当前 `z-index: 50`，AI 按钮 `z-50`。保持一致即可。

**Note**: 关键改动是将回到顶部按钮的水平偏移从"基于屏幕宽度的媒体查询"改为"基于 `notesCollapsed` 状态的动态计算"，与 AI 按钮使用完全相同的逻辑，确保两个按钮始终在同一垂直线上同步移动。

## Testing Strategy

### Validation Approach

测试策略分两阶段：先在未修复代码上验证缺陷存在（探索性测试），再验证修复后行为正确且不引入回归。

### Exploratory Bug Condition Checking

**Goal**: 在实施修复前，通过测试确认缺陷存在，验证根因分析。

**Test Plan**: 创建包含混合 `sourceType` 的笔记数组，模拟 `notesCount` 计算逻辑，验证在未修复代码上计数包含了 `wrong` 类型。

**Test Cases**:
1. **混合类型计数测试**：创建 2 条 `user` + 3 条 `wrong` 笔记，验证未修复的 `notesCount` 返回 5 而非 2（will fail on unfixed code — 即未修复代码会让此断言通过，因为它确实返回 5）
2. **纯错题计数测试**：创建 0 条普通笔记 + 3 条 `wrong` 笔记，验证未修复的 `notesCount` 返回 3 而非 0
3. **全类型混合测试**：创建 `user` + `ai` + `format` + `wrong` 各若干条，验证未修复代码的计数包含 `wrong`

**Expected Counterexamples**:
- `notesCount` 在包含 `wrong` 笔记时返回值大于预期
- 根因：过滤条件 `n.sourceType !== 'format'` 未排除 `wrong`

### Fix Checking

**Goal**: 验证修复后，所有包含 `wrong` 笔记的场景中 `notesCount` 正确排除错题。

**Pseudocode:**
```
FOR ALL notes WHERE isBugCondition_Bug1(notes) DO
  result := notesCount_fixed(notes)
  expected := notes.filter(n => n.sourceType !== 'format' AND n.sourceType !== 'wrong').length
  ASSERT result === expected
END FOR
```

### Preservation Checking

**Goal**: 验证修复后，不包含 `wrong` 笔记的场景中 `notesCount` 行为不变。

**Pseudocode:**
```
FOR ALL notes WHERE NOT isBugCondition_Bug1(notes) DO
  ASSERT notesCount_original(notes) === notesCount_fixed(notes)
END FOR
```

**Testing Approach**: 属性测试（PBT）适合验证保持性，因为它能自动生成大量不同的笔记数组组合，覆盖边界情况。

**Test Plan**: 先在未修复代码上观察纯 `user`/`ai` 笔记的计数行为，然后编写属性测试确保修复后行为一致。

**Test Cases**:
1. **纯用户笔记保持**：生成仅包含 `user`/`ai` 类型的随机笔记数组，验证修复前后 `notesCount` 一致
2. **错题徽章保持**：验证 `wrongAnswersCount` 不受 `notesCount` 修复影响
3. **空笔记列表保持**：验证空数组时 `notesCount` 返回 0

### Unit Tests

- 测试 `notesCount` 在各种 `sourceType` 组合下的计算结果
- 测试回到顶部按钮的 CSS `bottom` 值大于 AI 按钮的 `bottom` + 按钮高度
- 测试回到顶部按钮和 AI 按钮的 `right` 值一致

### Property-Based Tests

- 生成随机 `sourceType` 组合的笔记数组，验证 `notesCount` 始终等于 `user`/`ai`/undefined 类型的数量
- 生成仅包含 `user`/`ai` 类型的笔记数组，验证修复前后计数一致（保持性）
- 生成随机笔记数组，验证 `notesCount` + `wrongCount` + `formatCount` = `totalCount`

### Integration Tests

- 在完整 SmartBar 组件中验证笔记徽章显示正确数字
- 验证回到顶部按钮在页面滚动后出现在 AI 按钮上方
- 验证笔记列展开/收起时两个按钮位置协调
