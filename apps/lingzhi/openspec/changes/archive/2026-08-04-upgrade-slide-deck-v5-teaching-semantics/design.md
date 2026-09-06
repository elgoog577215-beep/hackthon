# Design

## Pipeline

```text
CourseDocument
  -> V16 structured adapter | legacy compatibility adapter
  -> PptSemanticUnitV2
  -> TeachingEpisodeContractV2
  -> story/allocation plan
  -> chapter-batched visual planning
  -> FinalPageContractV2 repair and validation
  -> web/PPT renderers
```

## Decisions

1. The core compiler uses subject-neutral teaching roles and presentation
   intents. Subject module IDs are confined to a data-driven profile registry.
2. Structured module and role metadata outrank headings. Heading inference is a
   marked legacy fallback with lower confidence.
3. `learner_action` and `feedback_check` are one interaction contract. A source
   answer wins; a bounded LLM answer is allowed only when the source has none and
   must retain question and evidence IDs.
4. Story and visual AI calls are chapter-batched. A failed batch keeps its
   deterministic pages without erasing accepted batches.
5. Final repair is deterministic and bounded to two passes. Publication remains
   blocked when a final visible contract still fails.

## Compatibility

The existing `SlideSpec` envelope and `slide_deck_v5` schema remain public.
Semantic units, episode contracts, per-page planner provenance, and final repair
diagnostics are additive internal fields. Build signatures include the semantic
compiler, subject-profile, visual-batching, and final-contract policy versions.
