# UI Interaction Fixes — Bugfix Design

## Overview

本设计文档涵盖 5 个 UI 交互缺陷的修复方案。这些缺陷分布在前端组件（`SideAIPanel.vue`、`CourseView.vue`、`ContentArea.vue`）和后端服务（`ai_graph_service.py`）中。修复策略遵循最小变更原则，每个 bug 独立修复，互不干扰。

## Glossary

- **Bug_Condition (C)**: 触发缺陷的输入条件集合
- **Property (P)**: 在 Bug_Condition 下的期望正确行为
- **Preservation**: 修复不应影响的现有行为
- **`SideAIPanel`**: AI 助手侧边面板组件（`frontend/src/components/SideAIPanel.vue`），通过 `quote-ask` 事件打开
- **`CourseView`**: 课程主视图（`frontend/src/views/CourseView.vue`），管理左侧目录、内容区域和 AI 面板的布局
- **`ContentArea`**: 内容区域组件（`frontend/src/components/ContentArea.vue`），包含回到顶部按钮、文字选择菜单和格式化功能
- **`applyFormat`**: `ContentArea.vue` 中的函数，处理文字格式化（加粗/下划线/波浪线/高亮）
- **`noteStore`**: Pinia 笔记存储（`frontend/src/stores/notes.ts`），管理笔记的 CRUD
- **`_validate_and_fix_knowledge_graph`**: `backend/ai_graph_service.py` 中的方法，验证并修复知识图谱节点的 `chapter_id` 映射

---

## Bug Details

### Bug 1: AI 助手浮动图标缺失

#### Bug Condition

当用户没有选取文字时，系统不显示任何 AI 助手入口。当前 `SideAIPanel` 只能通过 `ContentArea` 的 `quote-ask` 事件打开（用户选取文字后点击"提问"按钮），没有独立的浮动入口。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug1(state)
  INPUT: state of type AppState
  OUTPUT: boolean

  RETURN state.textSelection IS EMPTY
         AND state.sideAIPanelVisible IS false
         AND state.currentCourseId IS NOT EMPTY
         // 用户在课程页面，没有选取文字，没有 AI 面板入口
END FUNCTION
```

#### Examples

- 用户打开课程页面，没有选取任何文字 → 期望：右下角显示 AI 助手浮动图标；实际：无任何入口
- 用户关闭 AI 面板后 → 期望：浮动图标重新出现；实际：无法再次打开面板（除非重新选取文字）

---

### Bug 2: 左侧目录宽度过大且分隔条不可拖拽

#### Bug Condition

页面加载时左侧目录默认宽度为 300px（`CourseView.vue` 第 213 行 `leftWidth: 300`），占比偏大。分隔条的可交互区域仅为 `w-1`（4px），实际拖拽体验差。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug2(state)
  INPUT: state of type LayoutState
  OUTPUT: boolean

  RETURN (state.leftSidebarWidth == 300 AND state.screenWidth >= 1280)
         OR (state.resizerInteractiveWidth <= 4)
         // 默认宽度过大，或分隔条交互区域过窄
END FUNCTION
```

#### Examples

- 页面首次加载（无 localStorage 缓存）→ 期望：左侧目录 250px；实际：300px
- 用户尝试拖动分隔条 → 期望：容易抓取并拖动；实际：4px 宽度难以精确点击

---

### Bug 3: 回到顶部按钮与 AI 面板重叠

#### Bug Condition

`ContentArea.vue` 中的回到顶部按钮使用 `position: fixed` 定位，CSS 媒体查询仅考虑了笔记面板的偏移（`right: 300px`/`320px`），未考虑 `SideAIPanel` 打开时的额外偏移。按钮通过 `Teleport to="body"` 渲染，脱离了正常布局流。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug3(state)
  INPUT: state of type UIState
  OUTPUT: boolean

  RETURN state.sideAIPanelVisible IS true
         AND state.showBackToTop IS true
         // AI 面板打开且回到顶部按钮可见时，按钮与面板重叠
END FUNCTION
```

#### Examples

- 用户滚动超过 500px 后打开 AI 面板 → 期望：按钮在内容区域右下角；实际：按钮被 AI 面板遮挡
- 笔记面板折叠 + AI 面板打开 → 期望：按钮位置正确调整；实际：按钮仍在 `right: 300px` 位置

---

### Bug 4: 文字格式化无法 Toggle

#### Bug Condition

`ContentArea.vue` 中的 `applyFormat` 函数（第 1750 行）始终调用 `noteStore.createNote()` 创建新的 `sourceType: 'format'` 笔记，不检查选区内是否已存在相同格式的笔记。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug4(input)
  INPUT: input of type FormatAction { style: string, value?: string, selectedText: string, nodeId: string }
  OUTPUT: boolean

  existingNote := noteStore.notes.find(n =>
    n.sourceType == 'format'
    AND n.nodeId == input.nodeId
    AND n.quote == input.selectedText
    AND matchesStyle(n, input.style, input.value)
  )
  RETURN existingNote IS NOT NULL
         // 选区内已存在相同格式的笔记，再次点击应 toggle 移除
END FUNCTION
```

#### Examples

- 用户选取"量子力学"并点击加粗 → 创建 format 笔记（正确）→ 再次选取"量子力学"并点击加粗 → 期望：移除加粗；实际：创建第二个重复的 format 笔记
- 用户选取已有波浪线的文字并点击波浪线 → 期望：移除波浪线；实际：创建新的波浪线笔记

---

### Bug 5: 知识图谱跳转不准确

#### Bug Condition

`ai_graph_service.py` 的 `_validate_and_fix_knowledge_graph` 方法中，`chapter_id` 匹配逻辑使用简单的子串包含（Priority 2，第 113-117 行）和 fallback 到第一个节点（第 120 行）。子串匹配是双向的（`node_label in node_name OR node_name in node_label`），容易产生误匹配。

**Formal Specification:**
```
FUNCTION isBugCondition_Bug5(node, courseNodes)
  INPUT: node of type GraphNode, courseNodes of type List[CourseNode]
  OUTPUT: boolean

  chapter_id := node.chapter_id
  RETURN (chapter_id IS NULL OR chapter_id NOT IN validChapterIds)
         AND exactLabelMatch(node.label, courseNodes) IS NULL
         // chapter_id 无效且无精确标签匹配，将进入不精确的子串匹配或 fallback
END FUNCTION
```

#### Examples

- 知识图谱节点 label="量子" → 子串匹配到"量子力学基础"（正确）但也可能匹配到"量子计算应用"（错误，取决于遍历顺序）
- 知识图谱节点 label="基础概念" → 子串匹配到第一个包含"基础"的节点，可能不是最相关的
- 所有匹配都失败 → fallback 到 `course_nodes[0]`，跳转到完全不相关的章节

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 用户选取文字后点击"提问"按钮打开 `SideAIPanel` 并显示引用卡片和建议按钮的流程不变（Bug 1）
- 用户双击分隔条重置左侧目录宽度的行为不变（Bug 2）
- 移动端（< 768px）左侧目录以覆盖层模式显示的行为不变（Bug 2）
- 滚动距离超过 500px 时回到顶部按钮正常显示的逻辑不变（Bug 3）
- 点击回到顶部按钮平滑滚动到顶部的行为不变（Bug 3）
- 用户对文字应用高亮颜色的行为不变，高亮不受 toggle 逻辑影响（Bug 4）
- 用户通过笔记面板删除按钮删除格式笔记的行为不变（Bug 4）
- 知识图谱节点的 `chapter_id` 已正确匹配时直接使用该 ID 跳转的行为不变（Bug 5）
- 用户点击知识图谱中笔记条目跳转到笔记所属课程节点的行为不变（Bug 5）

**Scope:**
所有不涉及上述 5 个 bug 条件的输入和交互应完全不受修复影响。

---

## Hypothesized Root Cause

### Bug 1: AI 助手浮动图标缺失

`CourseView.vue` 中 `SideAIPanel` 仅在 `sideAIPanelVisible` 为 true 时渲染，而 `sideAIPanelVisible` 只通过 `openSideAIPanel` 设置为 true，该函数仅由 `ContentArea` 的 `quote-ask` 事件触发。缺少一个独立的浮动按钮来直接设置 `sideAIPanelVisible = true`。

### Bug 2: 左侧目录宽度过大且分隔条不可拖拽

1. `CourseView.vue` 第 213 行 `leftWidth: 300` 和第 363 行 `resetLeftSidebar` 中 `screenWidth >= SCREEN_XL ? 300 : 280` 设置了过大的默认值。
2. 分隔条使用 `w-1`（4px）作为基础宽度，虽然有 `hover:w-2` 扩展，但初始交互区域太窄，用户难以精确点击。

### Bug 3: 回到顶部按钮与 AI 面板重叠

`ContentArea.vue` 的 `.back-to-top` CSS 使用 `position: fixed` 和媒体查询设置 `right` 值（768px+ 时 `right: 300px`，1280px+ 时 `right: 320px`），这些值对应笔记面板宽度。但当 `SideAIPanel` 打开时（宽度为 `w-1/3 min-w-[320px] max-w-[480px]`），按钮位置没有相应调整。由于按钮通过 `Teleport to="body"` 渲染，无法通过父元素布局自动调整。

### Bug 4: 文字格式化无法 Toggle

`applyFormat` 函数（第 1750 行）直接调用 `noteStore.createNote()` 创建新笔记，没有先检查是否已存在相同格式的笔记。缺少 toggle 逻辑：查找匹配的现有 format 笔记 → 如果存在则删除（取消格式）→ 如果不存在则创建（应用格式）。

### Bug 5: 知识图谱跳转不准确

`_validate_and_fix_knowledge_graph` 的 Priority 2 匹配使用双向子串包含（`node_label in node_name OR node_name in node_label`），这会导致：
1. 短标签（如"基础"）匹配到多个节点，取决于遍历顺序
2. 长标签包含短节点名时产生误匹配
3. Fallback 到 `course_nodes[0]` 是最差情况，完全不考虑相关性

---

## Correctness Properties

Property 1: Bug Condition — AI 助手浮动图标在无选取文字时可见

_For any_ 应用状态，当用户在课程页面且未选取文字且 `SideAIPanel` 未打开时，修复后的 `CourseView` SHALL 在内容区域右下角显示一个浮动 AI 助手图标按钮，点击后打开 `SideAIPanel`。

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — 选取文字后的 AI 提问流程不变

_For any_ 用户选取文字后点击"提问"按钮的操作，修复后的代码 SHALL 产生与原代码完全相同的行为：打开 `SideAIPanel` 并显示引用卡片和建议按钮。

**Validates: Requirements 3.1, 3.2**

Property 3: Bug Condition — 左侧目录默认宽度缩小且分隔条可拖拽

_For any_ 页面加载（无缓存状态），修复后的 `CourseView` SHALL 将左侧目录默认宽度设为 250px，且分隔条的可交互区域 SHALL 足够宽（≥ 8px）以便正常拖拽。

**Validates: Requirements 2.3, 2.4**

Property 4: Preservation — 分隔条双击重置和移动端行为不变

_For any_ 双击分隔条或移动端访问的操作，修复后的代码 SHALL 产生与原代码相同的行为。

**Validates: Requirements 3.3, 3.4**

Property 5: Bug Condition — 回到顶部按钮不与 AI 面板重叠

_For any_ UI 状态，当 `SideAIPanel` 打开且 `showBackToTop` 为 true 时，修复后的回到顶部按钮 SHALL 定位在内容区域的右下角，不与 AI 面板区域重叠。

**Validates: Requirements 2.5, 2.6**

Property 6: Preservation — 回到顶部按钮的显示和滚动行为不变

_For any_ 滚动操作，修复后的回到顶部按钮 SHALL 在滚动距离超过 500px 时显示，点击后平滑滚动到顶部，与原代码行为一致。

**Validates: Requirements 3.5, 3.6**

Property 7: Bug Condition — 文字格式化支持 Toggle

_For any_ 格式化操作，当选区内已存在相同格式（加粗/下划线/波浪线）的 format 笔记时，修复后的 `applyFormat` SHALL 移除该笔记（取消格式），而非创建新的重复笔记。

**Validates: Requirements 2.7, 2.8**

Property 8: Preservation — 高亮和笔记删除行为不变

_For any_ 高亮颜色应用操作或通过笔记面板删除格式笔记的操作，修复后的代码 SHALL 产生与原代码完全相同的行为。

**Validates: Requirements 3.7, 3.8**

Property 9: Bug Condition — 知识图谱跳转准确性提升

_For any_ 知识图谱节点的 `chapter_id` 匹配失败时，修复后的 `_validate_and_fix_knowledge_graph` SHALL 使用更精确的匹配策略（基于相似度评分的排序），选择最相关的课程节点，而非简单的子串包含或 fallback 到第一个节点。

**Validates: Requirements 2.9, 2.10**

Property 10: Preservation — 已正确匹配的 chapter_id 不受影响

_For any_ 知识图谱节点的 `chapter_id` 已在 `valid_chapter_ids` 中的情况，修复后的代码 SHALL 跳过匹配逻辑，直接使用原 `chapter_id`，与原代码行为一致。

**Validates: Requirements 3.9, 3.10**

---

## Fix Implementation

### Changes Required

#### Bug 1: AI 助手浮动图标

**File**: `frontend/src/views/CourseView.vue`

**Specific Changes**:
1. 在 `ContentArea` 之后、`SideAIPanel` 之前添加一个浮动 AI 助手按钮，使用 `position: fixed` 定位在内容区域右下角
2. 按钮仅在 `!sideAIPanelVisible && courseStore.currentCourseId` 时显示
3. 点击按钮调用新的 `openSideAIPanelDirect()` 方法，设置 `sideAIPanelVisible = true` 但不传递引用文字
4. 添加 `openSideAIPanelDirect` 函数：与 `openSideAIPanel` 类似但不设置 `quoteText`

#### Bug 2: 左侧目录宽度和分隔条

**File**: `frontend/src/views/CourseView.vue`

**Specific Changes**:
1. 将 `loadSidebarState` 的默认 `leftWidth` 从 `300` 改为 `250`
2. 将 `resetLeftSidebar` 中的值从 `280/300` 改为 `240/250`
3. 将分隔条的基础宽度从 `w-1`（4px）改为 `w-2`（8px），并增加 `hover:w-3` 扩展效果，确保足够的可交互区域

#### Bug 3: 回到顶部按钮定位

**File**: `frontend/src/components/ContentArea.vue`

**Specific Changes**:
1. 将回到顶部按钮从 `Teleport to="body"` 改为在 `#content-scroll-container` 内部使用 `sticky` 或 `absolute` 定位，或者保留 Teleport 但通过 props 传入 `sideAIPanelVisible` 状态来动态调整 `right` 值
2. 推荐方案：通过 props 接收 `sideAIPanelVisible`，在按钮上使用动态 class 或 inline style 调整 `right` 值。当 AI 面板打开时，增加 `right` 偏移量（面板宽度约 `33vw`，最小 320px）
3. 在 `CourseView.vue` 中将 `sideAIPanelVisible` 作为 prop 传递给 `ContentArea`

#### Bug 4: 文字格式化 Toggle

**File**: `frontend/src/components/ContentArea.vue`

**Function**: `applyFormat`

**Specific Changes**:
1. 在 `applyFormat` 函数开头，创建新笔记之前，先查找是否存在匹配的 format 笔记：
   - 匹配条件：`sourceType === 'format'` AND `nodeId` 相同 AND `quote` 相同 AND 样式匹配（`style` 字段对应 bold/solid/wavy）
2. 如果找到匹配笔记：调用 `noteStore.deleteNote(existingNote.id)` 删除笔记，移除 DOM 中对应的高亮 span（通过 `highlightId` 查找并 unwrap），然后 return
3. 如果未找到：执行原有的创建逻辑
4. 注意：高亮颜色（`style === 'highlight'`）不参与 toggle 逻辑，保持原有行为

#### Bug 5: 知识图谱 chapter_id 匹配

**File**: `backend/ai_graph_service.py`

**Function**: `_validate_and_fix_knowledge_graph`

**Specific Changes**:
1. 替换 Priority 2 的简单子串匹配为基于评分的模糊匹配：
   - 计算 `node_label` 与每个 `course_node.node_name` 的相似度分数
   - 使用简单的字符重叠比率或最长公共子串长度作为评分
   - 选择得分最高且超过阈值的候选节点
2. 改进 Fallback 策略：
   - 如果模糊匹配无结果，尝试按节点层级（`node_level`）匹配：优先匹配叶子节点（更具体的内容）
   - 最终 fallback 仍使用第一个节点，但记录 warning 日志
3. 不修改 Priority 0（chapter_id 是 node_name）和 Priority 1（精确标签匹配）的逻辑

---

## Testing Strategy

### Validation Approach

测试策略分两阶段：先在未修复代码上验证 bug 存在（探索性测试），再在修复后验证正确性和行为保持。

### Exploratory Bug Condition Checking

**Goal**: 在实施修复前，确认 bug 的存在并验证根因分析。

**Test Cases**:
1. **Bug 1 — 浮动图标缺失**: 在 CourseView 中检查当 `sideAIPanelVisible === false` 时是否存在浮动 AI 按钮（将在未修复代码上失败）
2. **Bug 2 — 默认宽度**: 验证 `loadSidebarState()` 返回的默认 `leftWidth` 是否为 300（将在未修复代码上确认 bug）
3. **Bug 3 — 按钮重叠**: 模拟 AI 面板打开状态，检查回到顶部按钮的 `right` CSS 值是否考虑了面板宽度（将在未修复代码上失败）
4. **Bug 4 — 格式化不可 Toggle**: 调用 `applyFormat('bold')` 两次，检查是否创建了两个 format 笔记（将在未修复代码上确认 bug）
5. **Bug 5 — 子串匹配不精确**: 构造一个 `node_label="基础"` 和多个包含"基础"的课程节点，验证匹配结果是否为最相关的节点（将在未修复代码上失败）

**Expected Counterexamples**:
- Bug 1: 无浮动按钮元素存在
- Bug 4: `noteStore.notes` 中出现两个相同 quote 和 style 的 format 笔记
- Bug 5: 短标签匹配到第一个包含该子串的节点而非最相关的节点

### Fix Checking

**Goal**: 验证所有 bug 条件下，修复后的函数产生期望行为。

**Pseudocode:**
```
FOR ALL state WHERE isBugCondition_Bug1(state) DO
  result := renderCourseView_fixed(state)
  ASSERT floatingAIButtonExists(result)
END FOR

FOR ALL state WHERE isBugCondition_Bug2(state) DO
  result := loadSidebarState_fixed()
  ASSERT result.leftWidth == 250
  ASSERT resizerWidth >= 8
END FOR

FOR ALL state WHERE isBugCondition_Bug3(state) DO
  result := getBackToTopPosition_fixed(state)
  ASSERT result.right > sideAIPanelWidth + contentMargin
END FOR

FOR ALL input WHERE isBugCondition_Bug4(input) DO
  notesBefore := noteStore.notes.length
  applyFormat_fixed(input.style, input.value)
  ASSERT noteStore.notes.length == notesBefore - 1  // 笔记被删除
END FOR

FOR ALL (node, courseNodes) WHERE isBugCondition_Bug5(node, courseNodes) DO
  result := validateAndFix_fixed(node, courseNodes)
  ASSERT result.chapter_id == mostRelevantNode(node.label, courseNodes)
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

**Testing Approach**: 属性测试（Property-Based Testing）适用于 Bug 4 和 Bug 5 的保持性验证，因为它们有明确的输入域和可验证的输出。Bug 1-3 更适合组件级集成测试。

**Test Cases**:
1. **选取文字提问保持**: 验证 `openSideAIPanel` 在传入 quote 时仍正确设置 `sideAIQuoteText` 和 `sideAIPanelVisible`
2. **分隔条双击重置保持**: 验证 `resetLeftSidebar` 在修复后重置到新的默认值（250px）
3. **回到顶部显示逻辑保持**: 验证 `showBackToTop` 仍在 `scrollTop > 500` 时为 true
4. **高亮颜色不受 Toggle 影响**: 验证 `applyFormat('highlight', 'yellow')` 始终创建新笔记，不触发 toggle
5. **已正确匹配的 chapter_id 保持**: 验证当 `chapter_id` 在 `valid_chapter_ids` 中时，不执行任何匹配逻辑

### Unit Tests

- Bug 1: 测试浮动按钮的条件渲染（`v-if` 逻辑）
- Bug 2: 测试默认宽度值和分隔条宽度
- Bug 3: 测试回到顶部按钮在不同面板状态下的 `right` 值计算
- Bug 4: 测试 `applyFormat` 的 toggle 逻辑（创建/删除分支）
- Bug 5: 测试 `_validate_and_fix_knowledge_graph` 的匹配评分算法

### Property-Based Tests

- Bug 4: 生成随机的 format 笔记状态和格式化操作，验证 toggle 行为的幂等性（应用 → 取消 → 应用 = 一个笔记）
- Bug 5: 生成随机的节点标签和课程节点列表，验证匹配结果的相关性评分始终高于阈值（或正确 fallback）

### Integration Tests

- Bug 1: 完整流程测试：打开课程 → 点击浮动图标 → AI 面板打开 → 关闭面板 → 图标重新出现
- Bug 3: 完整流程测试：滚动 → 按钮出现 → 打开 AI 面板 → 按钮位置调整 → 关闭面板 → 按钮位置恢复
- Bug 4: 完整流程测试：选取文字 → 加粗 → 再次选取 → 加粗（取消）→ 验证 DOM 无加粗样式
- Bug 5: 完整流程测试：生成知识图谱 → 点击"前往学习" → 验证跳转到正确章节
