# slide-deck-v5 Specification

## Purpose
TBD - created by archiving change upgrade-slide-deck-v5. Update Purpose after archive.
## Requirements
### Requirement: V5 Plans the Whole Deck Before Materializing Pages

The system SHALL compile a source-bound deck outline containing the communication
job, minimal cover, 3-6 agenda sections, chapter arcs, and an explicit
course-level closing before materializing teaching pages.

#### Scenario: Course has eight top-level chapters
- **WHEN** the V5 deterministic fallback plans the deck
- **THEN** it groups contiguous chapters into no more than six agenda sections
- **AND** every agenda section retains the source chapter IDs it represents

#### Scenario: Course has one top-level chapter
- **WHEN** the V5 planner builds the deck outline
- **THEN** the agenda still contains a meaningful learning section
- **AND** it does not invent unrelated stages merely to reach three items

#### Scenario: Deck reaches its final page
- **WHEN** V5 materializes the complete deck
- **THEN** the final page resolves the communication job through synthesis,
  application, next action, or a productive question
- **AND** the deck does not end abruptly on a detail or generic thank-you page

### Requirement: V5 Uses a Two-Level Page Heading Contract

The system SHALL expose only an eyebrow and one primary title as visible
page-heading levels.

#### Scenario: A slide has an explicit title and a takeaway
- **WHEN** web preview and PPTX export render the slide
- **THEN** both render the explicit title as the primary heading
- **AND** the takeaway may appear only as body meaning or a callout

#### Scenario: Source claim is a long body sentence
- **WHEN** the title compiler creates the page heading
- **THEN** it produces or falls back to a bounded audience-facing title
- **AND** it does not repeat the first body sentence as the title

#### Scenario: Source heading names a numbered section or topic
- **WHEN** the selected source heading is a section label such as `1.1` or a
  topic-only label and the visible semantic group contains a supported claim
- **THEN** V5 keeps section context in the eyebrow or source metadata
- **AND** it uses the visible claim as the primary audience-facing title
- **AND** it does not expose the numbered source heading as the page title

### Requirement: Required Layout Slots Must Be Occupied

The system SHALL reject a candidate layout unless each required semantic slot is
bound to a distinct compatible content group.

#### Scenario: A page has one prose group
- **WHEN** a two-column layout is requested
- **THEN** the final layout resolves to a compatible single-region layout
- **AND** no empty second column is emitted

#### Scenario: A page has three sibling classification items
- **WHEN** the layout resolver evaluates the page
- **THEN** it selects a three-item classification or comparison-matrix layout
- **AND** it does not select a positive-negative or unbalanced two-column layout

### Requirement: V5 Preserves Complete Semantic Groups

The system SHALL select a bounded teaching arc from complete, source-bound
semantic groups and SHALL NOT mechanically split a selected group across
continuation pages.

#### Scenario: One source atom exceeds every layout budget
- **WHEN** a code block, display formula, prose sentence, or list item is larger
  than the safe input capacity of the semantic layout registry
- **THEN** source parsing partitions it at source-native boundaries and assigns
  stable continuation fragment IDs before layout selection
- **AND** all continuation fragments retain the same source block binding
- **AND** V5 either selects the complete bounded semantic group or records the
  complete oversized group as explicit source exclusions
- **AND** an oversized atom does not terminate the whole-course build with a
  layout-capacity exception

#### Scenario: A legacy section contains several Markdown subsections
- **WHEN** deterministic V5 compaction builds the section teaching arc
- **THEN** it selects no more than three complete concept, reasoning/example,
  and practice groups
- **AND** it records every unselected fragment as an explicit source decision

#### Scenario: A selected group mixes prose and a formula
- **WHEN** the allocator materializes the group
- **THEN** it keeps the selected group on one page
- **AND** it rejects an oversized group rather than cutting it at an arbitrary
  fragment boundary

#### Scenario: A selected group promises an enumerated set
- **WHEN** a visible source fragment promises `N` classes, steps, parts, or
  alternatives and the following source list supplies those `N` members
- **THEN** the promise and all required members form one indivisible semantic
  bundle
- **AND** optional background prose is omitted before any required member
- **AND** no required member may be recorded as an allowed semantic-core
  exclusion while the promise remains visible

#### Scenario: A chapter has no source-grounded practice and feedback
- **WHEN** V5 compacts the chapter teaching arc
- **THEN** it omits the unsupported practice episode
- **AND** it does not fabricate a prompt or answer merely to satisfy a template

#### Scenario: A bounded practice group exceeds the renderer row capacity
- **WHEN** complete question-answer pairs require more than one practice page
- **THEN** V5 partitions only at question-answer pair boundaries
- **AND** each page receives stable child semantic atom IDs while retaining the
  parent semantic atom IDs as provenance
- **AND** no question or its bound answer is split across pages

### Requirement: AI Refines the Compact Source-Bound Story

The system SHALL refine the deterministic V5 compact story with chapter-scoped,
source-bound directives before page allocation when an AI provider is
configured and the explicit planner kill switch is not disabled.

#### Scenario: A configured provider refines a multi-chapter course
- **WHEN** V5 has already selected complete semantic groups
- **THEN** the planner receives bounded chapter requests instead of one full-deck
  rewrite request
- **AND** it may select only supplied beat IDs, headline fragment IDs,
  capacity-compatible layout IDs, and supporting fragment IDs owned by the beat
- **AND** it may provide a bounded audience-facing title or summary only as a
  source-faithful rewrite or instructional scaffold
- **AND** every rewrite records its copy mode and exact supporting fragment IDs
- **AND** it must not invent or alter facts, numbers, formulas, units, named
  entities, or conclusions
- **AND** compilation preserves the accepted AI decisions through final
  materialization

#### Scenario: AI returns an invalid or failed refinement
- **WHEN** the configured provider times out, invents an ID, changes source
  claims, or returns an invalid contract
- **THEN** the system retains the deterministic source-bound story for that
  chapter without discarding valid refinements from other chapters
- **AND** it records the failed chapter, failure category, and successful and
  failed chapter counts in planning diagnostics
- **AND** the V5 publication gate reports the unavailable refinement as a
  warning instead of presenting the fallback as an AI-quality result
- **AND** provider availability alone does not block a deterministic deck that
  passes every source, semantic, capacity, composition, and rendering gate

#### Scenario: Every chapter refinement request fails
- **WHEN** all chapter-scoped AI requests time out or return invalid contracts
- **THEN** V5 compiles the complete source-grounded deterministic story
- **AND** the deck remains publishable only if its final page contracts pass
  all non-AI quality gates
- **AND** the planning diagnostics retain one failure result per chapter

#### Scenario: AI supplies a useful teaching transition
- **WHEN** the transition is grounded in fragments already owned by the beat
- **THEN** V5 may use it as audience-facing summary copy
- **AND** the exact primary claim and source provenance remain unchanged

#### Scenario: AI introduces an unsupported factual token
- **WHEN** a rewrite introduces a number, formula symbol, Latin identifier, or
  other protected factual token absent from its supporting fragments
- **THEN** the rewrite contract is rejected
- **AND** the deterministic source-exact beat remains available for diagnosis

### Requirement: Visual Rejection Triggers Layout Re-Resolution

The system SHALL compute the final page layout after visual assets are resolved.

#### Scenario: Requested visual is rejected
- **WHEN** the visual decision becomes `none`
- **THEN** visual-required layouts and compositions become ineligible
- **AND** the page resolves to a complete text-native composition without an
  empty frame

#### Scenario: Visual is accepted
- **WHEN** a source-grounded visual passes quality gates
- **THEN** the resolver may retain a compatible visual-led layout
- **AND** all required text and visual slots remain occupied

#### Scenario: Prose contains an incidental connector
- **WHEN** a connector such as `但是` or `不同` does not bind two meaningful
  local source excerpts into a defensible relationship
- **THEN** V5 resolves the visual decision to `none`
- **AND** it does not chain unrelated paragraphs into a synthetic diagram

#### Scenario: A long deck exceeds the bounded visual-planning budget
- **WHEN** the allocated deck contains more pages than the configured safe
  single-request visual-planning limit
- **THEN** V5 does not send the entire deck through one AI visual-planning call
- **AND** it uses only deterministic source-evidenced visuals whose quality can
  be guaranteed
- **AND** ambiguous pages resolve to `none` and reflow to a complete text-native
  composition without an empty visual region

### Requirement: Web and PPT Render the Same Final Contract

The system SHALL make `resolved_layout` and `resolved_composition` authoritative
for both browser preview and PPTX export.

#### Scenario: Planner requested two columns but resolver selected editorial body
- **WHEN** the same `SlideSpec` is rendered in web and PPT
- **THEN** both renderers use editorial body
- **AND** neither renderer falls back to the stale requested layout

### Requirement: V5 Uses Presentation-Native Opening and Section Rhythm

The system SHALL use minimal cover, linear agenda, sparse chapter transitions,
content-shaped teaching pages, chapter recap, and course synthesis layouts.

#### Scenario: No trustworthy cover image exists
- **WHEN** V5 renders the cover
- **THEN** it uses a typography-led minimal cover
- **AND** it does not render a fake image, empty image frame, badge, button, or
  learning-mainline card

#### Scenario: Chapter entry has no prose fragment
- **WHEN** chapter metadata and a learning objective are available
- **THEN** V5 still renders the chapter transition from navigation metadata
- **AND** it does not fabricate a knowledge claim

### Requirement: V5 Publication Gates Inspect Visible Composition

The system SHALL block publication for unfilled required slots, visual layouts
without visuals, empty major regions, orphan formulas, title/body duplication,
enumeration cardinality mismatches, numbered source headings used as content
titles, or web/PPT final-contract drift.

#### Scenario: One major region is empty
- **WHEN** the empty region is not intentional cover or transition whitespace
- **THEN** quality reports a critical `empty_major_region` issue

#### Scenario: All final contracts are complete
- **WHEN** required slots are occupied, visual fallbacks are resolved, heading
  contracts pass, and both renderers agree
- **THEN** V5 composition integrity does not block publication

#### Scenario: Resolved page exceeds its layout budget
- **WHEN** title characters, visible items, or body characters exceed the
  resolved layout's presentation-safe budget
- **THEN** publication is blocked
- **AND** neither renderer shrinks audience body text below 16 pt or primary
  titles below 35 pt

#### Scenario: Visible claim promises more members than the page contains
- **WHEN** the title or body promises `N` classes, steps, parts, or alternatives
  but fewer than `N` list members are visible
- **THEN** publication is blocked with
  `enumeration_cardinality_mismatch`
- **AND** the incomplete page is not treated as a quality-equivalent fallback

#### Scenario: A final slide retains a page-level critical issue
- **WHEN** any materialized slide reports a critical blocker or failed page
  quality contract
- **THEN** the deck-level V5 publication report is failed
- **AND** the page issue remains visible in the deck blockers

#### Scenario: V5 replaces a V4 page-capacity decision
- **WHEN** V5 reflows a page and the final V5 contract fits its resolved layout
- **THEN** superseded V4 capacity findings are removed from the page and deck
  reports
- **AND** only issues recomputed from the final visible V5 composition may
  block publication

### Requirement: Durable Completion Publishes Atomically

The frontend SHALL reconcile durable task completion to the newly published V5
registry and SHALL clear any intermediate live-slide draft before presenting a
terminal completed state.

#### Scenario: Durable task completes while the event stream is still open
- **WHEN** polling observes `completed` before the SSE stream emits its terminal
  event
- **THEN** the frontend reloads the published registry and selected V5 spec
- **AND** it switches the preview and quality report to the published version
- **AND** stale live slides and draft quality are cleared atomically

### Requirement: Classification Visuals Preserve Required Siblings
The system SHALL render every required source member of a visible hierarchy or
classification and SHALL reject a diagram that silently omits a member.

#### Scenario: Three system types appear in one hierarchy
- **WHEN** the source heading promises three system types and supplies three
  list members
- **THEN** the diagram contains one source-bound node for each of the three
  members and no member is removed by label shortening

#### Scenario: A required label cannot fit safely
- **WHEN** a required source label cannot be shortened without breaking its
  meaning or bracket balance
- **THEN** the visual decision becomes text-only instead of publishing an
  incomplete diagram

### Requirement: Every Direct Answer Is Bound to One Question
The system SHALL assign stable question IDs and SHALL bind each direct answer to
the question it answers.

#### Scenario: Source contains explicit answers
- **WHEN** a practice page has explicit source answers
- **THEN** the published page contains the same number of direct answers as
  questions and records their `answer_for_question_ids`

#### Scenario: Source has no answer and AI is available
- **WHEN** a practice question has no explicit answer and the configured LLM
  returns a valid bounded response
- **THEN** the page publishes one `llm_generated` direct answer for that question
  with supporting source fragment IDs

#### Scenario: Generated answer is invalid or unavailable
- **WHEN** AI is unavailable, omits a question, references unknown evidence, or
  fails validation
- **THEN** the page renders related material only as shared judgment evidence
  and does not pair it positionally with a question

#### Scenario: Provider returns harmless formatting variance
- **WHEN** a provider omits optional copy while echoing a rewrite mode, exceeds
  the answer limit, repeats internal fragment IDs in answer text, or uses A/B
  and 1/2 as case labels
- **THEN** the system canonicalizes that variance before validation while still
  rejecting unsupported factual numbers, formulas, units, and named entities

#### Scenario: Several source questions render as one compound row
- **WHEN** fragment-level prompt questions are combined into one visible prompt
  block by the renderer
- **THEN** their generated conclusions are composed into one direct answer and
  both sides carry the same single stable question ID

#### Scenario: One optional AI field is invalid
- **WHEN** an otherwise valid chapter response contains an incompatible layout,
  an out-of-beat headline or copy binding, or one unsafe generated answer
- **THEN** only that optional field is discarded and valid chapter directives
  remain eligible for publication

#### Scenario: A fallback model responds slowly but within provider limits
- **WHEN** a configured fallback model needs longer than the old chapter timeout
  but remains within the provider request window
- **THEN** the planner waits for that bounded response instead of cancelling the
  chapter early

### Requirement: Transition-Only Pages Are Removed
The system SHALL not publish a full slide whose only teaching job is announcing
the immediately following section.

#### Scenario: Legacy compiler emitted a standalone transition
- **WHEN** a V4 unit has transition scene semantics or a transition-only unit ID
- **THEN** V5 removes the unit and records its next topic on the adjacent
  instructional slide

#### Scenario: Genuine chapter entry follows
- **WHEN** the following unit contains a driving question or learning objective
- **THEN** that chapter entry remains and owns the visible transition

### Requirement: Concept Definitions Are Complete and Aligned
The system SHALL represent a formal definition as a first-class semantic group
and SHALL align all editorial groups to one text baseline.

#### Scenario: Source contains background followed by a definition
- **WHEN** a concept page contains both supporting context and an explicit
  definition sentence
- **THEN** the definition is visible as the primary group before context and no
  generic template label is shown

#### Scenario: Candidate title ends mid-claim
- **WHEN** title compaction would end in a dependent particle, unmatched bracket,
  or incomplete relation
- **THEN** the compiler derives a complete concise claim or blocks publication

### Requirement: Chapter Recaps Use Complete Declarative Claims
The system SHALL compose chapter recaps from complete short claims and SHALL not
hard-cut source strings in the middle of a phrase.

#### Scenario: Candidate exceeds the recap limit without a safe boundary
- **WHEN** a source candidate cannot be shortened to a complete claim
- **THEN** the compiler skips it and selects another source-bound claim

#### Scenario: Four recap claims are available
- **WHEN** a chapter recap contains four complete claims
- **THEN** web preview and PPTX export render the same four claims in a balanced
  2x2 composition without clipping

### Requirement: Semantic Policy Changes Invalidate Existing Decks
The system SHALL include semantic compiler, final-page contract, and visual
policy versions in the build signature.

#### Scenario: Semantic-integrity policy is deployed
- **WHEN** an existing deck was built with the previous policy versions
- **THEN** it is not considered current and a rebuild produces a new spec before
  publication

### Requirement: V5 Compiles One Subject-Neutral Teaching Semantic Protocol

The system SHALL normalize structured V16 courses and legacy courses into one
typed teaching-semantic protocol before story compaction.

#### Scenario: V16 content contains explicit pedagogy metadata
- **WHEN** a block has a module, role, composition, lesson archetype, difficulty,
  knowledge, or evidence contract
- **THEN** those values remain traceable on its PPT semantic unit
- **AND** they take precedence over heading keyword inference

#### Scenario: A legacy course has no module metadata
- **WHEN** the compatibility adapter classifies its source
- **THEN** the same protocol is emitted with a marked fallback source and
  confidence
- **AND** the course uses the same story, layout, and rendering pipeline

### Requirement: Subject Profiles Extend Rather Than Fork The Compiler

The system SHALL map subject modules to common presentation intents through a
data-driven profile registry outside the core renderer.

#### Scenario: An unknown subject is compiled
- **WHEN** no subject profile matches its modules
- **THEN** common block roles and explicit source structures select a safe
  generic intent
- **AND** the build does not fail because a subject-specific rule is absent

### Requirement: Practice And Feedback Form One Interaction Contract

The system SHALL bind every direct answer to stable question IDs.

#### Scenario: Learner action and feedback are adjacent in one lesson
- **WHEN** V5 compacts the section
- **THEN** their fragments remain in one practice-feedback teaching episode
- **AND** feedback records the question IDs it answers

### Requirement: Long Deck Visual Planning Is Chapter-Batched

The system SHALL split visual planning into bounded chapter batches instead of
disabling AI for the entire long deck.

#### Scenario: One visual batch fails
- **WHEN** other chapter batches return valid source-bound plans
- **THEN** accepted batches remain AI planned
- **AND** only the failed batch uses deterministic pages with explicit diagnostics

### Requirement: Final V5 Validation Uses Repaired Visible Contracts

The system SHALL run at most two deterministic repair passes before recomputing
the publication report from final visible pages.

#### Scenario: A V4 capacity warning is resolved by the final V5 layout
- **WHEN** the final page fits its title, character, and item budget
- **THEN** the stale intermediate warning is removed
- **AND** it cannot block publication

#### Scenario: Semantic repair considers merging adjacent pages
- **WHEN** a sparse, dangling, or split-atom page is eligible for a deterministic
  merge
- **THEN** the merge is allowed only when the combined body and visible items
  fit the target page's resolved final-layout budgets
- **AND** semantic repair does not replace one semantic issue with a final-page
  overflow

#### Scenario: The first V5 candidate fails its final publication gate
- **WHEN** the first AI, partially deterministic, or fully deterministic V5
  candidate is not already the strict `quality_fallback` profile
- **THEN** the system retries once with the source-only `quality_fallback`
  profile and newly compiled allocation and visual plans
- **AND** only a candidate that passes all final semantic, capacity,
  composition, export, and rendering gates is atomically published
- **AND** a terminal compiler exception emits its structured blocker and
  original diagnostic message to the durable task and browser client

### Requirement: V5 Builds Are Schema Closed

The system SHALL treat a requested V5 build as a schema-closed operation whose
only terminal outcomes are `v5_ready`, `v5_needs_manual_edit`, and
`v5_failed`.

#### Scenario: V5 generation cannot produce a valid V5 candidate
- **WHEN** a requested V5 build exhausts its allowed in-V5 fallbacks
- **THEN** the build ends as `v5_failed` with a structured reason
- **AND** it does not compile, publish, or present a V3 or V4 candidate

#### Scenario: A page remains visually imperfect but readable
- **WHEN** all source content is present and the page passes readability and export integrity gates
- **THEN** the page is marked `manual_edit_required`
- **AND** the complete deck ends as `v5_needs_manual_edit` instead of failing or changing schema

### Requirement: V5 Builds Freeze A Source Contract

The system SHALL create `ppt_source_contract_v1` from the canonical course
document, course logic, references, and source revision before V5 compilation.

#### Scenario: The course remains static during generation
- **WHEN** the source contract is valid and its revision remains unchanged through commit
- **THEN** all V5 pages and source dispositions refer to that frozen revision

#### Scenario: The source changes during generation
- **WHEN** the source revision at commit differs from the frozen contract
- **THEN** the build ends as `v5_failed`
- **AND** the failure code identifies a source revision conflict as retryable

### Requirement: Internal Materialization Does Not Leak Legacy Candidates

The system SHALL keep legacy materializer pages private to the V5 compiler and
publish preview events only after V5 final page contracts are complete.

#### Scenario: V5 reuses the V3 materializer
- **WHEN** the internal materializer emits base slide updates
- **THEN** those updates are not forwarded as public candidate pages
- **AND** final public page events declare `engine_schema=slide_deck_v5` and `candidate_stage=final_contract`

#### Scenario: A V5 client receives a legacy page event
- **WHEN** the event lacks the V5 final-candidate envelope or declares an older schema
- **THEN** the client ignores it
- **AND** it does not replace the last valid V5 preview

### Requirement: Oversized Sources Use Lossless V5 Safe Pages

The system SHALL render sources that cannot safely use a rich layout with a V5
safe layout and deterministic continuation pages.

#### Scenario: One source unit fits within three safe pages
- **WHEN** a document, code, table, formula, or mixed source exceeds a rich page budget
- **THEN** the system renders it in one to three safe V5 pages
- **AND** records `rendered_in_safe_layout` for every included source fragment

#### Scenario: Completeness requires more than three pages
- **WHEN** three pages cannot contain the source without truncation or unreadable text
- **THEN** the system creates additional continuation pages and records a diagnostic
- **AND** it does not omit content merely to enforce the target page count

### Requirement: Every Source Fragment Has A Final Disposition

The system SHALL assign exactly one auditable final disposition to every source
fragment used by the V5 build.

#### Scenario: Publication completeness is audited
- **WHEN** the final candidate is evaluated
- **THEN** each fragment is `rendered`, `rendered_in_safe_layout`, `moved_to_appendix`, `needs_manual_edit`, or `intentionally_excluded_with_reason`
- **AND** a missing or unexplained disposition blocks publication

### Requirement: V5 Failures Are Structured And Actionable

The system SHALL return a stable V5 failure envelope for every hard failure.

#### Scenario: Infrastructure or compiler integrity fails
- **WHEN** model, storage, renderer, export integrity, source contract, or an unknown compiler invariant fails
- **THEN** the envelope contains `stage`, `code`, `message`, `retryable`, and `source_revision`
- **AND** includes `chapter_id` and `page_id` when the failure is localized

### Requirement: V5 Renderers Fail Closed On Missing Final Layouts

The system SHALL use `quality.resolved_layout` as the only layout authority for
a page carrying the V5 final page contract.

#### Scenario: A final V5 page has no resolved layout
- **WHEN** browser preview, quality audit, or PPTX export resolves the page
- **THEN** publication or export fails with a structured invariant error
- **AND** neither `requested_layout` nor legacy `layout` is used as fallback
