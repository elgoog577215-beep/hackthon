## 1. Unify the Mermaid rendering pipeline

- [x] 1.1 Extract shared Mermaid normalization, syntax-repair, and SVG post-processing helpers into a frontend utility used by both `MarkdownRenderer.vue` and `useMermaid.ts`
- [x] 1.2 Align Mermaid initialization settings across both frontend entry points so theme, font, and security behavior are consistent
- [x] 1.3 Update both rendering paths to use the shared helpers without breaking the existing queued/lazy rendering lifecycle in `useMermaid.ts`

## 2. Fix Markdown preservation and label rendering behavior

- [x] 2.1 Verify and correct the Markdown-to-Mermaid integration so headings and prose around Mermaid code fences remain rendered as Markdown in imported content
- [x] 2.2 Replace destructive inner-quote rewriting with targeted repair logic that preserves formula semantics for labels such as `cos(ωt - kz)`
- [x] 2.3 Tune SVG safety margins and node width adjustments to prevent clipping for Chinese and mixed-width Mermaid labels

## 3. Tighten generation guidance and add regressions

- [x] 3.1 Update `backend/prompts.py` Mermaid instructions to discourage nested unescaped double quotes and recommend Mermaid-safe formula labels
- [x] 3.2 Refresh frontend Mermaid tests to assert the new canonical output instead of the old single-quote rewrite behavior
- [x] 3.3 Add a regression case derived from `tests/test_md_import.md` that covers raw-heading leakage, formula-label preservation, and right-edge clipping prevention

## 4. Verify apply readiness

- [x] 4.1 Run the relevant frontend test suite for Mermaid and Markdown rendering regressions
- [ ] 4.2 Manually verify the known imported Markdown example renders correctly in the UI without Mermaid error states or clipped labels

### 2026-07-23 复核记录

- 在真实课程《电磁学：理论基础与工程应用》中检查到 4 个 Mermaid 容器均生成 SVG，未出现 Mermaid 错误态，容器 `scrollWidth` 与 `clientWidth` 一致。
- 同一课程的旧导入内容仍把 `#### ### 标题` 渲染为带可见 `###` 的四级标题，尚未满足“无原始标题标记泄漏”的人工门禁。
- 当前测试目录中未找到任务 3.3 所述的 `tests/test_md_import.md` 派生回归；归档前需要补齐对应测试并重新执行本节人工验收。
