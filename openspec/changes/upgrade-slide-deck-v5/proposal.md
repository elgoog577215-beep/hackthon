# Upgrade Slide Deck Generation to V5

## Why

The current V4 slide pipeline improves source grounding and semantic pagination,
but it still behaves like a page allocator in several visible ways:

- a requested two-column layout may survive even when only one semantic region
  has content;
- a visual may be rejected while the page keeps a visual-dependent composition;
- browser preview and PPTX export can select different effective layouts;
- raw source sentences are promoted into slide headings instead of being compiled
  into a stable two-level title contract;
- cover, roadmap, chapter transitions, and course closing are not planned as one
  deck-level narrative;
- chapter entry and recap beats may exist in the story manifest but disappear
  from the rendered deck when they have no prose fragment;
- quality gates do not reject empty major regions, unfilled required slots, or
  title/body duplication.

These failures are especially visible in long course decks, where repeated
left-heavy pages, mechanical titles, abrupt chapter transitions, and unnecessary
pagination make the result look unlike a presentation.

## What Changes

V5 introduces one shared presentation contract between story planning, layout
selection, visual resolution, web preview, and PPTX export.

1. Add a deck-level outline that defines the communication job, minimal cover,
   3-6 agenda sections, chapter teaching arcs, and an explicit course closing.
2. Limit visible page-title hierarchy to an eyebrow and one primary title.
3. Bind semantic content groups to required layout slots before accepting a
   layout.
4. Resolve the final layout after visual assets are accepted or rejected.
5. Make `resolved_layout` and `resolved_composition` authoritative for both web
   and PPT renderers.
6. Add presentation-native layouts for classification, comparison, formula
   explanation, process, worked example, practice feedback, and recap.
7. Add critical publication gates for empty major regions, invalid slot
   occupancy, visual-dependent layouts without visuals, orphan formulas, and
   preview/export contract drift.
8. Roll out V5 with an explicit target schema while retaining V4 as a reversible
   fallback during migration.

## Expected Outcome

For knowledge-led courses, generated decks should exhibit the same core
discipline as a mature presentation workflow: a deliberate opening and closing,
clear section rhythm, one teaching job per slide, content-shaped layouts,
source-grounded titles, and deterministic degradation when no trustworthy
visual is available.

V5 does not claim to replace photography or high-end illustration generation.
When visual quality cannot be guaranteed, a complete text-native composition is
the correct successful result.

