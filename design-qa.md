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
