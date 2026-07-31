# Slide Deck V5 Design

## Design Principles

1. `CourseDocument` remains the semantic source of truth.
2. A deck is planned before pages are materialized.
3. An agenda is a projection of the planned narrative, not a copy of the course
   tree.
4. Every slide has one teaching job and one primary claim.
5. Visible heading hierarchy contains only:
   - eyebrow: navigation and section context;
   - title: the audience-facing point of the page.
6. Layout slots are contracts, not decorative metadata.
7. Visual rejection triggers layout re-resolution.
8. Web preview and PPTX export consume the same final layout fields.
9. `none` is a valid visual decision.
10. Rendered evidence, not planner intent, decides publication readiness.

## V5 Pipeline

```text
CourseDocument + teaching plan + knowledge/coherence contracts
  -> CommunicationBriefV5
  -> DeckOutlineV5
  -> TeachingEpisode / StoryBeat
  -> SemanticPageGroupV5
  -> CandidateLayoutV5 + slot bindings
  -> visual planning / asset resolution
  -> FinalPageContractV5
  -> web renderer + PPT renderer
  -> object audit + rendered-slide review
  -> publish
```

## Deck-Level Outline

`DeckOutlineV5` is a source-bound structural plan:

```text
schema_version
communication_job
cover
agenda_sections[]
chapters[]
closing
source_revision
planner
fallback_reason
```

### Cover

The cover contains only:

- one eyebrow;
- the canonical course title;
- optional compact metadata such as audience or revision.

It must not contain a learning-mainline card, decorative badge, fake image, or a
third title level. A half-image cover is eligible only when a grounded,
quality-approved image exists.

### Agenda

The agenda contains 3-6 contiguous learning sections. Each agenda section owns
one or more source chapter IDs and has:

- a short audience-facing label;
- one learning outcome or driving question;
- stable source chapter references.

If the course has more than six top-level chapters, deterministic fallback
groups adjacent chapters into balanced learning stages. AI planning may improve
labels, but it cannot reorder dependencies or invent course topics.

### Chapter Arc

A chapter owns a required entry and recap, plus content-supported episodes:

```text
chapter entry
  -> prerequisite activation (optional)
  -> concept / reasoning
  -> method
  -> worked example
  -> practice and feedback (when source-grounded)
  -> misconception repair (optional)
  -> application transfer (optional)
  -> chapter recap
```

Navigation-only chapter pages may derive visible copy from chapter metadata and
learning objectives. Knowledge claims still require source fragments.

### Semantic Compaction

The deterministic V5 fallback selects no more than three complete semantic
groups for each level-2 source section:

1. the core concept or background;
2. a worked example, method, or reasoning group when available;
3. a practice/checkpoint group when available.

The selected group is an atomic page input: the allocator must not split it
again merely because adjacent fragments have different Markdown types.
Oversized atomic groups are rejected rather than truncated. Every unselected
fragment remains source-traceable through an explicit `v5_semantic_core`
exclusion, including in teaching mode. This preserves decision coverage without
turning the slide deck into a dense appendix or reproducing the textbook.

### Closing

The deck always ends with a course-level synthesis, application, next action, or
productive question that resolves the communication job. A generic thank-you
page is not a valid default closing.

## Title Contract

Every non-cover page exposes:

```text
eyebrow
title
```

`subtitle` is not part of the V5 page-heading contract.

The title compiler receives the local scene, topic, primary source claim,
semantic groups, and source references. It returns a direct, speakable title.
The title must not:

- be a raw production instruction;
- be a raw formula or diagram identifier;
- duplicate the first body sentence;
- expose Markdown, code, Mermaid, or LaTeX syntax;
- consist only of numbering or punctuation;
- exceed the configured title budget.

Deterministic fallback prefers the explicit source heading, then a bounded local
claim excerpt. `takeaway` remains body meaning and never overrides `title` in a
renderer.

## Semantic Groups and Slot Binding

Before layout selection, page content is normalized into semantic groups:

```text
definition
boundary
classification_item
comparison_side
process_step
formula
formula_interpretation
example_prompt
example_solution
feedback
misconception
repair
summary_point
visual
```

Each layout declares required semantic slots. A candidate layout is rejected
unless every required slot has a distinct compatible binding.

Examples:

- one prose group cannot satisfy both columns of a two-column layout;
- three sibling classification items select `classification-3` or
  `comparison-matrix`, not `positive-negative`;
- a formula requires adjacent interpretation unless it is intentionally part of
  a larger evidence layout;
- a visual/text split requires an accepted visual and a text group.

## Final Layout Resolution

`FinalPageContractV5` is computed after asset resolution:

```text
requested_layout
resolved_layout
requested_composition
resolved_composition
slot_bindings
visual_decision
fallback_reason
major_region_count
occupied_major_region_count
```

Rules:

- if `visual_decision == none`, visual-required layouts and compositions are
  ineligible;
- if only one text region is bound, a two-column layout is ineligible;
- if a requested layout fails, choose the highest-scoring compatible text-native
  layout;
- renderers use only `resolved_layout` and `resolved_composition`;
- planner intent remains available for diagnostics but cannot control rendering.

## Initial Layout Set

V5 starts with a small reliable set rather than many weak templates:

1. `cover-minimal`
2. `agenda-linear`
3. `chapter-entry`
4. `editorial-body`
5. `balanced-two-column`
6. `classification-3`
7. `comparison-matrix`
8. `process-sequence`
9. `formula-explanation`
10. `worked-example`
11. `practice-feedback`
12. `chapter-recap`
13. `course-synthesis`

Adjacent slides should vary silhouette only within layouts compatible with their
semantic groups.

## Rendering

The existing `SlideSpec` remains the interchange envelope during migration.
V5 adds final layout fields to `quality` first to keep V3/V4 readers compatible:

```text
quality.requested_layout
quality.resolved_layout
quality.requested_composition
quality.resolved_composition
quality.slot_bindings
quality.layout_fallback_reason
```

Both the Vue canvas and PPTX renderer must resolve from those final fields. V5
cover, agenda, and chapter pages use flat presentation-native compositions with
thin rules and restrained accent color rather than UI cards, pills, or badges.

## Quality Gates

The following are critical:

- `required_slot_unfilled`
- `single_group_two_column`
- `visual_layout_without_visual`
- `empty_major_region`
- `orphan_formula`
- `raw_source_sentence_as_title`
- `title_body_duplication`
- `preview_export_contract_mismatch`
- title, visible-item, or body density overflow at the resolved-layout budget
- unresolved required assets or invalid visual programs

The regression set includes quantitative, programming, humanities, business,
and medical/structural course fixtures.

## Rollout

1. Add V5 contracts, deterministic outline compiler, final layout resolver, and
   tests.
2. Make both renderers consume resolved layout fields.
3. Add V5 cover, agenda, chapter, and closing materialization.
4. Add title compiler and optional AI outline/title planning.
5. Add rendered-slide occupancy review and cross-renderer parity fixtures.
6. Enable V5 target schema for eligible courses.
7. Keep V4 as an explicit fallback until the cross-course evaluation set passes.
