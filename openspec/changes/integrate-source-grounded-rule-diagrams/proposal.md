## Why

The course-to-PPT pipeline currently treats visual-looking source as page furniture instead of as typed teaching content. This produces three visible failures:

- Mermaid source is flattened into a generic code fragment and can be published as raw `graph TD` text.
- formulas and headings are paginated as independent atoms, so a continuous explanation is split into low-value or formula-only slides.
- image-like placeholders and unconstrained generated illustrations can consume a slide even when their semantic or visual quality is not defensible.

The product does not currently have a dependable image-generation model. The safe near-term capability is therefore not free-form image generation; it is source-grounded rule-diagram compilation. A language model may select a diagram template and extract source-bound labels, while deterministic renderers own geometry, validation, and fallback.

## What Changes

- Preserve fenced-block language during source fragmentation and classify Mermaid as a diagram rather than generic code.
- Introduce a typed, source-grounded rule-diagram contract shared by web preview and native PPT rendering.
- Add a generic diagram compiler with small domain template packs instead of course-specific prompt branches.
- Keep headings, formulas, and their explanatory prose together during semantic pagination whenever capacity permits.
- Make raster illustration generation explicitly opt-in and degrade unavailable or low-confidence visuals to text-only slides.
- Add pre-publish blockers for raw Mermaid leakage, invalid rule diagrams, empty visual frames, and contextless formula pages.
- Move visual intent selection ahead of final pagination in the target AI chain so layout decisions can account for the visual that will actually be rendered.

## Capabilities

### New Capabilities

- `source-grounded-rule-diagrams`: Compile source evidence into bounded, editable rule diagrams and safely degrade to text when the contract or layout cannot be validated.

### Modified Capabilities

- `course-ppt-generation`: Use semantic content groups and visual intent before final page allocation, with publish-time visual integrity gates.

## Impact

- Backend source fragmentation, story planning, page allocation, visual planning, asset resolution, PPT rendering, and release-quality validation.
- Frontend slide visual rendering and its component tests.
- Course-agnostic behavior for science, engineering, humanities, and other subjects through a generic core plus optional template packs.
- Existing generated course data is not rewritten automatically; affected decks must be regenerated to receive the new behavior.

