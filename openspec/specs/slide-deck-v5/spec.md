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

#### Scenario: One AI-planned optional visual is structurally invalid
- **WHEN** a chart lacks numeric source data or another page-level visual fails
  its source and structure contract
- **THEN** V5 rejects that page's visual before final compilation and uses the
  deterministic source-bound visual decision for that page
- **AND** valid visual decisions from the same batch remain usable

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

### Requirement: Final V5 Pages Are Presentation Native

The system SHALL publish teaching pages as source-bound visual regions rather
than a sequence of prose documents placed on slide canvases.

#### Scenario: A concept, method, or reasoning source is one long paragraph
- **WHEN** the source contains two or three complete source-bound judgments
- **THEN** the compiler exposes them as two or three visible semantic regions
- **AND** the final page does not use `editorial-body`

#### Scenario: A source contains exactly four peer regions
- **WHEN** the regions do not express a causal or ordered process
- **THEN** the final page uses a balanced 2x2 parallel composition
- **AND** no region is hidden or collapsed into a singleton continuation

#### Scenario: A source contains labeled error and inference pairs
- **WHEN** three errors and their available inferences are present
- **THEN** the final page renders three equal judgment regions
- **AND** retains the source wording for every error and inference

#### Scenario: A sparse source contains one intentional claim
- **WHEN** the claim cannot be combined without changing its teaching intent
- **THEN** it may use an explicit `hero-claim` page
- **AND** browser preview and PPTX export render that claim as the dominant
  full-canvas teaching object rather than a small label surrounded by unused
  space
- **AND** generic teaching-job scaffolding is not shown in place of the claim
- **AND** no complete deck contains more than three such pages

#### Scenario: A dedicated code page has no source-bound annotation
- **WHEN** a selected code excerpt is the page's only occupied semantic region
- **THEN** browser preview and PPTX export expand the code region to the
  available teaching canvas
- **AND** neither renderer emits an empty annotation or reading-hint column

#### Scenario: A dedicated code page has source-bound annotation
- **WHEN** an explanation, output, condition, or interpretation is bound to the
  selected code excerpt
- **THEN** the page may use a split code-and-annotation composition
- **AND** both major regions contain visible source-grounded meaning

#### Scenario: A planned visual is `kind=none`
- **WHEN** final layout occupancy and visual quality are evaluated
- **THEN** the placeholder does not count as an effective visual region
- **AND** it cannot justify a visual-directed layout

### Requirement: Navigation And Continuation Copy Remains Complete

The system SHALL preserve a complete visible teaching title and navigation
mainline after every semantic and render repair pass.

#### Scenario: Semantic repair empties a chapter entry mainline
- **WHEN** the chapter outline still contains a learning objective or driving question
- **THEN** the compiler restores a navigation statement from that outline
- **AND** avoids copying an adjacent content page verbatim

#### Scenario: A continuation page is rendered
- **WHEN** a source unit spans more than one page
- **THEN** every continuation title retains a complete source-bound base title
- **AND** appends an explicit `续N/M` sequence without dangling conjunctions or hidden headings

### Requirement: Render Repair Preserves Presentation Semantics

The system SHALL repair only the failing capacity or renderer behavior and
SHALL NOT convert every render issue into a prose-only safe page.

#### Scenario: Two regions request a three-region classification layout
- **WHEN** final contract resolution finds exactly two occupied semantic regions
- **THEN** it selects `balanced-two-column`
- **AND** the renderer does not add an empty third region

#### Scenario: A three-region page mixes block content and list items
- **WHEN** the final layout is `classification-3`
- **THEN** the renderer treats block content and list items as peer regions
- **AND** renders the page heading exactly once

#### Scenario: Export audit finds a critical issue
- **WHEN** deterministic repair cannot preserve the page's semantic regions and minimum 16pt body text
- **THEN** the V5 candidate fails with the localized export issue
- **AND** it is not silently replaced by an `editorial-body` page

#### Scenario: The production application host lacks render QA binaries
- **WHEN** the deployed chain has passed semantic and PPTX structural gates but
  LibreOffice or PDF rasterization is unavailable on the application host
- **THEN** the result remains `passed_pending_render` and the private PPTX is
  rendered by an isolated CI runner using the same checked-in QA logic
- **AND** publication evidence is marked passed only after the rendered page
  count matches and the render artifacts are retained with the report

### Requirement: Presentation-Native Density Is A Publication Gate

The system SHALL compute presentation density from final visible pages.

#### Scenario: A final teaching deck contains prose-only editorial pages
- **WHEN** more than 35 percent of eligible teaching pages are text-only editorial pages
  or three such pages are consecutive within one chapter
- **THEN** publication is blocked with a presentation-density issue
- **AND** chapter boundaries reset the consecutive-page counter

#### Scenario: A chapter recap repeats a preceding claim
- **WHEN** the repetition is used as an explicit retrieval summary
- **THEN** it is exempt from adjacent-content duplication
- **AND** all other material adjacent duplication remains blocking

#### Scenario: Practice rendering adds prompt and feedback labels
- **WHEN** allocation estimates the body capacity of a practice-feedback page
- **THEN** it reserves space for renderer-added labels and interaction chrome
- **AND** the final visible page remains within the resolved layout budget

#### Scenario: A practical lab mixes an assignment, operating steps, and checks
- **WHEN** source-bound practice copy asks the learner to create, run, inspect,
  modify, or verify an artifact rather than answer a closed question
- **THEN** V5 preserves the activity as an overview, ordered procedure, and
  verification sequence using their corresponding visual grammars
- **AND** it does not attach unrelated conceptual prose as a synthetic answer
  or judgment-evidence column
- **AND** adjacent underfilled task pages are consolidated without changing
  source order or dropping source fragment bindings
- **AND** layout choices from an earlier generic story pass do not prevent task
  items from being reflowed into phase-specific task pages
- **AND** task overview and verification use prompt/checklist grammar while
  operating steps use a readable vertical numbered sequence
- **AND** one task activity uses no more than four readable pages

#### Scenario: A task activity is consolidated after pagination
- **WHEN** several source-safe pages are recomposed into fewer final pages
- **THEN** their visible title sequence is renumbered against the final page
  count
- **AND** every original task item remains visible exactly once
- **AND** the final task phases remain ordered as overview, procedure, then
  verification
- **AND** a source procedure atom may span pages only when every affected page
  belongs to the same explicitly ordered task continuation; all other semantic
  atom splits remain blocking failures

#### Scenario: Structured source syntax ends with a semicolon or colon
- **WHEN** the terminal punctuation belongs to code, a complete checklist row,
  or another structured region rather than unfinished prose
- **THEN** the quality gate does not classify that punctuation alone as a
  dangling fragment
- **AND** a bare instructional scaffold or genuinely unfinished clause remains
  blocking

### Requirement: V5 Is A Course-Native Teaching Projection

The system SHALL treat the canonical course document and formal teaching plan
as the teaching narrative authority. V5 may compress and visually reorganize
that narrative for projection, but SHALL NOT independently reconstruct a
different sequence of claims from disconnected source fragments.

#### Scenario: A course section already forms a complete teaching loop
- **WHEN** its ordered source blocks express concept, explanation, example or
  artifact, learner action, and feedback
- **THEN** V5 preserves that relative teaching order in one or more adjacent
  teaching episodes
- **AND** every page remains traceable to the source section, module instance,
  semantic unit, and source fragment IDs that established the loop

#### Scenario: Course prose is too dense for direct projection
- **WHEN** the canonical section cannot fit readable slide budgets verbatim
- **THEN** V5 selects complete source-bound judgments and artifacts while
  preserving the section's teaching intent and dependencies
- **AND** it does not copy the entire prose document onto slides or replace it
  with an unrelated slide-only narrative

#### Scenario: Adjacent source modules depend on one another
- **WHEN** an example, runnable artifact, output, modification, or feedback
  depends on an earlier concept or action
- **THEN** the story plan records the dependency in one teaching episode chain
- **AND** compaction cannot separate the dependent page from all of its
  prerequisite context

#### Scenario: Source fragments come from different course topics
- **WHEN** they do not share one section-level teaching episode or an explicit
  transition in the formal teaching plan
- **THEN** they cannot be combined merely to fill a page
- **AND** a visible transition is required before the deck changes topics

### Requirement: Every V5 Build Has A Subject Presentation Contract

The system SHALL compile a typed subject presentation contract after source
fragmentation and semantic normalization, and before V5 story compaction. The
contract SHALL use the persisted pedagogy profile, subject modules, lesson
archetypes, and source artifact evidence instead of relying only on a course
title or a model prompt.

#### Scenario: A programming and engineering course contains runnable code
- **WHEN** code, execution output, mechanism, modification, debugging, testing,
  or architecture evidence is present in the canonical course
- **THEN** the contract marks the applicable evidence as characteristic
  teaching artifacts
- **AND** the story plan preserves at least one complete source-bound
  implementation loop per applicable chapter

#### Scenario: A non-programming subject is compiled
- **WHEN** its subject profile requires formulas, derivations, experiment data,
  source excerpts, timelines, dialogues, cases, charts, or another domain
  representation
- **THEN** the contract records the required and optional representation kinds,
  minimum chapter coverage, and supported page compositions
- **AND** generic text layouts alone cannot satisfy a required representation

#### Scenario: Subject classification is uncertain
- **WHEN** the persisted profile has low confidence or conflicts with module and
  source artifact evidence
- **THEN** the compiler records `subject_profile_evidence_conflict` or requests
  confirmation before claiming subject-specific completeness
- **AND** it does not silently apply an unrelated subject grammar

#### Scenario: A migrated legacy course lacks subject pedagogy metadata
- **WHEN** course-logic upgrade promotes an existing canonical course into the
  V5 prerequisite contracts
- **THEN** it derives a subject profile from the canonical title and existing
  course evidence and persists that profile with the course module plan and
  pedagogy quality contract
- **AND** the formal teaching plan receives the matching subject-native lesson
  modules before the knowledge base and coherence contract are compiled
- **AND** the canonical course document and its revision remain unchanged
- **AND** an ambiguous or internally conflicting subject classification cannot
  be presented as subject-specific completeness

### Requirement: Characteristic Teaching Artifacts Are Non-Discardable

The system SHALL distinguish optional prose from characteristic artifacts that
are required by the subject presentation contract. A characteristic artifact
cannot receive a generic semantic-core exclusion merely because it exceeds a
text page budget or loses a competition between three source groups.

#### Scenario: A code, formula, table, diagram, dataset, or source excerpt is long
- **WHEN** the artifact is required for the current teaching episode
- **THEN** V5 paginates it at a semantically safe boundary and retains its
  explanation, conditions, and expected result on adjacent pages
- **AND** it does not replace the artifact with a prose paraphrase

#### Scenario: A programming chapter contains more source code than a presentation can teach legibly
- **WHEN** complete code coverage would exceed three dedicated code pages in one
  chapter
- **THEN** V5 renders a source-exact teaching excerpt on one to three code pages
  while preserving the selected excerpt's source order
- **AND** every omitted code fragment is recorded as
  `subject_artifact_redundant_after_chapter_coverage` instead of being silently
  discarded or converted to editorial prose

#### Scenario: Final semantic pagination expands a code excerpt
- **WHEN** semantic-atom boundaries would split the selected excerpt into more
  than three final code pages
- **THEN** the final allocator retains the first three source-ordered pages and
  applies the same explicit disposition to overflow fragments
- **AND** no later compiler or renderer stage may re-expand the chapter beyond
  the three-page code contract

#### Scenario: The source contains more characteristic artifacts than the deck needs
- **WHEN** the subject coverage minimum is already satisfied by stronger,
  complete teaching loops
- **THEN** additional artifacts may be intentionally excluded with a specific
  pedagogical reason
- **AND** the disposition cannot be the undifferentiated
  `v5_semantic_core` reason

#### Scenario: A required artifact is missing or invalid
- **WHEN** the course lacks the source evidence required by its subject contract,
  or the artifact cannot pass the applicable syntax, structure, or binding gate
- **THEN** the candidate ends as `v5_failed` or `v5_needs_manual_edit` according
  to whether the defect changes teaching correctness
- **AND** the failure identifies the missing or invalid representation and its
  source section

### Requirement: Subject Fidelity Is A Final Publication Gate

The system SHALL evaluate the final visible deck against the subject
presentation contract after semantic and render repair.

#### Scenario: A programming course publishes without code
- **WHEN** the canonical source contains valid runnable code but no final page
  renders a code artifact
- **THEN** publication is blocked with `required_subject_representation_missing`
- **AND** generic concept, column, or diagram pages do not satisfy the code
  requirement

#### Scenario: Render repair would erase a characteristic artifact
- **WHEN** a required code, formula, data, source, or experiment page fails a
  capacity or export check
- **THEN** repair preserves the artifact through semantic pagination or returns
  a localized failure
- **AND** it cannot convert the page to `editorial-body` and still publish

#### Scenario: Optional decorative media is unavailable
- **WHEN** subject-critical source artifacts remain readable and complete
- **THEN** missing decorative imagery is a warning rather than a subject
  fidelity blocker
- **AND** the final report distinguishes optional visual richness from required
  disciplinary representation

### Requirement: Every Semantic Region Has An Intent-Specific Presentation Grammar

The system SHALL assign every visible semantic region a typed presentation
grammar derived from its teaching intent and the course subject presentation
contract. The grammar SHALL define `presentation_intent`, `copy_voice`,
`information_structure`, `visual_grammar`, `allowed_layouts`, and
`forbidden_fallbacks`. These local grammars SHALL remain inside one coherent
deck-level visual system for typography, color, spacing, grid, and navigation;
they SHALL NOT become arbitrary per-block template changes.

#### Scenario: A page explains a concept or definition
- **WHEN** the dominant teaching intent is to establish meaning, boundary, or
  relationship
- **THEN** the copy uses concise explanatory or judgment language and includes
  the applicable boundary, example, or counterexample
- **AND** the visual grammar uses hierarchy, relationship, or a structurally
  justified concept composition rather than a raw prose dump

#### Scenario: A page explains a mechanism, cause, or process
- **WHEN** the source expresses causality, execution order, state change, data
  movement, or procedural steps
- **THEN** the copy preserves explicit connectors such as cause, condition,
  consequence, and sequence
- **AND** the visual grammar uses the applicable causal, control-flow,
  data-flow, state, or sequence composition rather than unordered peer cards

#### Scenario: A page teaches through code, formula, data, evidence, or a source artifact
- **WHEN** a characteristic artifact carries the teaching meaning
- **THEN** the artifact is the dominant visible object and its annotations,
  result, or interpretation remain source-bound and adjacent
- **AND** the page cannot satisfy the intent by paraphrasing the artifact into
  generic body text

#### Scenario: A page compares alternatives or corrects a misconception
- **WHEN** the teaching intent is comparison, diagnosis, correction, or
  verification
- **THEN** the copy uses consistent comparison axes or the explicit sequence
  of symptom, cause, correction, and verification
- **AND** the visual grammar uses a paired, matrix, before-and-after, or
  diagnostic composition instead of scattered paragraphs

#### Scenario: Practice and feedback are presented
- **WHEN** a learner-facing region is a task, exercise, check, answer, rubric,
  or remediation
- **THEN** task copy is actionable and withholds the direct answer, while
  feedback copy is diagnostic and names the applicable criterion or error
- **AND** task and feedback regions are visually distinguishable and cannot be
  collapsed into the same generic content card

#### Scenario: A page provides navigation or recap
- **WHEN** the dominant intent is orientation, transition, retrieval, or recap
- **THEN** the copy is brief and points to the course thread being entered,
  left, or recalled
- **AND** the region does not introduce a new concept through long-form prose

#### Scenario: One page receives incompatible semantic jobs
- **WHEN** semantic regions cannot share one dominant teaching intent or one
  coherent reading order
- **THEN** the story planner splits them across pages or retains only the
  source-authorized teaching episode
- **AND** it does not combine unrelated regions merely to reduce whitespace

#### Scenario: Final expression does not match teaching intent
- **WHEN** the rendered copy voice, information structure, visual grammar, or
  layout is incompatible with the assigned presentation intent
- **THEN** the quality gate records `presentation_grammar_mismatch` with the
  page, region, expected grammar, and observed fallback
- **AND** a mismatch that erases or changes required teaching meaning blocks
  publication, while a non-critical mismatch requires explicit manual review
