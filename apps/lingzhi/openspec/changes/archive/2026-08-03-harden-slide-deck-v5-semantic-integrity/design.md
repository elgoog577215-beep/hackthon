## Goals

1. Preserve complete teaching meaning across AI planning and deterministic
   rendering.
2. Make source provenance and question-answer binding explicit and testable.
3. Fail publication when a visible classification, answer, title, transition,
   definition, or recap is semantically incomplete.
4. Keep web preview and PPTX export on the same final contract.

## Decisions

### Diagram coverage is a contract

For a hierarchy derived from a heading plus source list, the visual plan records
all required list fragment IDs. Node labels use a concise, balanced source
excerpt such as the term before a definition colon. Validation rejects a visual
when any required fragment lacks a node. The renderer never decides which
siblings to drop.

### Practice feedback uses explicit identities

Every visible prompt receives a stable `question_id`. Direct-answer blocks
carry aligned `answer_for_question_ids`, `direct_answer=true`, a generation
mode, and source fragment IDs.

Answer selection follows this order:

1. extract an explicit source answer or feedback beat;
2. when absent and an AI provider is available, request one concise answer per
   supplied question from bounded chapter context;
3. when AI is unavailable or invalid, render related source material only as
   `shared_evidence` with `direct_answer=false`.

The LLM may synthesize an answer but may not change question order, omit a
question, add questions, cite unknown fragments, expose internal planning
language, or return an unbound answer. Invalid AI output falls back to shared
evidence rather than publishing a mismatched pair.

Provider formatting differences are normalized before validation. The planner
canonicalizes an omitted rewrite as `source_exact`, removes internal fragment
IDs accidentally repeated inside answer copy, bounds overlong answers at a
sentence boundary, and treats A/B or 1/2 as non-factual case labels. Unsafe
optional title copy is discarded without losing valid answer directives from
the chapter. When several source-level questions render as one compound prompt
row, their generated conclusions are combined into one direct answer bound to
that row's single stable question ID.

Optional headline, layout, audience-copy, and generated-answer fields fail
independently. An incompatible optional field cannot invalidate its chapter or
other chapters. Chapter calls retain bounded concurrency, and the chapter
timeout matches the provider request window so a healthy slow fallback model
is not cancelled at half of its configured network timeout.

### Micro-transitions do not own slides

A transition-only V4 artifact, including a unit ending in `:transition`, is
removed during V5 materialization. Its next topic and source unit ID are kept on
the preceding instructional slide for audit. True chapter entries remain
eligible because they contain a driving question or learning objective.

### Concept pages expose a formal definition group

Generic template labels are removed from visible copy. A sentence matching a
definition relation becomes a `definition` semantic block and is placed before
supporting context. Editorial groups share one left baseline. Titles ending in
a dependent particle or an unmatched bracket are invalid; the compiler derives
a complete concise claim from the definition instead.

### Recaps contain complete claims

Recap candidates prefer complete takeaway titles and short declarative claims.
Question prompts, template labels, and strings that require a mid-clause hard
cut are ineligible. Four claims render as a 2x2 memory grid in both adapters.

## Quality gates

The following codes are critical:

- `diagram_required_item_missing`
- `practice_direct_answer_unbound`
- `practice_direct_answer_count_mismatch`
- `standalone_transition_page`
- `incomplete_title_claim`
- `concept_definition_missing`
- `recap_item_incomplete`

## Rollout

The compiler and visual-policy versions change in the same release. This makes
the existing production artifact stale. After deployment, the affected course
variant is rebuilt with `force_rebuild=true` and audited before handoff.
