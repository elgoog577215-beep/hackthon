## ADDED Requirements

### Requirement: V6 Freezes Every Authoritative Input
The system SHALL build `ppt_source_contract_v2` before planning and SHALL freeze the canonical course revision, ordered active course blocks, formal teaching plan, knowledge snapshot, template version and planning policies.

#### Scenario: Course changes during generation
- **WHEN** the course document revision or active block digest differs at publication
- **THEN** the candidate ends as `v6_failed` with `source_revision_changed`
- **AND** the last published representation remains available

#### Scenario: Template changes during generation
- **WHEN** the selected template version or digest differs at publication
- **THEN** the candidate ends as `v6_failed` with `template_revision_changed`
- **AND** the compiler does not silently use the newer template

### Requirement: V6 Builds A Complete Course Presentation Graph
The system SHALL deterministically compile `course_presentation_graph_v1` from `CourseDocument`, ordered active `CourseBlock` values and the formal teaching plan before applying any presentation capacity.

#### Scenario: A complete teaching loop spans several adjacent blocks
- **WHEN** concept, explanation, artifact, operation, result, practice and feedback share one source section and dependency chain
- **THEN** the graph preserves their source order in one or more connected teaching units
- **AND** it records their prerequisite and dependent relationships

#### Scenario: One block contains more than 230 characters
- **WHEN** the graph compiler processes that block
- **THEN** character count does not split the teaching unit
- **AND** capacity is considered only during final page allocation

#### Scenario: Adjacent blocks belong to different topics
- **WHEN** they lack a shared teaching unit or formal transition
- **THEN** the graph keeps them in separate units
- **AND** they are not merged merely to fill a page

### Requirement: Every Formal Course Block Has A Primary Presentation
The system SHALL assign every active formal course block to exactly one primary teaching unit and SHALL bind its complete source text to speaker notes.

#### Scenario: A block is reused as supporting context
- **WHEN** another unit references the same block
- **THEN** the block retains one primary owner and may appear as supporting evidence elsewhere
- **AND** coverage metrics do not double count it

#### Scenario: Final deck omits one formal block
- **WHEN** primary visible coverage is below 100% or note binding is below 100%
- **THEN** publication fails with `course_block_coverage_incomplete`
- **AND** no generic exclusion reason can convert it to success

### Requirement: Characteristic Artifacts Form Atomic Teaching Combinations
The system SHALL keep required code, formulas, tables, experiment data and source evidence adjacent to their conditions, explanation and result.

#### Scenario: A programming unit contains code and expected output
- **WHEN** V6 allocates the unit
- **THEN** the page budget is derived from contiguous source slices that satisfy the published template's artifact and slot-capacity contracts
- **AND** the compact default may expand beyond three pages only when the template-safe partition requires additional narrative room
- **AND** adjacent pages preserve the code, execution conditions, explanation and result
- **AND** generic prose cannot replace the code artifact

#### Scenario: A mathematical unit contains definition, formula and derivation
- **WHEN** V6 allocates the unit
- **THEN** formula and derivation remain source-bound and ordered after their definition
- **AND** no fixed formula identifier or course title selects the rule

#### Scenario: A humanities unit contains source excerpt and interpretation
- **WHEN** the same graph rules process the unit
- **THEN** the source excerpt and interpretation remain bound without a mathematics or programming branch

### Requirement: Story AI Is Mandatory And Source Bound
The system SHALL run chapter-scoped `slide_story_plan_v3` batches through the shared `AIBase` provider pool and SHALL NOT publish a deterministic story as an AI result.

#### Scenario: AI story planning succeeds
- **WHEN** every batch selects only supplied teaching units and template layouts and passes validation
- **THEN** accepted batches merge in original course/dependency order
- **AND** diagnostics identify the provider, model, duration, retries and validation result

#### Scenario: One story batch fails
- **WHEN** a provider is unavailable, a batch is invalid, or validation rejects it
- **THEN** the whole V6 candidate ends as `v6_failed`
- **AND** the failure identifies stage, code, retryability and chapter/batch
- **AND** the previous published deck remains available

#### Scenario: Story AI omits or invents a source
- **WHEN** a batch omits a formal block, references an unknown ID, inverts a dependency or introduces an unsupported fact
- **THEN** the batch is rejected
- **AND** no partial or deterministic substitute is published

### Requirement: V6 Uses Only Published Template Layout Contracts
The system SHALL resolve every final page through `template_layout_contract_v1` from the frozen published template version.

#### Scenario: Story AI requests a legacy layout
- **WHEN** it returns `two-column`, `answer`, `data-highlight` or another identifier absent from the V6 contract
- **THEN** validation fails with `template_layout_unavailable`
- **AND** the compiler does not heuristically choose an old renderer layout

#### Scenario: A specialized layout inherits a base layout
- **WHEN** the published template declares finite, cycle-free inheritance with compatible slots and adapters
- **THEN** V6 resolves the inherited contract explicitly
- **AND** records the base layout ID in page diagnostics

#### Scenario: A required slot is empty or over capacity
- **WHEN** allocated content cannot occupy every required slot within declared capacity
- **THEN** the unit is repaginated into at most three declared safe pages or fails
- **AND** the renderer does not emit an empty card, shrink below minimum size or crop content

#### Scenario: A source-critical code artifact has no supporting prose
- **WHEN** a source block contains a complete code artifact but no source-backed annotation
- **THEN** the code template uses an optional support slot and gives the artifact the available canvas width
- **AND** V6 does not invent annotation text or combine an unrelated topic merely to fill the slot

### Requirement: Visual AI Has A Controlled Page-Level Degradation
The system SHALL plan `slide_visual_plan_v2` in bounded chapter batches and SHALL distinguish optional visual enrichment from subject-critical artifacts.

#### Scenario: Decorative visual planning fails
- **WHEN** a page can retain all required source meaning in a declared text-native layout
- **THEN** the page records a visual degradation and uses that layout
- **AND** the deck ends as `v6_needs_manual_edit`

#### Scenario: A required visual artifact cannot be represented
- **WHEN** source-critical code, formula, table, data or evidence would be lost or no compatible template layout exists
- **THEN** the candidate ends as `v6_failed`
- **AND** it does not publish a prose paraphrase as equivalent

### Requirement: Degraded Visuals Are Repaired Selectively
The system SHALL repair a published `v6_needs_manual_edit` deck from its frozen story, healthy visual decisions, source revision and template contract without restarting the full course build.

#### Scenario: A teacher retries degraded pages
- **WHEN** one or more published visual decisions are marked degraded
- **THEN** the durable repair task sends only those page IDs to visual AI
- **AND** preserves all healthy story and visual decisions unchanged
- **AND** reports each target page and degradation reason

#### Scenario: Selective visual repair succeeds
- **WHEN** every target page produces a source-bound, template-valid visual decision and the rebuilt Web/PPTX contract passes all gates
- **THEN** a new V6 spec revision is published atomically
- **AND** the prior published spec remains available in history

#### Scenario: Selective visual repair fails or races a newer publication
- **WHEN** any target remains degraded, source/template inputs drift, rendering fails, or the base representation changes during repair
- **THEN** the repair task fails with a structured `visual_repair` or `publish` reason
- **AND** the previously published V6 revision remains the public version

### Requirement: V6 Publishes One Final Cross-Renderer Contract
The system SHALL compile `slide_deck_v6` with resolved template layout IDs, typed slots, source bindings, speaker notes, visual decisions and renderer adapters for both Web and PPTX.

#### Scenario: Web preview and PPTX export render one page
- **WHEN** the page is materialized
- **THEN** both renderers consume its resolved layout and slots from `slide_deck_v6`
- **AND** neither renderer re-evaluates story intent or legacy aliases

#### Scenario: Full source is too dense for the canvas
- **WHEN** a teaching unit requires compression for projection
- **THEN** the canvas contains a semantically closed source-faithful expression
- **AND** complete source text and full code remain in speaker notes with block and revision bindings

#### Scenario: A full course contains multiple top-level sections
- **WHEN** the final V6 deck is compiled from the frozen full-course document
- **THEN** one or more `agenda-path` pages are inserted from the ordered source section titles
- **AND** agenda pages bind section IDs without claiming visible `CourseBlock` coverage
- **AND** chapter-only shadow documents with one top-level section do not receive a false course agenda

#### Scenario: Source prose contains semantic paragraphs
- **WHEN** a body slot projects multiple source paragraphs or list groups
- **THEN** paragraph and list boundaries remain visible rather than being flattened into an arbitrary sentence stream
- **AND** capacity selection ends at a complete semantic group or complete source sentence

#### Scenario: A task contains explicit ordered steps
- **WHEN** the source declares two or more ordered actions
- **THEN** the final layout uses the published vertical numbered-sequence composition
- **AND** Web and PPTX preserve one source step per numbered row in source order

#### Scenario: A source table exceeds one slide's readable capacity
- **WHEN** wrapped cell height, row count or protected identifiers cannot fit the selected table variant without semantic loss
- **THEN** the compiler selects a declared full-width or wide table variant, or paginates complete rows across continuation pages with the header repeated
- **AND** a single oversized row is promoted to a source-bound detail expression instead of being clipped
- **AND** no renderer or compiler inserts an ellipsis that was absent from the source
- **AND** every visible identifier, number, formula and code token remains complete; otherwise the candidate fails before publication

### Requirement: V6 Applies Fidelity And Render Gates Before Atomic Publication
The system SHALL publish only after course coverage, order, fact traceability, subject artifacts, teaching intent, template capacity, render integrity and export checks pass.

#### Scenario: A final page contains an untraceable fact
- **WHEN** a number, formula, identifier or factual assertion lacks a source binding
- **THEN** publication fails with a page-scoped diagnostic

#### Scenario: A final page has multiple incompatible teaching jobs
- **WHEN** its visible regions lack one dominant instructional task or reading order
- **THEN** the unit is repaginated or publication fails with `presentation_grammar_mismatch`

#### Scenario: All hard gates pass with no degradation
- **WHEN** source and template remain frozen and both renderers pass
- **THEN** the version publishes atomically as `v6_ready`

#### Scenario: A candidate fails after a V5 or V6 deck was published
- **WHEN** any hard gate fails
- **THEN** the candidate records `v6_failed`
- **AND** the registry continues to serve the last published deck

### Requirement: All V6 Entry Points Share One Durable Orchestrator
The system SHALL route every V6 generation request into the same persisted orchestration, AI, validation and publication path.

#### Scenario: A compatibility route cannot reach the orchestrator
- **WHEN** the durable task service is unavailable
- **THEN** the route returns `v6_orchestrator_unavailable`
- **AND** it does not compile a deterministic story or visual plan inline

#### Scenario: Provider rotation is required
- **WHEN** the first configured AI provider fails and the existing pool has another eligible provider
- **THEN** `AIBase` applies the shared rotation policy
- **AND** V6 does not use a PPT-specific credential or course-specific provider branch

### Requirement: V6 Is General Across Subjects
The system SHALL implement grouping, planning, pagination and quality gates through typed evidence and contracts rather than course identity.

#### Scenario: A regression scan inspects V6 source
- **WHEN** the implementation is validated
- **THEN** it contains no branches on course title, course ID, fixed formula, fixed asset ID or fixed chapter structure
- **AND** programming, mathematics/data and non-math/non-programming fixtures pass the same public contracts

### Requirement: Chapter Shadow Validation Never Replaces A Published Deck
The system SHALL support an explicit V6-only shadow request for one selected section subtree and SHALL run the same source, AI, template, render and export gates without publishing the candidate.

#### Scenario: A canonical online chapter is shadow built
- **WHEN** an authenticated caller supplies `shadow_only=true`, `engine_version=v6` and an existing `chapter_id`
- **THEN** the durable orchestrator freezes only that chapter and its descendants
- **AND** the terminal candidate reaches 100% with `published=false`
- **AND** the course registry continues to serve its previous deck

#### Scenario: A legacy online course is inspected without migration
- **WHEN** the same read-only shadow request selects a chapter from a legacy projection
- **THEN** V6 may freeze the projected chapter for validation without persisting a canonical migration
- **AND** missing formal prerequisite artifacts still fail explicitly rather than being synthesized or bypassed

#### Scenario: A caller requests a shadow artifact
- **WHEN** the task belongs to the requested course and passed the final gates
- **THEN** the authenticated candidate and its exportable PPTX are available from the shadow diagnostics endpoints
- **AND** a public build, cross-course task or failed candidate is not exposed as a successful shadow artifact
