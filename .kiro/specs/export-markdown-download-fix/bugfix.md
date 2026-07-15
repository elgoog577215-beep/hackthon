# Bugfix Requirements Document

## Introduction

点击顶部导航栏的"导出 JSON 备份"或"导出 Markdown 文档"按钮后，界面显示成功提示，但实际上没有任何文件下载发生。

存在两个 Bug：

**主要 Bug（Bug A）**：`App.vue` 中的 `handleExport` 函数（第 299-307 行）是一个空壳——只显示成功消息，没有调用任何实际的导出逻辑。顶部导航栏的导出下拉菜单（第 186-196 行）通过 `@command="handleExport"` 触发此函数，但函数体内只有 `ElMessage.success(...)` 而没有调用 `courseStore.exportCourseJson()` 或 `courseStore.exportCourseMarkdown()`。

**次要 Bug（Bug B）**：`course.ts` 中的 `downloadBlob` 工具函数（第 38-46 行）在 `a.click()` 之后立即同步调用 `URL.revokeObjectURL(url)`。即使 Bug A 修复后，由于浏览器下载是异步启动的，Blob URL 在浏览器实际发起下载请求之前就被撤销，可能导致下载静默失败。

受影响文件：
- `frontend/src/App.vue` — `handleExport` 函数（主要 Bug）
- `frontend/src/stores/course.ts` — `downloadBlob` 函数（次要 Bug）

**注意**：之前的分析错误地将 `ContentArea.vue` 的 `exportToMarkdown`/`exportToJSON` 识别为问题代码。这些函数由 ContentArea 内部的导出对话框触发，属于不同的 UI 路径，且已经应用了 setTimeout 修复。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户在顶部导航栏点击导出下拉菜单并选择"导出 Markdown 文档" THEN 系统显示"Markdown 导出成功"提示，但没有调用 `courseStore.exportCourseMarkdown()`，没有任何文件下载到本地

1.2 WHEN 用户在顶部导航栏点击导出下拉菜单并选择"导出 JSON 备份" THEN 系统显示"JSON 导出成功"提示，但没有调用 `courseStore.exportCourseJson()`，没有任何文件下载到本地

1.3 WHEN `handleExport` 函数被调用时 THEN 函数体只包含注释和 `ElMessage.success()` 调用，没有任何实际的导出/下载逻辑

1.4 WHEN `downloadBlob` 函数执行时（被 `exportCourseJson`、`exportCourseMarkdown`、`exportNotesMarkdown`、`downloadNotes` 调用） THEN 系统在 `a.click()` 之后立即同步调用 `URL.revokeObjectURL(url)`，可能导致 Blob URL 在浏览器启动下载前就失效

### Expected Behavior (Correct)

2.1 WHEN 用户在顶部导航栏点击导出下拉菜单并选择"导出 Markdown 文档" THEN 系统 SHALL 调用 `courseStore.exportCourseMarkdown()`，触发浏览器文件下载，将课程内容保存为 `.md` 文件

2.2 WHEN 用户在顶部导航栏点击导出下拉菜单并选择"导出 JSON 备份" THEN 系统 SHALL 调用 `courseStore.exportCourseJson()`，触发浏览器文件下载，将课程数据保存为 `.json` 文件

2.3 WHEN `handleExport` 函数被调用时 THEN 函数 SHALL 根据 `command` 参数值（`'json'` 或 `'markdown'`）调用对应的 courseStore 导出方法

2.4 WHEN `downloadBlob` 函数执行时 THEN 系统 SHALL 在 `a.click()` 之后延迟足够时间（如 100ms）再调用 `URL.revokeObjectURL(url)`，确保浏览器有时间启动下载

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 当前没有课程、节点和笔记可导出时 THEN 系统 SHALL CONTINUE TO 显示"当前没有可导出的内容"警告提示，不触发下载

3.2 WHEN ContentArea 内部导出对话框触发的 `exportToMarkdown`/`exportToJSON` 函数执行时 THEN 系统 SHALL CONTINUE TO 按原有逻辑正常工作（这些函数已有 setTimeout 修复，不受本次修改影响）

3.3 WHEN `downloadNotes`、`exportNotesMarkdown` 等其他使用 `downloadBlob` 的函数执行时 THEN 系统 SHALL CONTINUE TO 正常触发文件下载

3.4 WHEN 导出成功后 THEN 系统 SHALL CONTINUE TO 显示成功提示消息
