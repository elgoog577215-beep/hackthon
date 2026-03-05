# Export Markdown/JSON Download Fix Bugfix Design

## Overview

点击顶部导航栏的"导出 Markdown 文档"或"导出 JSON 备份"按钮后，界面显示成功提示，但实际上没有任何文件被下载。

存在两个独立的 Bug：

**Bug A（主要）**：`App.vue` 的 `handleExport` 函数是空壳，只显示成功消息，没有调用 `courseStore` 的导出方法。
**Bug B（次要）**：`course.ts` 的 `downloadBlob` 函数在 `a.click()` 后同步调用 `URL.revokeObjectURL(url)`，可能导致下载失败。

修复策略：
1. 在 `handleExport` 中调用 `courseStore.exportCourseJson()` / `courseStore.exportCourseMarkdown()`，并移除多余的 `ElMessage.success()`（因为 store 方法内部已有成功提示）
2. 在 `downloadBlob` 中将 `URL.revokeObjectURL(url)` 改为 `setTimeout(() => URL.revokeObjectURL(url), 100)`

## Glossary

- **Bug_Condition_A (C_A)**：`handleExport` 函数被调用时，函数体为空壳，不调用任何实际导出逻辑
- **Bug_Condition_B (C_B)**：`downloadBlob` 函数中 `URL.revokeObjectURL(url)` 在 `a.click()` 之后被同步调用
- **Property_A (P_A)**：`handleExport` 应根据 command 参数调用对应的 courseStore 导出方法
- **Property_B (P_B)**：`downloadBlob` 应在 `a.click()` 后延迟撤销 Blob URL
- **Preservation**：ContentArea.vue 的导出功能、downloadNotes、exportNotesMarkdown 等不受影响
- **handleExport**：`frontend/src/App.vue` 中的函数，处理顶部导航栏导出下拉菜单的 command 事件
- **downloadBlob**：`frontend/src/stores/course.ts` 中的工具函数，创建 Blob URL 并触发浏览器下载
- **exportCourseJson**：`course.ts` store 中的 action，将课程数据序列化为 JSON 并调用 `downloadBlob` 下载
- **exportCourseMarkdown**：`course.ts` store 中的 action，将课程内容序列化为 Markdown 并调用 `downloadBlob` 下载

## Bug Details

### Fault Condition A — handleExport 空壳

当用户在顶部导航栏点击导出下拉菜单并选择格式时，`handleExport(command)` 被调用。函数体只包含注释占位符和 `ElMessage.success()` 调用，没有调用 `courseStore.exportCourseJson()` 或 `courseStore.exportCourseMarkdown()`，导致没有任何导出/下载逻辑被执行。

**Formal Specification:**
```
FUNCTION isBugConditionA(input)
  INPUT: input of type ExportCommand
  OUTPUT: boolean

  RETURN input.source = 'top-navbar-dropdown'
         AND input.command IN ['json', 'markdown']
         AND handleExport does NOT call courseStore export methods
END FUNCTION
```

### Fault Condition B — downloadBlob 同步撤销

`downloadBlob` 函数在 `a.click()` 之后立即同步调用 `URL.revokeObjectURL(url)`。由于浏览器下载是异步启动的，Blob URL 在浏览器实际发起下载请求之前就已失效，可能导致下载静默失败。

**Formal Specification:**
```
FUNCTION isBugConditionB(input)
  INPUT: input of type DownloadAction
  OUTPUT: boolean

  RETURN downloadBlob is called with valid blob and filename
         AND URL.revokeObjectURL is called synchronously after a.click()
END FUNCTION
```

### Examples

- 用户在顶部导航栏选择"导出 Markdown 文档" → 显示"Markdown 导出成功"，但无文件下载（Bug A）
- 用户在顶部导航栏选择"导出 JSON 备份" → 显示"JSON 导出成功"，但无文件下载（Bug A）
- 修复后，用户在顶部导航栏选择"导出 Markdown 文档" → 调用 `courseStore.exportCourseMarkdown()`，浏览器下载 `.md` 文件（期望行为）
- 修复后，用户在顶部导航栏选择"导出 JSON 备份" → 调用 `courseStore.exportCourseJson()`，浏览器下载 `.json` 文件（期望行为）
- 当前没有课程/节点/笔记时，点击导出 → 显示"当前没有可导出的内容"警告（不受 Bug 影响，由 store 方法内部处理）

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- ContentArea.vue 内部导出对话框的 `exportToMarkdown`/`exportToJSON` 功能不受影响（不同 UI 路径）
- `downloadNotes`、`exportNotesMarkdown` 等其他使用 `downloadBlob` 的函数继续正常工作
- 当没有可导出内容时，store 方法内部的警告提示继续正常显示
- 导出成功后的成功提示继续正常显示（由 store 方法内部处理）

**Scope:**
- `App.vue`：仅修改 `handleExport` 函数体
- `course.ts`：仅修改 `downloadBlob` 函数中的 `URL.revokeObjectURL` 调用方式
- 不涉及任何其他文件或函数

## Hypothesized Root Cause

### Bug A — handleExport 空壳（已确认）

`handleExport` 函数是开发过程中的未完成代码。函数结构已搭建（if/else 分支判断 command 类型），但实际的导出调用从未被实现，只留下了注释占位符：

```javascript
function handleExport(command: string) {
  if (command === 'json') {
    // Export JSON logic    ← 空注释，没有实际代码
    ElMessage.success('JSON 导出成功')
  } else if (command === 'markdown') {
    // Export Markdown logic ← 空注释，没有实际代码
    ElMessage.success('Markdown 导出成功')
  }
}
```

### Bug B — downloadBlob 同步撤销（已确认）

`downloadBlob` 中 `URL.revokeObjectURL(url)` 在 `a.click()` 之后同步调用：

```javascript
const downloadBlob = (blob: Blob, filename: string) => {
    // ...
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)  // ← 同步撤销，浏览器可能还没启动下载
}
```

`a.click()` 仅通知浏览器"有一个下载请求"，实际的文件 I/O 在后续事件循环中发生。同步撤销 Blob URL 可能导致浏览器访问该 URL 时得到空响应。

## Correctness Properties

Property 1: Fault Condition A — handleExport 应调用 courseStore 导出方法

_For any_ 顶部导航栏导出操作，当用户选择 `'markdown'` 或 `'json'` 格式时，修复后的 `handleExport` 函数 SHALL 调用对应的 `courseStore.exportCourseMarkdown()` 或 `courseStore.exportCourseJson()` 方法，触发实际的文件下载。

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Fault Condition B — downloadBlob 应异步撤销 Blob URL

_For any_ 通过 `downloadBlob` 触发的下载操作，修复后的函数 SHALL 在 `a.click()` 之后通过 `setTimeout` 延迟调用 `URL.revokeObjectURL(url)`，确保浏览器有足够时间启动下载。

**Validates: Requirement 2.4**

Property 3: Preservation — 其他导出路径和行为不变

_For any_ 不涉及 `handleExport` 或 `downloadBlob` 内部 Blob URL 时序的操作，修复后的代码 SHALL 产生与原始代码完全相同的行为。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

**File 1**: `frontend/src/App.vue`
**Function**: `handleExport`

**修复前:**
```javascript
function handleExport(command: string) {
  if (command === 'json') {
    // Export JSON logic
    ElMessage.success('JSON 导出成功')
  } else if (command === 'markdown') {
    // Export Markdown logic
    ElMessage.success('Markdown 导出成功')
  }
}
```

**修复后:**
```javascript
function handleExport(command: string) {
  if (command === 'json') {
    courseStore.exportCourseJson()
  } else if (command === 'markdown') {
    courseStore.exportCourseMarkdown()
  }
}
```

**说明**: 移除了多余的 `ElMessage.success()` 调用，因为 `exportCourseJson()` 和 `exportCourseMarkdown()` 内部已经有 `ElMessage.success('导出成功')` 调用。

---

**File 2**: `frontend/src/stores/course.ts`
**Function**: `downloadBlob`

**修复前:**
```javascript
const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}
```

**修复后:**
```javascript
const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
}
```

## Testing Strategy

### Validation Approach

由于这是前端 UI 交互 Bug，主要通过手动测试验证。项目使用 Vite 进行本地开发。

### Manual Testing Steps

**Bug A 验证（handleExport 修复）：**
1. 启动本地开发服务器：`cd frontend && npm run dev`
2. 打开浏览器，进入应用
3. 选择一个有内容的课程
4. 点击顶部导航栏的导出按钮（下载图标）
5. 选择"导出 Markdown 文档" → 验证浏览器触发文件下载，文件名格式为 `{课程名}_export_{时间戳}.md`
6. 再次点击导出按钮，选择"导出 JSON 备份" → 验证浏览器触发文件下载，文件名格式为 `{课程名}_export_{时间戳}.json`
7. 验证下载的文件内容正确（Markdown 包含课程结构和笔记，JSON 包含完整课程数据）

**Bug B 验证（downloadBlob 修复）：**
- 上述步骤 5-7 同时验证了 downloadBlob 的修复，因为 `exportCourseMarkdown` 和 `exportCourseJson` 都调用 `downloadBlob`

**边界情况验证：**
8. 在没有选择课程时点击导出 → 验证显示"当前没有可导出的内容"警告
9. 验证 ContentArea 内部的导出对话框仍然正常工作（不同 UI 路径）

### Preservation Checking

验证以下行为在修复后保持不变：
- 空内容时的警告提示
- ContentArea 内部导出功能
- 其他使用 downloadBlob 的功能（如 downloadNotes）
