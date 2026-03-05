# Implementation Plan

- [ ] 1. Fix handleExport empty stub in App.vue
  - In `frontend/src/App.vue`, replace the `handleExport` function body
  - Change `command === 'json'` branch: replace comment + `ElMessage.success('JSON 导出成功')` with `courseStore.exportCourseJson()`
  - Change `command === 'markdown'` branch: replace comment + `ElMessage.success('Markdown 导出成功')` with `courseStore.exportCourseMarkdown()`
  - Remove the standalone `ElMessage.success()` calls (store methods already show success messages internally)
  - _Bug_Condition: handleExport is called but does not invoke any courseStore export method_
  - _Expected_Behavior: handleExport calls courseStore.exportCourseJson() for 'json' command and courseStore.exportCourseMarkdown() for 'markdown' command_
  - _Preservation: No other functions in App.vue are modified; courseStore methods handle empty-content warnings internally_
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 2. Fix downloadBlob synchronous revokeObjectURL in course.ts
  - In `frontend/src/stores/course.ts`, in the `downloadBlob` function (line 38-46)
  - Replace `URL.revokeObjectURL(url)` with `setTimeout(() => URL.revokeObjectURL(url), 100)`
  - This ensures the browser has time to initiate the download before the Blob URL is revoked
  - _Bug_Condition: URL.revokeObjectURL is called synchronously after a.click() in downloadBlob_
  - _Expected_Behavior: URL.revokeObjectURL is called asynchronously via setTimeout(100ms) after a.click()_
  - _Preservation: All callers of downloadBlob (exportCourseJson, exportCourseMarkdown, exportNotesMarkdown, downloadNotes) benefit from this fix without any changes_
  - _Requirements: 2.4, 3.3_

- [ ] 3. Manual verification
  - Start local dev server: `cd frontend && npm run dev`
  - Open browser, select a course with content
  - Click top navbar export dropdown → select "导出 Markdown 文档" → verify browser downloads `.md` file
  - Click top navbar export dropdown → select "导出 JSON 备份" → verify browser downloads `.json` file
  - Verify downloaded file contents are correct
  - Verify empty-content warning still shows when no course is selected
  - Verify ContentArea internal export dialog still works (different UI path)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_
