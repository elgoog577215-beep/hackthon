# Design QA — 新建课程与课程工作台精修（2026-08-22）

## Comparison target

- Source visual truth: `/var/folders/5z/ysrw5tcd3fngb509jyxr533c0000gn/T/codex-clipboard-7c86619e-fc93-460b-aea8-1baa353e3f97.png` (`1436 × 1552`, supplied Retina-style reference).
- Rendered creation route: `http://localhost:5173/teacher/courses/new`.
- Normalized creation screenshot: `output/playwright/course-create-design-qa-718.jpg` (`718 × 776`, CSS viewport `718 × 776`, `devicePixelRatio = 1`).
- Full-view comparison: `output/playwright/course-create-design-qa-comparison-normalized.jpg` (`1454 × 818`).
- Focused header/field comparison: `output/playwright/course-create-design-qa-focused.jpg` (`1454 × 552`).
- Workbench desktop evidence: `output/playwright/course-workbench-refined-center.jpg` (`1280 × 720`) and `output/playwright/course-workbench-refined.jpg` (`1280 × 720`, AI assistant open).
- Mobile evidence: `output/playwright/course-create-refined-mobile.jpg` (`390 × 844`) and `output/playwright/course-workbench-refined-mobile.jpg` (`390 × 844`).
- State: Chinese, light theme, empty creation form with systematic course/intermediate/manual defaults; existing AI-literacy course outline for the workbench.

## Viewport and density normalization

- The `1436 × 1552` source was treated as a 2× capture and downsampled to `718 × 776` for comparison with a `718 × 776` CSS viewport at 1× density.
- The normalized comparison therefore judges component proportions, radius, hierarchy, spacing, selected states and copy density without confusing Retina density with CSS size.
- The desktop workbench and `390 × 844` responsive captures are supplemental product-state evidence rather than direct pixel references for the creation panel.

## Full-view and focused comparison evidence

- The creation route now opens one full-height rounded panel instead of a three-step shell followed by a second dialog. The header, white surface, purple focal icon, large selectable cards, fixed footer and muted backdrop preserve the supplied reference's composition.
- The current product needs course type, goal, knowledge structure, production mode and course scale, so those replace the reference's old teaching-style and free-form requirement groups. Explanatory subtitles and option descriptions are intentionally omitted per the user's instruction.
- The focused comparison confirms a consistent icon family, readable Chinese hierarchy, clear active borders and evenly aligned controls. The mobile capture confirms two-column course-type cards, scrollable content and a fixed action footer without horizontal overflow.
- The workbench captures confirm that the middle formal-content column is a distinct rounded surface with a matching radius/border/shadow system. At `1280px`, the AI assistant overlays instead of compressing the middle column; closing it restores the full content width.

## Findings

- No actionable P0, P1 or P2 visual mismatch remains.
- Fonts and typography: the existing Chinese system sans stack is preserved; titles, labels and actions use a compact hierarchy with no instructional paragraphs. The implementation is intentionally less verbose than the reference.
- Spacing and layout rhythm: creation uses a full-height sheet, fixed header/footer, orderly section dividers and large card controls. Workbench surfaces use `22–24px` primary radii and aligned `12–14px` control radii.
- Colors and visual tokens: the reference's white, cool-gray and violet direction is retained using existing product tokens; semantic green/orange statuses remain limited to readiness states.
- Image quality and asset fidelity: no content imagery is required by the revised fields. Product logo and Lucide icons are used directly; no emoji, handcrafted SVG, CSS illustration or placeholder image was introduced.
- Copy and content: only stable creation fields, values, statuses and actions remain visible. Fixed “大学生” audience is persisted but no longer shown as a form field.
- Interactions and accessibility: verified course-type switching, production-mode switching, required-field disabled submit state, AI assistant open/close, course navigation and desktop/mobile responsiveness. Dialog, fieldset, labels, pressed states and complementary regions remain semantic. Browser console reported no errors for the checked creation interactions.

## Comparison history

- Pass 1 found a P1 composition mismatch: the first implementation was capped at `1080 × 900`, leaving a large empty perimeter and losing the reference's full-sheet presence.
- Fix: expanded the course-space dialog to `1320px` and `calc(100vh - 28px)`, retained its fixed footer, and captured `output/playwright/course-create-refined-top.jpg` plus the normalized post-fix comparison.
- Pass 2 found a P2 workbench crowding issue at `1280px`: keeping the assistant as a fixed third grid column compressed and clipped the middle summary surface.
- Fix: changed the assistant to an overlay below `1500px`; post-fix evidence is `output/playwright/course-workbench-refined.jpg`, and the unobstructed middle surface is `output/playwright/course-workbench-refined-center.jpg`.
- Pass 3 found no remaining actionable P0/P1/P2 issue. Full-view, focused-region and mobile evidence all use the current verified implementation state.

## Follow-up polish

- P3: if future testing shows teachers frequently use 700–760px landscape windows, the course panel may adopt a small outer inset instead of the current bottom-sheet treatment at that breakpoint.

final result: passed

---

# Design QA — 题库外部文件导入工作区（2026-08-24）

## Comparison target

- Source visual truth: `/Users/yq/.codex/generated_images/01a0342a-0fe8-7aa3-99ed-b33c7ae910fd/exec-cfa1d530-c7e2-4eef-84a9-9e8f620d1b1b.png` (`1488 × 1058`).
- Rendered implementation: `http://127.0.0.1:5173/course/6d9e2eec-2e95-468c-ad5c-c02dc8f63543/workspace/build?stage=question-bank`.
- Implementation screenshot: `/tmp/lingzhi-question-bank-import-qa-20260824.png` (`1440 × 1024`).
- Full-view comparison: `/tmp/lingzhi-question-bank-import-comparison-20260824.png` (`2880 × 1024`).
- Focused editor/footer comparison: `/tmp/lingzhi-question-bank-import-comparison-focused-20260824.png` (`1400 × 774`).
- State: Chinese, light theme, real three-question DOCX import restored after refresh; all questions confirmed, formal import intentionally not executed.

## Viewport and density normalization

- Browser CSS viewport and implementation screenshot are both `1440 × 1024` at density `1`.
- The source was normalized from `1488 × 1058` to `1440 × 1024` with Lanczos resampling before the side-by-side comparison. Its aspect ratio differs by less than `0.1%`, so layout proportions remain comparable without crop drift.

## Full-view and focused comparison evidence

- The full-view comparison confirms the intended hierarchy: retained global course-stage rail, secondary AI action, four-step import progress, source file bar, left original document, right structured editor, and a single formal-import footer. The redundant right information-source rail is absent in this mode.
- The focused comparison covers question navigation, warning/success status, type selection, prompt, options, answer controls, explanation, per-question confirmation and the final import gate. The implementation integrates the correct-answer radio with each option instead of duplicating a second answer row; this is an intentional density reduction and preserves the same task.
- The source uses a PDF page image and 32-question pending state; the implementation evidence uses a parsed DOCX and three-question confirmed state. These content/state differences are expected and were not judged as visual drift.

## Findings

- No actionable P0, P1 or P2 mismatch remains.
- Fonts and typography: the existing Chinese system sans stack and compact label hierarchy match the source direction; the document preview intentionally uses the product's serif reading stack. No clipping or broken wrapping was observed.
- Spacing and layout rhythm: the left rail and split work area preserve the source proportions. The final revision constrains the review surface to the available viewport and keeps the import footer visible at `1440 × 1024`.
- Colors and visual tokens: existing white/cool-gray/violet tokens match the source; green success and orange warning remain semantic and restrained.
- Image quality and asset fidelity: the target contains no decorative raster imagery. The implementation uses the existing Lucide icon family and parsed document text; no placeholder image, handcrafted SVG, CSS drawing or emoji was introduced.
- Copy and content: file status, question count, pending count, warning reason and import consequence are concise and task-specific. AI generation is visibly secondary.
- Interaction and accessibility: verified refresh recovery, automatic selection of the pending question, answer selection, per-question confirmation, disabled-to-enabled formal-import gate, semantic form controls and zero browser console warnings/errors. The final import was not clicked to avoid adding test questions to the formal course bank.

## Comparison history

- Pass 1 found P2 viewport overflow: the editor's natural content height expanded the split view to about `789px`, placing the persistent formal-import action below the initial viewport.
- Fix: constrained the desktop review surface to `max(480px, calc(100vh - 442px))`, retained internal scrolling for source/editor content, and kept stacked narrow-screen behavior automatic.
- Pass 2 evidence: the review surface measured `582px` and the formal-import footer ended at `1023.6px` in the `1440 × 1024` viewport. The post-fix full and focused comparisons show the complete task hierarchy with no remaining P0/P1/P2 finding.

## Follow-up polish

- P3: a future scanned-PDF/OCR iteration can add page-region highlighting after the parser exposes bounding boxes; the current text-layer preview correctly avoids inventing unavailable coordinates.

final result: passed

---

# Design QA — 课程生产工作台（2026-08-22）

## Comparison target

- Source visual truth: `/var/folders/5z/ysrw5tcd3fngb509jyxr533c0000gn/T/codex-clipboard-e801322e-01ec-4848-b584-676b6c9cedf5.png` (`3402 × 1762`, supplied at 2× density).
- Source intent: preserve the existing blue-purple course-space language and master-detail composition, while turning the category surface into the primary production console and keeping the file view as the secondary free-form organizer.
- Rendered implementation: `http://127.0.0.1:5173/course/2ba26f2c-0f00-4702-bc1c-0d8296ec76a7/workspace/setup`.
- Desktop implementation screenshot: `/tmp/lingzhi-workbench-audit.RbrGjH/implementation-desktop-final.png` (`1701 × 881`).
- Mobile implementation screenshot: `/tmp/lingzhi-workbench-audit.RbrGjH/implementation-mobile-final.png` (`390 × 844`).
- Combined same-state comparison: `/tmp/lingzhi-workbench-audit.RbrGjH/before-after-comparison-final.png` (PPT empty state in both source and implementation).

## Full-view and focused-region comparison

- The centered mode switch now leads with “工作台”; the file view remains adjacent and was verified to switch without changing the course identity.
- The left production rail keeps the source's four-category structure, but adds dependency order, stage descriptions, honest counts and total progress. The right side keeps one content surface and adds a persistent course-production settings strip plus a contextual empty-state console.
- Focused inspection covered the top mode switch, production rail, settings strip, PPT prerequisite card and outline start state. The final empty course reports `0/4` and outline `0/1`; it no longer treats an empty document revision as a finished outline.

## Mandatory QA findings

- Fonts and typography: existing product font stack, weight hierarchy and 12px-or-larger support text are preserved; workbench titles, stage descriptions and action copy remain scannable at desktop and mobile widths.
- Spacing and layout: desktop retains the source's compact left rail and broad work surface; the added settings strip does not create a duplicate toolbar. At `390 × 844`, the rail becomes a vertical preparation overview and the content continues below it without horizontal overflow (`scrollWidth = innerWidth = 390`).
- Colors and tokens: existing blue-purple brand, neutral surfaces, and orange/green semantic states are reused. No new palette or decorative effects were introduced.
- Image quality and assets: the target surface contains no content imagery; implementation uses the existing Lucide icon family and does not substitute raster placeholders, custom SVG art or CSS illustrations.
- Copy and content: Chinese and English locale keys cover “Workbench”, shared production settings, dependency guidance and stage actions. The settings dialog restores the persisted generation request and preserves material bindings when no replacement file is uploaded.
- States and interactions: verified workbench/file-view switching, settings dialog opening, PPT-to-outline prerequisite routing, outline start action, desktop/mobile layout, and zero browser errors or warnings.
- Accessibility: actions remain semantic buttons with visible labels, the progress control exposes a progressbar role, mobile tap targets remain practical, and no text or control is clipped at the checked breakpoint.

## Comparison history

- Pass 1 found a P1 state-truth mismatch: an empty course with only a document revision was shown as outline `1/1` even though the editor reported no outline.
- Fix: outline readiness now requires real course nodes; a regression test covers the empty-revision case.
- Pass 2 found no actionable P0, P1 or P2 mismatch. Focused component tests and the production build passed after the fix.

final result: passed

---

# Prior Design QA — 课程分类主从浏览

## Comparison target

- Source visual truth: `/var/folders/5z/ysrw5tcd3fngb509jyxr533c0000gn/T/codex-clipboard-d704dd46-cef4-41c5-bb18-06a598083f60.png`
- Source intent: 保留现有“左侧生产分类、右侧工作区”的构图与产品视觉；用户本轮明确要求右侧不再显示第二张产物表，而是直接显示当前内容，教案等课次资产在左侧分类下展开。
- Rendered implementation: `http://localhost:5173/course/130ef446-b68a-4375-a019-27de292d3f51/workspace/setup`
- Implementation screenshot: `/tmp/lingzhi-category-qa.4PHLSc/category-outline-implementation.png`
- Expanded lesson-plan screenshot: `/tmp/lingzhi-category-qa.4PHLSc/category-plan-empty-implementation.png`
- Combined comparison evidence: `/tmp/lingzhi-category-qa.4PHLSc/category-reference-implementation-comparison.png`

## Viewport and normalization

- Source pixels: `3420 × 1398`; source density metadata was not available.
- Implementation browser CSS viewport: `949 × 904`; `devicePixelRatio = 2`.
- Implementation screenshot pixels: `949 × 904`; the in-app browser normalized capture to CSS pixels.
- Comparison normalization: the source image was proportionally downsampled to `949 × 388` and stacked above the unchanged `949 × 904` implementation capture. The different aspect ratios reflect the supplied wide screenshot versus the user's current in-app browser panel, so comparisons focus on information architecture, hierarchy, density, and component treatment rather than pixel coordinates.
- State: desktop, Chinese, light theme. Full-view comparison uses “课程大纲 / 已就绪”; focused interaction evidence uses “教案 / 第一课次 / 未生成”.

## Full-view comparison evidence

- The implementation preserves the source's left category navigation, selected blue-purple category state, restrained status colors, and a single right-side content region.
- The obsolete right-side table is gone. The selected outline's real headings and learning objectives are rendered directly inside a readable document surface.
- The existing global top bar, compact centered file/category switch, and established brand tokens remain intact.

## Focused region comparison evidence

- `/tmp/lingzhi-category-qa.4PHLSc/category-plan-empty-implementation.png` confirms that selecting “教案” expands the lesson list in place, keeps the current lesson visibly selected, and shows the matching empty detail state on the right.
- DOM inspection confirmed the expanded `教案` group, a selectable lesson child, direct content rendering for `课程大纲` and `正文`, and exactly one “新建” action in the empty lesson-plan state.
- A separate crop was unnecessary because the left navigation and right detail region are both legible in the full implementation captures.

## Findings

- No actionable P0, P1, or P2 mismatch remains.
- Fonts and typography: existing product family and weights are preserved; 12px supporting text remains readable, while object titles and document headings have a clear hierarchy.
- Spacing and layout rhythm: the sidebar remains compact, child lessons use an indented tree instead of another row or panel, and the document surface provides enough reading width without compressing the top bar.
- Colors and visual tokens: existing blue-purple brand, neutral borders, and semantic green/orange status colors are reused; no new palette was introduced.
- Image quality and asset fidelity: no new raster assets, logos, illustrations, or handcrafted icons were introduced; existing Lucide icons and the product logo remain unchanged.
- Copy and content: Chinese and English keys are both present; the right side displays real outline/body/lesson-plan/PPT projection content or an honest missing state.

## Comparison history

- Formal comparison pass 1: no P0/P1/P2 findings. The reference and implementation intentionally differ on the right because the user's request replaces the old production table with direct content.
- Interaction pass: verified category selection, lesson expansion, lesson switching, direct outline/body rendering, missing-state generation entry, and zero browser console errors.

## Implementation checklist

- [x] Remove the category production table.
- [x] Expand lesson-scoped categories in the left navigation.
- [x] Switch right-side detail content when the selected lesson changes.
- [x] Render real outline, lesson plan, lesson body, and supported PPT content without a new API or content truth.
- [x] Keep missing states and existing create/open/export actions usable.
- [x] Verify Chinese/English locale JSON, focused tests, production build, OpenSpec, and browser runtime.

final result: passed

---

# Course file inspector design QA

- Source visual truth: `/var/folders/5z/ysrw5tcd3fngb509jyxr533c0000gn/T/codex-clipboard-0c8088df-9c05-4bc8-81e4-219f5eb5d90e.png`
- Desktop implementation: `/tmp/lingzhi-inspector-audit.9dDkl0/desktop-inspector-ready.png`
- Mobile implementation: `/tmp/lingzhi-inspector-audit.9dDkl0/mobile-final-top.png` and `/tmp/lingzhi-inspector-audit.9dDkl0/mobile-final-actions.png`
- Focused comparison: `/tmp/lingzhi-inspector-audit.9dDkl0/reference-vs-implementation.png`
- Mobile comparison: `/tmp/lingzhi-inspector-audit.9dDkl0/mobile-before-after.png`
- Desktop viewport: 1440 × 1000 CSS px, device scale factor 1, screenshot 1440 × 1000 px.
- Mobile viewport: 390 × 844 CSS px, device scale factor 1, screenshot 390 × 844 px.
- Source pixels: 1382 × 1608 px. The focused source inspector was cropped to 623 × 1566 px, normalized to 312 px wide, and compared with the 312 × 920 px implementation inspector crop.
- State: file view with the AI assistant closed. Desktop covers a selected missing managed asset, a ready managed asset, and a materials folder. Mobile covers the session folder and its action area. The reference uses a missing practice asset while the implementation uses the equivalent missing lesson-plan state, so copy differs intentionally while hierarchy and action treatment are comparable.

## Full-view comparison

- The desktop implementation preserves the reference hierarchy: object header, status, file information, a large quiet details region, and a persistent bottom action area.
- The live product uses the existing blue-purple tokens, Lucide icon set, table density, borders, and typography rather than introducing a parallel visual system.
- The ready asset state exposes `Open` as the primary action and `Export` as a subordinate action. Fixed course assets never expose delete.
- The materials-folder state exposes `Add material` as primary and `New folder` as secondary.

## Focused comparison

- Typography: title, section title, metadata labels, values, and action copy retain the same relative optical hierarchy as the reference. The product font remains the current application font.
- Spacing and layout: the inspector remains 312 px wide on desktop; metadata rows and the bottom action dock align with the reference rhythm without adding nested cards.
- Colors and tokens: status dots, blue-purple icon surfaces, borders, muted metadata, and the solid primary action use the current product tokens and preserve reference semantics.
- Image and icon quality: there are no raster product assets in this component. Existing library icons remain sharp and consistent; no custom SVG or CSS-drawn icon was introduced.
- Copy: Chinese and English both render through the existing i18n dictionaries. The action hint explains version/export/delete boundaries without replacing action labels.

## Comparison history

1. Initial mobile finding — P1: the stacked inspector consumed the remaining height and made the file list effectively disappear.
   - Fix: the mobile layout now provides a 170 px folder region, at least a 280 px / 45 vh file-list region, then the inspector in the same scroll flow.
   - Post-fix evidence: `mobile-final-top.png` shows the folder tree, file list, selected session, and the start of inspector information in one coherent sequence.
2. Second mobile finding — P2: allowing inspector metadata to overflow while retaining the desktop flex layout placed the action dock before trailing metadata rows.
   - Fix: the mobile inspector now uses normal block flow, automatic metadata height, and a non-sticky action section.
   - Post-fix evidence: `mobile-final-actions.png` shows all metadata rows before `Available actions`, with no overlap or reordering.

## Interaction and runtime checks

- Tested workbench/file-view switching, AI assistant collapse, folder navigation, managed-asset selection, ready/missing states, and opening/closing the New folder dialog without submitting data.
- Uploaded-file Preview / Download / Delete coverage is automated because the current local course package has no uploaded assets; the focused component test verifies that action matrix and that managed assets omit Delete.
- Browser console: no errors in the verified desktop state.
- Responsive: desktop Chinese and mobile English states were inspected. English `Not generated` wraps in the narrow status column but remains readable and does not overlap controls; classified as P3 polish.

## Findings

No actionable P0, P1, or P2 findings remain.

## Follow-up polish

- P3: a future density pass may shorten the English mobile status label or slightly widen the status track to avoid two-line wrapping at 390 px.

final result: passed
