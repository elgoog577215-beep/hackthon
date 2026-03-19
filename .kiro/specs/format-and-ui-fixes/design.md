# Format and UI Fixes — Bugfix Design

## Overview

本设计文档涵盖 4 个前端 UI/格式化缺陷的修复方案。这些缺陷集中在 `CourseView.vue`、`ContentArea.vue` 和 `SmartBar.vue` 三个组件中，涉及定位、交互逻辑、CSS 样式污染和数据计数问题。修复策略遵循最小变更原则，每个 bug 独立修复。

## Glossary

- **Bug_Condition (C)**: 触发缺陷的输入条件集合
- **Property (P)**: 在 Bug_Condition 下的期望正确行为
- **Preservation**: 修复不应影响的现有行为
- **`SmartBar`**: 底部导航栏组件（`frontend/src/components/SmartBar.vue`），`position: fixed; bottom: 0; height: 56px`
- **`applyFormat`**: `ContentArea.vue` 中的格式化函数（第 1752 行），处理高亮/加粗/下划线/波浪线
- **`wrapRange`**: `ContentArea.vue` 中的 DOM 包裹函数（第 1851 行），为选区创建 `<span>` 并赋予样式类
- **`.highlight-marker`**: CSS 基础类，定义了黄色背景（`background-color: rgba(251, 191, 36, 0.3)`）、底部边框（`border-bottom: 2px solid #f59e0b`）和 `mix-blend-mode: multiply`
- **`formatHighlightMap`**: 高亮颜色到 Tailwind 类的映射对象（第 1489 行）
- **`noteStore`**: Pinia 笔记存储（`frontend/src/stores/notes.ts`），管理笔记 CRUD
- **Format Note**: `sourceType === 'format'` 的笔记，用于存储文字格式化操作（非用户手写笔记）

---

## Bug Details

### Bug 1: AI 助手浮动按钮被 SmartBar 遮挡

#### Bug Condition

`CourseView.vue` 第 82 行的浮动 AI 按钮使用 `bottom-6`（24px），而 SmartBar 固定在 `bottom: 0` 且高度为 56px。按钮被 SmartBar 遮挡了约 32px。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug1(state)
  INPUT: state of type UIState
  OUTPUT: boolean

  RETURN state.sideAIPanelVisible IS false
         AND state.courseStore.currentCourseId IS NOT EMPTY
         AND state.courseStore.isFocusMode IS false
         // SmartBar 可见时，bottom-6 (24px) < SmartBar height (56px)，按钮被遮挡
END FUNCTION
```

#### Examples

- 用户在课程页面，SmartBar 可见 → 期望：AI 按钮完全可见在 SmartBar 上方；实际：按钮下半部分被 SmartBar 遮挡
- 用户在专注模式（`isFocusMode = true`）→ SmartBar 隐藏，按钮在 `bottom-6` 位置正常显示（非 bug 条件）

---

### Bug 2: 高亮操作叠加 + 缺少清除格式按钮

#### Bug Condition

`applyFormat` 函数（第 1771 行）的 toggle 逻辑通过 `if (style !== 'highlight')` 排除了高亮类型。当 `style === 'highlight'` 时，函数直接跳过 toggle 检查，始终创建新的 format 笔记，导致同一文字上叠加多个高亮 span。

此外，选择菜单模板（第 280-310 行）中没有"清除格式"按钮。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug2(input)
  INPUT: input of type FormatAction { style: 'highlight', color: string, selectedText: string, nodeId: string }
  OUTPUT: boolean

  existingHighlight := noteStore.notes.find(n =>
    n.sourceType == 'format'
    AND n.nodeId == input.nodeId
    AND n.quote == input.selectedText
    AND n.style == 'highlight'
  )
  RETURN existingHighlight IS NOT NULL
         // 选区已有高亮笔记，再次点击高亮色应 toggle/替换，而非叠加
END FUNCTION
```

#### Examples

- 选取"量子力学"→ 点击黄色高亮 → 再次选取"量子力学"→ 点击黄色高亮 → 期望：移除高亮（toggle off）；实际：创建第二个黄色高亮笔记，DOM 中出现嵌套 span
- 选取"量子力学"→ 点击黄色高亮 → 再次选取"量子力学"→ 点击绿色高亮 → 期望：替换为绿色；实际：黄色和绿色叠加
- 选取已有多种格式的文字 → 期望：菜单中有"清除格式"按钮；实际：无此按钮

---

### Bug 3: 非高亮格式 span 被 `.highlight-marker` CSS 污染

#### Bug Condition

`wrapRange` 函数（第 1862 行）为所有 format 类型的 span 都添加了 `highlight-marker` 基础类：
```js
let className = 'highlight-marker transition-colors cursor-pointer '
```

而 `.highlight-marker` CSS 规则（第 3067 行）定义了：
- `background-color: rgba(251, 191, 36, 0.3)` — 黄色背景
- `border-bottom: 2px solid #f59e0b` — 黄色底部边框
- `mix-blend-mode: multiply`

这些样式被应用到 bold、solid（下划线）、wavy（波浪线）的 span 上，使它们看起来像高亮而非纯文本装饰。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug3(note)
  INPUT: note of type Note
  OUTPUT: boolean

  RETURN note.sourceType == 'format'
         AND note.style IN ['bold', 'solid', 'wavy']
         // 非高亮格式的 span 不应有 highlight-marker 的背景/边框样式
END FUNCTION
```

#### Examples

- 用户对"量子力学"应用加粗 → 期望：文字加粗，无背景色；实际：文字加粗 + 黄色背景 + 黄色底部边框
- 用户对"量子力学"应用下划线 → 期望：文字下方有深色实线；实际：文字有黄色背景 + 两条边框（CSS 的 `border-bottom` 和 Tailwind 的 `border-b-2 border-slate-800` 冲突）
- 用户对"量子力学"应用波浪线 → 期望：文字下方有波浪装饰线；实际：文字有黄色背景 + 波浪线

---

### Bug 4: Format 笔记被计入 SmartBar 笔记数

#### Bug Condition

`CourseView.vue` 第 552 行的 `notesCount` 计算属性：
```js
const notesCount = computed(() => noteStore.notes?.length || 0)
```
直接使用 `notes.length`，包含了所有 `sourceType === 'format'` 的格式化笔记。这些是内部格式化操作记录，不是用户手写笔记。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug4(notes)
  INPUT: notes of type Note[]
  OUTPUT: boolean

  formatNotes := notes.filter(n => n.sourceType == 'format')
  RETURN formatNotes.length > 0
         // 存在 format 笔记时，notesCount 会虚高
END FUNCTION
```

#### Examples

- 用户有 2 条手写笔记 + 5 条格式化操作 → 期望：SmartBar 显示 "2"；实际：显示 "7"
- 用户只有格式化操作，无手写笔记 → 期望：SmartBar 不显示 badge；实际：显示格式化操作数量

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 专注模式（`isFocusMode = true`）下 SmartBar 隐藏时，AI 浮动按钮保持当前 `bottom-6` 定位不变（Bug 1）
- 对未高亮文字点击高亮色仍正常创建新高亮笔记和 DOM span（Bug 2）
- 对已有 bold/underline/wavy 格式的文字再次点击相同格式仍正常 toggle off（Bug 2，已有逻辑）
- 高亮类型格式笔记（`color !== 'transparent'`）的 span 仍显示彩色背景高亮效果（Bug 3）
- `user`、`ai`、`wrong` 类型笔记仍正常计入 SmartBar badge（Bug 4）
- 导出笔记时仍排除 format 笔记（已在 `course.ts` 中实现）（Bug 4）

**Scope:**
所有不涉及上述 4 个 bug 条件的输入和交互应完全不受修复影响。

---

## Hypothesized Root Cause

### Bug 1: AI 浮动按钮定位

`CourseView.vue` 第 82 行使用 Tailwind `bottom-6`（= 1.5rem = 24px）。SmartBar 高度为 56px，固定在底部。按钮中心在 24px + 24px（按钮高度一半）= 48px 处，仍低于 SmartBar 顶部。需要将 `bottom-6` 改为足够大的值（如 `bottom-20` = 80px）使按钮完全在 SmartBar 上方。

### Bug 2: 高亮 toggle 逻辑缺失

`applyFormat` 第 1771 行的 toggle 条件为 `if (style !== 'highlight' && nodeId)`，明确排除了 `highlight` 类型。这是前一轮修复（ui-interaction-fixes）中为 bold/underline/wavy 添加 toggle 时的遗留问题——高亮被有意排除，但实际上高亮也需要 toggle（同色移除）和替换（异色替换）逻辑。

### Bug 3: CSS 类污染

`wrapRange` 第 1862 行无条件地将 `highlight-marker` 作为所有 span 的基础类。`.highlight-marker` CSS 规则包含黄色背景和边框，这些样式对 bold/solid/wavy 格式是不需要的。根因是 `highlight-marker` 被当作通用标记类使用，但其 CSS 定义是针对高亮场景的。

### Bug 4: notesCount 未过滤

`CourseView.vue` 第 552 行 `noteStore.notes?.length` 未过滤 `sourceType`。虽然导出功能（`course.ts`）已正确排除 format 笔记，但 SmartBar badge 的计数逻辑遗漏了这个过滤。

---

## Correctness Properties

Property 1: Bug Condition — AI 浮动按钮在 SmartBar 上方完全可见

_For any_ UI 状态，当 SmartBar 可见（`isFocusMode === false`）且 AI 浮动按钮显示时，修复后的按钮 SHALL 定位在 SmartBar 上方，按钮底边距离视口底部 ≥ SmartBar 高度（56px）+ 合理间距。

**Validates: Requirements 2.1**

Property 2: Preservation — 专注模式下按钮定位不变

_For any_ UI 状态，当 `isFocusMode === true`（SmartBar 隐藏）时，修复后的代码 SHALL 不影响 AI 浮动按钮的定位逻辑，按钮仍在视口右下角正常显示。

**Validates: Requirements 3.1**

Property 3: Bug Condition — 高亮同色 toggle off、异色替换

_For any_ 格式化操作，当选区已有高亮笔记且用户点击相同颜色时，修复后的 `applyFormat` SHALL 删除该高亮笔记并移除 DOM span（toggle off）。当用户点击不同颜色时，SHALL 删除旧高亮笔记并创建新颜色的高亮笔记（替换）。

**Validates: Requirements 2.2, 2.3**

Property 4: Preservation — 未高亮文字的高亮创建和非高亮格式 toggle 不变

_For any_ 对未高亮文字的高亮操作，修复后的代码 SHALL 继续正常创建新高亮笔记。对已有 bold/underline/wavy 格式的 toggle 行为 SHALL 与原代码一致。

**Validates: Requirements 3.2, 3.3, 3.4**

Property 5: Bug Condition — 非高亮格式 span 无背景/边框污染

_For any_ `sourceType === 'format'` 且 `style` 为 `bold`、`solid` 或 `wavy` 的笔记，修复后的 DOM span SHALL 不包含 `.highlight-marker` 的黄色背景和边框样式，仅显示对应的文本装饰效果。

**Validates: Requirements 2.5**

Property 6: Preservation — 高亮类型 span 仍显示彩色背景

_For any_ `sourceType === 'format'` 且 `color !== 'transparent'`（高亮类型）的笔记，修复后的 DOM span SHALL 继续显示对应颜色的背景高亮效果，与原代码行为一致。

**Validates: Requirements 3.5**

Property 7: Bug Condition — SmartBar badge 排除 format 笔记

_For any_ 笔记列表，修复后的 `notesCount` SHALL 仅计算 `sourceType !== 'format'` 的笔记数量，不包含格式化操作记录。

**Validates: Requirements 2.6**

Property 8: Preservation — user/ai/wrong 笔记仍正常计数

_For any_ 笔记列表中的 `user`、`ai`、`wrong` 类型笔记，修复后的 `notesCount` SHALL 继续正确计入这些笔记，与原代码行为一致。

**Validates: Requirements 3.6**

---

## Fix Implementation

### Changes Required

#### Bug 1: AI 浮动按钮定位

**File**: `frontend/src/views/CourseView.vue`

**Specific Changes**:
1. 将第 82 行的 `bottom-6` 改为 `bottom-20`（= 5rem = 80px），使按钮完全在 SmartBar（56px）上方，留有 24px 间距

#### Bug 2: 高亮 toggle/替换逻辑 + 清除格式按钮

**File**: `frontend/src/components/ContentArea.vue`

**Function**: `applyFormat`（第 1752 行）

**Specific Changes**:
1. **移除 `style !== 'highlight'` 排除条件**：将第 1771 行的 `if (style !== 'highlight' && nodeId)` 改为 `if (nodeId)`，使高亮也进入 toggle 检查
2. **调整匹配逻辑**：对于高亮类型，匹配条件为 `n.style === 'highlight'`（不区分颜色），找到已有高亮笔记后：
   - 如果颜色相同（`existingNote.color === color`）→ 删除笔记 + 移除 DOM span（toggle off）
   - 如果颜色不同 → 删除旧笔记 + 移除旧 DOM span + 继续执行创建新笔记的逻辑（替换）
3. **非高亮格式的 toggle 逻辑保持不变**：bold/solid/wavy 的匹配仍按 `n.style === noteStyle` 精确匹配

**Template Changes**（选择菜单，约第 309 行）:
4. **添加"清除格式"按钮**：在 Row 2 的 Styles 区域末尾添加一个按钮，调用新函数 `clearFormats()`
5. **实现 `clearFormats` 函数**：查找当前选区对应 nodeId 和 quote 的所有 `sourceType === 'format'` 笔记，逐一删除并移除 DOM span

#### Bug 3: CSS 类污染修复

**File**: `frontend/src/components/ContentArea.vue`

**Function**: `wrapRange`（第 1851 行）

**Specific Changes**:
1. **拆分基础类**：将第 1862 行的 `highlight-marker` 从通用基础类中移除。改为：
   - 非高亮格式（bold/solid/wavy）使用新的基础类 `format-marker`，仅包含 `transition-colors cursor-pointer`
   - 高亮格式和非 format 笔记继续使用 `highlight-marker`
2. **添加 `.format-marker` CSS 规则**：仅包含 `transition: all 0.2s ease; cursor: pointer;`，不包含背景色和边框

具体实现：将 `wrapRange` 中的类名构建逻辑改为：
```js
let className = 'transition-colors cursor-pointer '
if (note?.sourceType === 'format') {
    if (note.style === 'bold') {
        className += 'format-marker font-bold '
    } else if (note.style === 'solid') {
        className += 'format-marker border-b-2 border-slate-800 '
    } else if (note.style === 'wavy') {
        className += 'format-marker underline decoration-wavy decoration-slate-800 '
    } else if (note.color && note.color !== 'transparent') {
        className += 'highlight-marker ' + colorClass + ' '
    }
} else {
    className += 'highlight-marker '
    // ... existing ai/default logic
}
```

#### Bug 4: notesCount 过滤

**File**: `frontend/src/views/CourseView.vue`

**Specific Changes**:
1. 将第 552 行的 `notesCount` 计算属性从：
   ```js
   const notesCount = computed(() => noteStore.notes?.length || 0)
   ```
   改为：
   ```js
   const notesCount = computed(() => noteStore.notes?.filter(n => n.sourceType !== 'format').length || 0)
   ```

---

## Testing Strategy

### Validation Approach

测试策略分两阶段：先在未修复代码上验证 bug 存在（探索性测试），再在修复后验证正确性和行为保持。

### Exploratory Bug Condition Checking

**Goal**: 在实施修复前，确认 bug 的存在并验证根因分析。

**Test Cases**:
1. **Bug 1 — 按钮遮挡**: 检查 AI 浮动按钮的 `bottom` CSS 值是否小于 SmartBar 高度（将在未修复代码上确认 `bottom-6` = 24px < 56px）
2. **Bug 2 — 高亮叠加**: 对同一文字连续两次调用 `applyFormat('highlight', 'yellow')`，检查是否创建了两个高亮笔记（将在未修复代码上确认 bug）
3. **Bug 3 — CSS 污染**: 检查 `wrapRange` 为 bold 格式创建的 span 是否包含 `highlight-marker` 类（将在未修复代码上确认）
4. **Bug 4 — 计数虚高**: 创建 format 笔记后检查 `notesCount` 是否包含它们（将在未修复代码上确认）

**Expected Counterexamples**:
- Bug 2: `noteStore.notes` 中出现两个相同 quote 的 highlight 笔记
- Bug 3: bold span 的 `className` 包含 `highlight-marker`，导致黄色背景
- Bug 4: `notesCount` 返回值大于非 format 笔记数

### Fix Checking

**Goal**: 验证所有 bug 条件下，修复后的函数产生期望行为。

**Pseudocode:**
```
// Bug 1
FOR ALL state WHERE isBugCondition_Bug1(state) DO
  buttonBottom := getComputedStyle(aiButton).bottom
  ASSERT parseFloat(buttonBottom) >= 56 + margin
END FOR

// Bug 2
FOR ALL input WHERE isBugCondition_Bug2(input) DO
  notesBefore := noteStore.notes.filter(n => n.style === 'highlight' && n.quote === input.selectedText)
  applyFormat_fixed('highlight', input.color)
  IF input.color === notesBefore[0].color THEN
    ASSERT noteStore.notes.filter(...).length === notesBefore.length - 1  // toggle off
  ELSE
    ASSERT noteStore.notes.filter(...).length === notesBefore.length      // replaced, count unchanged
    ASSERT noteStore.notes.find(...).color === input.color                // new color
  END IF
END FOR

// Bug 3
FOR ALL note WHERE isBugCondition_Bug3(note) DO
  span := wrapRange_fixed(range, id, note.id)
  ASSERT NOT span.classList.contains('highlight-marker')
  ASSERT span.classList.contains('format-marker')
END FOR

// Bug 4
FOR ALL notes WHERE isBugCondition_Bug4(notes) DO
  result := notesCount_fixed(notes)
  ASSERT result === notes.filter(n => n.sourceType !== 'format').length
END FOR
```

### Preservation Checking

**Goal**: 验证所有非 bug 条件下，修复后的函数与原函数行为一致。

**Pseudocode:**
```
FOR ALL state WHERE NOT isBugCondition(state) DO
  ASSERT originalFunction(state) == fixedFunction(state)
END FOR
```

**Testing Approach**: 属性测试（Property-Based Testing）适用于 Bug 2 和 Bug 4 的保持性验证。Bug 1 和 Bug 3 更适合单元测试验证。

**Test Cases**:
1. **未高亮文字的高亮创建保持**: 对无已有高亮的文字调用 `applyFormat('highlight', color)`，验证仍正常创建笔记
2. **非高亮格式 toggle 保持**: 对已有 bold 的文字再次 `applyFormat('bold')`，验证仍正常 toggle off
3. **高亮 span 样式保持**: 验证 `color !== 'transparent'` 的高亮笔记 span 仍包含 `highlight-marker` 类和对应颜色类
4. **user/ai/wrong 笔记计数保持**: 验证这些类型笔记仍被 `notesCount` 正确计入

### Unit Tests

- Bug 1: 验证 AI 浮动按钮的 Tailwind 类包含 `bottom-20` 而非 `bottom-6`
- Bug 2: 测试 `applyFormat('highlight', 'yellow')` 的 toggle 逻辑（同色移除、异色替换）
- Bug 2: 测试 `clearFormats()` 函数移除所有格式笔记
- Bug 3: 测试 `wrapRange` 为 bold/solid/wavy 创建的 span 不包含 `highlight-marker`
- Bug 4: 测试 `notesCount` 计算属性排除 `sourceType === 'format'` 的笔记

### Property-Based Tests

- Bug 2: 生成随机的高亮颜色序列和选区文字，验证 toggle/替换行为的正确性（同色 toggle off，异色替换，无已有高亮则创建）
- Bug 4: 生成随机的笔记列表（混合 user/ai/format/wrong 类型），验证 `notesCount` 始终等于非 format 笔记数

### Integration Tests

- Bug 1: 完整流程：打开课程 → SmartBar 可见 → AI 按钮在 SmartBar 上方 → 进入专注模式 → SmartBar 隐藏 → 按钮位置正常
- Bug 2: 完整流程：选取文字 → 黄色高亮 → 再次选取 → 黄色高亮（toggle off）→ 验证 DOM 无高亮 span → 绿色高亮 → 再次选取 → 蓝色高亮（替换）→ 验证 DOM 只有蓝色 span
- Bug 3: 完整流程：选取文字 → 加粗 → 验证 DOM span 无黄色背景 → 下划线 → 验证 DOM span 无黄色背景
- Bug 4: 完整流程：创建手写笔记 → 应用格式化 → 验证 SmartBar badge 只显示手写笔记数
