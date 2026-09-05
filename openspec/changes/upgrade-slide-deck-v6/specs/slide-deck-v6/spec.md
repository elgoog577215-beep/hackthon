## ADDED Requirements

The enhanced requirements below govern new `page_teaching_v2` manuscripts. Previously stored versions retain their original read/export behavior; migrating them requires an explicit new draft rather than silent normalization.

### Requirement: V6 Freezes Every Authoritative Input
The system SHALL build `ppt_source_contract_v2` before planning and SHALL freeze the current structurally usable, source-current teacher script, canonical course projection, ordered active blocks, formal teaching-plan revision, relevant accepted assets, published template version and planning policies. A teacher-script confirmation flag SHALL NOT be an additional prerequisite. The script remains the content authority; contextual knowledge SHALL NOT introduce new facts during PPT production.

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
- **AND** template capabilities inform draft planning, while measured capacity is checked during layout binding before manuscript confirmation

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

#### Scenario: Final deck omits source accountability
- **WHEN** any formal block lacks its primary owner, complete note binding or explicit screen-versus-notes disposition
- **THEN** publication fails with `course_block_coverage_incomplete`
- **AND** an unsupported exclusion reason cannot convert it to success

#### Scenario: Teacher exposition is represented visually
- **WHEN** a validated draft represents an explanatory paragraph through a source-bound comparison or diagram
- **THEN** the source remains complete in notes and every required teaching condition, relation and evidence item is represented on screen
- **AND** the system does not require every word of that paragraph to appear on slides
- **AND** marking core teaching evidence as notes-only without an adequate teaching rationale does not satisfy screen completeness

### Requirement: Characteristic Artifacts Form Atomic Teaching Combinations
The system SHALL keep required code, formulas, tables, experiment data and source evidence adjacent to their conditions, explanation and result.

#### Scenario: A programming unit contains code and expected output
- **WHEN** V6 allocates the unit
- **THEN** the draft page budget is derived from the source-bound code range selected for the teaching task and the published template's artifact and slot-capacity contracts
- **AND** before confirmation the allocation expands to the declared safe pages needed for that selected range and all required conditions and results, within the explicit lesson pacing budget; exceeding that budget requires draft reorganization or an explicit budget revision
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
The system SHALL run lesson-scoped `slide_story_plan_v3` batches through the shared `AIBase` route using the designated private `qwen3.8-27b`, SHALL produce a source-bound lesson narrative brief and real page-level teaching decisions, and SHALL NOT publish a deterministic story as an AI result. Historical chapter scopes remain read-compatible.

#### Scenario: AI story planning succeeds
- **WHEN** every batch selects only supplied teaching units and template layouts and passes validation
- **THEN** accepted batches merge in original course/dependency order
- **AND** the lesson narrative brief records the central question, ordered learning path, observable checkpoints, time budget and must-include source blocks
- **AND** every planned page records a concrete goal, central question or claim appropriate to its teaching role, and source bindings; learner actions have an expected response or observable evidence, progressive pages have reveal states, and adjacent pages have applicable transitions
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

#### Scenario: Required teaching content is missing or unsupported
- **WHEN** a page omits required role-specific content, binds only slot names without a semantic expression, or asks a practice question unrelated to its source task
- **THEN** the batch is rejected with a page-scoped structural or source diagnostic
- **AND** the compiler does not fill the missing decision with a fixed sentence and continue

#### Scenario: Wording could be pedagogically improved
- **WHEN** a source-valid and structurally usable page has a generic transition, repetitive title or weak stylistic phrasing
- **THEN** the reviewer records an actionable suggestion
- **AND** a heuristic wording preference alone does not become a hard source or structure failure

### Requirement: The Page Manuscript Is The Only Editable Content Contract
The system SHALL store `ppt_manuscript_v1` as the sole editable page-level content contract between the current usable teacher script and the final PPT. For `page_teaching_v2`, content planning, visual structure, asset selection, layout binding, capacity preflight and physical page order SHALL finish before explicit manuscript confirmation. Draft previews MAY render before confirmation but SHALL NOT be published as the final PPT.

#### Scenario: A teacher edits a draft page
- **WHEN** the teacher changes its visible copy or teaching fields using the current manuscript revision
- **THEN** the system creates a new draft revision and synchronizes the visible copy into the materialized page regions
- **AND** it reruns source-fidelity and teaching-content validation for the affected page
- **AND** the previous confirmed manuscript remains immutable while the new revision requires confirmation

#### Scenario: Two editors save the same draft revision
- **WHEN** a stale revision attempts to overwrite a newer manuscript draft
- **THEN** the save fails with a revision-conflict response containing the current revision
- **AND** neither revision is silently overwritten

#### Scenario: Rendering receives unconfirmed or inconsistent content
- **WHEN** the manuscript is unconfirmed, its source revision is stale, or its visible copy differs from final page regions
- **THEN** final deck generation is blocked with structured manuscript diagnostics
- **AND** the renderer does not reinterpret or rewrite the content

### Requirement: Teachers Can Lock And Regenerate Page Content Selectively
The system SHALL support page-level teacher locks and targeted manuscript regeneration while retaining the last good draft and all non-target content.

#### Scenario: A teacher regenerates selected pages
- **WHEN** the request contains explicit target page IDs and the current manuscript revision
- **THEN** Story AI receives only the targets and their bounded neighboring context
- **AND** every non-target page and every source-current locked page remains byte-for-byte unchanged
- **AND** the result is saved as a new unconfirmed draft revision only after all target pages pass validation

#### Scenario: One target page fails regeneration
- **WHEN** the provider fails or the regenerated content violates source or teaching-content gates
- **THEN** the operation returns page-scoped diagnostics
- **AND** the last good manuscript draft remains available without a partial overwrite

#### Scenario: A locked page has stale source
- **WHEN** one of its bound source blocks changes
- **THEN** the page is marked as an explicit lock/source conflict requiring teacher action
- **AND** the system neither preserves it as current nor silently unlocks and rewrites it

### Requirement: Manuscript Rebuild Follows Source Bindings And Accepted Assets
The system SHALL compute manuscript impact from page-to-source bindings and SHALL treat accepted question-bank items and shared visual expressions as optional, revision-bound inputs rather than parallel content sources.

#### Scenario: One source block changes
- **WHEN** the current script publishes a new revision for that block
- **THEN** the system identifies only manuscript pages bound to the changed block as affected
- **AND** source-current unbound pages retain their content, order and lock state

#### Scenario: A current accepted question or shared expression applies
- **WHEN** its source bindings and revision match the page's frozen inputs
- **THEN** Story AI may cite its stable ID and use its accepted content in the manuscript
- **AND** the manuscript records that binding for impact and fidelity checks

#### Scenario: An optional asset is absent, stale or unconfirmed
- **WHEN** Story AI plans the page
- **THEN** it ignores that asset and continues from the current usable script
- **AND** it does not adopt the candidate, invent a replacement fact or create a second manuscript path

### Requirement: Page Content Passes A Teaching Quality Gate Before Confirmation
The system SHALL validate required role-specific teaching structure and source fidelity before confirmation, and SHALL distinguish objective missing/invalid content from advisory judgments about teaching style.

#### Scenario: A page asks learners to act
- **WHEN** it contains an audience question, comparison, calculation, prediction or practice action
- **THEN** it identifies the expected response or observable evidence used by the teacher to judge the result
- **AND** that response remains traceable to the page sources

#### Scenario: A page reveals content progressively
- **WHEN** it declares two or more reveal steps
- **THEN** each step names a semantic idea, artifact, operation or conclusion in teaching order
- **AND** `page_teaching_v2` also binds the step to an explicit visible-element state
- **AND** renderer slot identifiers alone cannot satisfy the teaching gate

#### Scenario: Adjacent planned pages form a sequence
- **WHEN** the previous page and next page both exist
- **THEN** the transition states the actual prerequisite, contrast, example, practice or conclusion relationship
- **AND** a generic continuity sentence cannot satisfy the gate

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
- **THEN** before confirmation the draft selects a compatible certified layout or is revised into safe pages, and fails when no faithful representation exists
- **AND** after confirmation a capacity failure returns a diagnostic without changing the confirmed text, layout or page count
- **AND** the renderer does not emit an empty card, shrink below minimum size or crop content

#### Scenario: A source-critical code artifact has no supporting prose
- **WHEN** a source block contains a complete code artifact but no source-backed annotation
- **THEN** the code template uses an optional support slot and gives the artifact the available canvas width
- **AND** V6 does not invent annotation text or combine an unrelated topic merely to fill the slot

### Requirement: Visual AI Has A Controlled Page-Level Degradation
The system SHALL plan `slide_visual_plan_v2` in bounded lesson batches before manuscript confirmation and SHALL distinguish optional visual enrichment from subject-critical artifacts. Structural visuals SHALL NOT require an image-generation provider.

#### Scenario: Decorative visual planning fails
- **WHEN** a page can retain all required source meaning in a declared text-native layout
- **THEN** the unconfirmed page records the degradation and proposed compatible layout
- **AND** the teacher reviews that actual layout before confirming the manuscript
- **AND** the final deck preserves the accepted degradation as `v6_needs_manual_edit`

#### Scenario: A required visual artifact cannot be represented
- **WHEN** source-critical code, formula, table, data or evidence would be lost or no compatible template layout exists
- **THEN** the candidate ends as `v6_failed`
- **AND** it does not publish a prose paraphrase as equivalent

### Requirement: Degraded Visuals Are Repaired Selectively
The system SHALL repair a published `v6_needs_manual_edit` deck from its frozen story, healthy visual decisions, source revision and template contract without restarting the full course build. For `page_teaching_v2`, changes to visible content, assets, relations, states or layouts SHALL create a new unconfirmed manuscript revision. Only an execution retry of the same immutable plan MAY proceed without reconfirmation.

#### Scenario: A teacher retries degraded pages
- **WHEN** one or more published visual decisions are marked degraded
- **THEN** the durable repair task sends only those page IDs to visual AI
- **AND** preserves all healthy story and visual decisions unchanged
- **AND** reports each target page and degradation reason

#### Scenario: Selective visual repair succeeds
- **WHEN** every target page produces a source-bound, template-valid visual decision and the rebuilt Web/PPTX contract passes all gates
- **THEN** for `page_teaching_v2` the corrected pages are saved as an unconfirmed manuscript candidate and final publication waits for that revision's explicit confirmation and export checks
- **AND** the prior published spec remains available in history

#### Scenario: Selective visual repair fails or races a newer publication
- **WHEN** any target remains degraded, source/template inputs drift, rendering fails, or the base representation changes during repair
- **THEN** the repair task fails with a structured `visual_repair` or `publish` reason
- **AND** the previously published V6 revision remains the public version

### Requirement: V6 Publishes One Final Cross-Renderer Contract
The system SHALL compile `slide_deck_v6` with resolved template layout IDs, typed slots, source bindings, speaker notes, visual decisions and renderer adapters for both Web and PPTX. For `page_teaching_v2`, both outputs SHALL consume the same immutable resolved scene containing element geometry, style references, typed relations, asset digests and state-to-physical-page mapping.

#### Scenario: Web preview and PPTX export render one page
- **WHEN** the page is materialized
- **THEN** both renderers consume its resolved layout and slots from `slide_deck_v6`
- **AND** neither renderer re-evaluates story intent or legacy aliases

#### Scenario: Full source is too dense for the canvas
- **WHEN** a teaching unit requires compression for projection
- **THEN** the canvas contains a semantically closed source-faithful expression
- **AND** complete source text and full code remain in speaker notes with block and revision bindings
- **AND** selected on-screen code ranges, quoted source excerpts, formulas, table data and required action steps remain exact and complete in the confirmed presentation
- **AND** explanatory prose may be transformed into validated concise copy or structured visuals without a sole-body verbatim rule
- **AND** an excerpt is explicitly source-ranged and cannot pretend to be the complete source

#### Scenario: A full course contains multiple top-level sections
- **WHEN** the final V6 deck is compiled from the frozen full-course document
- **THEN** one or more `agenda-path` pages are inserted from the ordered source section titles
- **AND** agenda pages bind section IDs without claiming visible `CourseBlock` coverage
- **AND** chapter-only shadow documents with one top-level section do not receive a false course agenda

#### Scenario: Confirmed prose contains semantic paragraphs
- **WHEN** the final output renders multiple paragraphs or list groups selected in the confirmed manuscript
- **THEN** their approved boundaries and complete wording remain visible
- **AND** any necessary shortening or pagination has already been reviewed in the draft, rather than being introduced by the renderer

#### Scenario: A task contains explicit ordered steps
- **WHEN** the source declares two or more ordered actions
- **THEN** the final layout uses the published vertical numbered-sequence composition
- **AND** Web and PPTX preserve one source step per numbered row in source order

#### Scenario: A table selected for the screen exceeds one slide's readable capacity
- **WHEN** wrapped cell height, row count or protected identifiers cannot fit the selected table variant without semantic loss
- **THEN** draft layout binding selects a declared full-width or wide table variant, or paginates complete rows across continuation pages with the header repeated before confirmation
- **AND** a single oversized row is promoted to a source-bound detail expression instead of being clipped
- **AND** no renderer or compiler inserts an ellipsis that was absent from the source
- **AND** every visible identifier, number, formula and code token remains complete; otherwise the candidate fails before publication

### Requirement: Course Agenda Preserves The Sample's Editorial Hierarchy
The system SHALL render the course agenda as a source-bound editorial route rather than a compressed title inventory.

#### Scenario: A course has several top-level chapters
- **WHEN** V6 compiles the full-course agenda
- **THEN** each entry shows a stable chapter number and the complete source chapter title
- **AND** it shows a complete source-derived learning objective or path explanation when one fits the declared agenda geometry
- **AND** a missing description remains empty rather than being invented or copied from the title

#### Scenario: More chapters exist than one agenda page can present readably
- **WHEN** the certified agenda capacity or measured geometry rejects the current set
- **THEN** draft preparation creates ordered `agenda-path` continuation pages before confirmation
- **AND** it does not shrink below the template font floor, truncate a title or description, or force all entries onto one page

### Requirement: Exported Slides Preserve Every Materialized Source Region
The system SHALL verify exported PPTX visibility against the final `slide_deck_v6` regions, not only against the pre-render page model.

#### Scenario: A renderer omits a body or step region
- **WHEN** a materialized source region cannot be found in the corresponding exported slide objects in source order
- **THEN** publication fails with `exported_source_region_missing`
- **AND** speaker-note presence or a passing geometric overflow audit cannot convert the candidate to success

#### Scenario: A renderer omits a page title or table cell
- **WHEN** the final PPTX lacks the complete materialized title or any complete source table cell
- **THEN** publication fails with a page- and region-scoped export diagnostic
- **AND** the last published deck remains available

### Requirement: Code Pages Preserve Source And Add Teaching-Readable Formatting
The system SHALL preserve exact selected source code lines, indentation and blank lines while adding reading aids shared by Web and PPTX. Source excerpts SHALL retain explicit original line ranges; omitted context SHALL NOT change the teaching meaning or be presented as a complete program.

#### Scenario: Fenced code spans several pages
- **WHEN** a selected source code range exceeds one declared code slot during draft preparation
- **THEN** every page records the source language, original start line, end line and continuation position
- **AND** both renderers show a compact language/continuation header and a separate line-number gutter
- **AND** these aids do not alter the source code used by fidelity checks

#### Scenario: A declaration group fits on one page
- **WHEN** adjacent interface members, a method signature and opening body, or a comment and its declaration fit within one declared code page
- **THEN** pagination keeps that group together
- **AND** it does not leave a declaration, opening brace or isolated comment as an avoidable orphan

#### Scenario: A code group is genuinely longer than one page
- **WHEN** no complete-page allocation can retain the whole group
- **THEN** V6 splits at the least harmful complete statement boundary
- **AND** no code byte, blank source line or indentation is removed
- **AND** audience-facing pages do not expose generic internal labels such as `CODE` or `SOURCE`

### Requirement: V6 Applies Fidelity And Render Gates Before Atomic Publication
The system SHALL publish only after course coverage, order, fact traceability, subject artifacts, teaching intent, template capacity, render integrity and export checks pass.

#### Scenario: A final page contains an untraceable fact
- **WHEN** a number, formula, identifier or factual assertion lacks a source binding
- **THEN** publication fails with a page-scoped diagnostic

#### Scenario: A final page has multiple incompatible teaching jobs
- **WHEN** its visible regions lack one dominant instructional task or reading order
- **THEN** draft preparation reports the issue and may revise the page; a confirmed candidate fails with `presentation_grammar_mismatch` without renderer-driven repagination

#### Scenario: All hard gates pass with no degradation
- **WHEN** source and template remain frozen and both renderers pass
- **THEN** the version publishes atomically as `v6_ready`

#### Scenario: Visible source semantics are truncated or synthesized
- **WHEN** visible content differs from the confirmed manuscript, selected exact artifacts differ from their frozen source ranges, required meaning is missing, or the compiler introduces an unapproved ellipsis
- **THEN** publication fails with a structured fidelity diagnostic
- **AND** passing geometric overflow checks cannot convert the candidate to success

#### Scenario: A planned page has no visible title
- **WHEN** a story page title is empty or whitespace-only
- **THEN** validation fails with `story_title_missing`
- **AND** the untitled page is not rendered or published

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

#### Scenario: The designated text model is unavailable
- **WHEN** the private `qwen3.8-27b` route fails after the bounded retry policy
- **THEN** the task reports provider failure and preserves accepted checkpoints and the last good deck
- **AND** no ModelScope, DeepSeek or other external text model is used as primary or fallback

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

### Requirement: Three Stage Content Is Typed And Reviewable
The system SHALL use `page_teaching_v2` inside `ppt_manuscript_v1` for the enhanced workflow and SHALL represent teaching roles independently from expression structures and visual themes.

#### Scenario: A comparison is planned
- **WHEN** the page compares two or more subjects
- **THEN** it declares stable subjects, common dimensions, complete subject-dimension cells and source-bound element references
- **AND** missing cells, reversed bindings or incompatible comparison conditions fail validation
- **AND** two arbitrary paragraphs placed side by side do not satisfy the comparison contract

#### Scenario: A relation diagram is planned
- **WHEN** its meaning is sequence, causality or hierarchy
- **THEN** it declares typed relations, source and target IDs, direction and relevant conditions
- **AND** the relation type is not inferred from node array order
- **AND** a causal claim requires evidence for the causal relationship rather than co-occurrence alone

#### Scenario: A text-light page is valid
- **WHEN** the source-bound teaching meaning is fully conveyed by a diagram, formula or question
- **THEN** no minimum prose length forces additional text
- **AND** a question-led page need not expose its answer as a title

#### Scenario: Source data is shown as horizontal bars
- **WHEN** a page uses the initial `chart` expression with 2-6 values
- **THEN** it binds every category and exact nonnegative decimal value to source elements and keeps an exact common unit visible
- **AND** all reveal states share one zero baseline and one scale calculated from the full set of values
- **AND** export preserves the value text and bar proportions as editable native text and shapes
- **AND** negative values, mixed units and unsupported numeric notation fail before confirmation rather than being silently converted

#### Scenario: A source contains an intentionally incomplete matrix counterexample
- **WHEN** the selected source matrix has unequal row lengths
- **THEN** its display preserves every supplied entry and leaves absent entries empty without inventing zeros
- **AND** the original source syntax and character range remain unchanged in the manuscript

### Requirement: Static Reveal States Are Compiled Before Confirmation
The system SHALL represent progressive teaching as explicit ordered element states and SHALL select physical slides through an explicit complete, question-answer or justified key-step presentation policy before exporting static consecutive slides without enabling frozen animation features.

#### Scenario: A question precedes its answer
- **WHEN** a logical page defines a question state followed by an answer state
- **THEN** each state names its visible and emphasized element IDs
- **AND** draft review shows the actual physical slide sequence and count before confirmation
- **AND** the question slide does not expose the answer through visible objects

#### Scenario: A diagram is expanded in stages
- **WHEN** a later state adds nodes and relations
- **THEN** output checks validate exactly the expected elements and relations for each state
- **AND** existing visible elements retain their declared positions unless an explicit state transition changes them

#### Scenario: Draft narration continues without changing the canvas
- **WHEN** consecutive selected steps in any new draft entry, including formal teaching payloads have identical visible elements and no distinct emphasis
- **THEN** draft compilation merges those steps into one physical state and concatenates every narration note in its original order
- **AND** a declared reveal step without a note or an answer appearing before its question still fails validation
- **AND** the resulting page count is shown before confirmation and this normalization never rewrites confirmed states
- **AND** source note coverage is reconciled through logical-page ownership without falsely counting repeated state pages as missing or duplicate ownership

### Requirement: Final Generation Performs No Content Or Visual Planning
The system SHALL generate the final deck only from the confirmed manuscript and its frozen template, scene, assets, font policy and tool versions.

#### Scenario: A confirmed manuscript is exported twice
- **WHEN** the frozen inputs and compiler/render versions are unchanged
- **THEN** semantic page objects, text, relations, data, physical order and note bindings are identical
- **AND** no text or visual planning model is invoked
- **AND** file timestamps or package metadata do not count as semantic differences

#### Scenario: Export discovers a capacity error
- **WHEN** text cannot fit at the template font floor
- **THEN** export fails with the page and slot IDs
- **AND** it does not silently shorten, repaginate, replace a layout or re-prompt a model
- **AND** a content-changing repair returns to an unconfirmed draft

### Requirement: Export Preserves Typed Relations And Asset Identity
The system SHALL validate actual exported graphical relationships and asset bindings against the resolved page scene in addition to text and object bounds.

#### Scenario: A branching graph is exported through a personal template
- **WHEN** the source scene contains A-to-B and A-to-C relations without B-to-C
- **THEN** both preview and PPTX display exactly those declared relationships and directions
- **AND** rendering A, B and C as an adjacent chain fails the relation audit

#### Scenario: A comparison matrix is exported
- **WHEN** the renderer produces table cells or paired graphical groups
- **THEN** subject and dimension identities remain aligned in both outputs
- **AND** a cell swap fails even if every word is present somewhere on the slide

#### Scenario: An accepted shared visual is used
- **WHEN** the manuscript binds an immutable adopted asset or diagram specification
- **THEN** the actual output contains that asset or its verified structural rendering
- **AND** merely storing its ID in metadata is insufficient
- **AND** stale or unadopted versions are not substituted

### Requirement: Quality And Tool Versions Govern Reuse
The system SHALL include source, manuscript, template, font, compiler, renderer and quality-policy versions in derived-plan and artifact reuse checks.

#### Scenario: Fonts or renderer version changes
- **WHEN** a cached artifact was built using a different declared font bundle or renderer
- **THEN** its render acceptance is not reused blindly
- **AND** local checks are rerun before final delivery without unnecessarily regenerating content with a model

#### Scenario: An output contains a vector formula asset
- **WHEN** symbol-level native editing is unsupported for that formula
- **THEN** its editability is disclosed accurately and original formula source is retained
- **AND** an image or vector asset is not described as symbol-level editable

### Requirement: Release Evidence Covers Teaching And Execution Separately
The system SHALL validate the enhanced contract using real private-model outputs and real rendered decks for mathematics/data, programming/engineering and humanities/social-science teaching inputs.

#### Scenario: A release candidate is evaluated
- **WHEN** contract tests and export checks pass
- **THEN** representative teacher-path and classroom-readability review is still recorded separately
- **AND** every physical page has source, relation, layout and export evidence
- **AND** a passing mock, screenshot, average score or template-count metric does not replace the missing evidence

#### Scenario: The enhanced workflow is disabled
- **WHEN** its independent new-build feature switch is turned off
- **THEN** existing manuscripts and artifacts remain readable and exportable under their versioned contracts
- **AND** running tasks are not silently rerouted to a different content policy or engine

### Requirement: Final scene execution checks use the confirmed contract

The system SHALL compile confirmed teaching scenes without resuming content planning and SHALL audit their fixed geometry and text using the declared execution contract.

#### Scenario: Confirmed teaching scenes start a new final generation task
- **WHEN** a teacher generates a new PPT from a confirmed `page_teaching_v2` manuscript
- **THEN** the new task reads the confirmed manuscript without requiring or cloning its content-planning checkpoint
- **AND** only an explicit resume reuses a final-generation checkpoint with matching manuscript, source, template and tool identities
- **AND** the final generation does not invoke a content or visual model

#### Scenario: Fixed text lines and inline mathematics are verified
- **WHEN** a manuscript includes supported delimited mathematics inside prose or an exact source quotation
- **THEN** notation is projected and measured before confirmation while the original quotation and source range remain unchanged
- **AND** unsupported notation fails the draft instead of remaining as visible LaTeX commands
- **AND** exported fixed-line text is measured with the declared font and written line spacing, checking both horizontal and vertical overflow without inventing automatic wrapping
- **AND** PDF glyph aliases are accepted only for verified identical pinned-font glyphs while OOXML retains exact code-point and order checks

### Requirement: Lesson Pacing Governs Draft Production
The system SHALL plan related source blocks around one learner task, allow contiguous cross-unit source groups with preserved source ownership and first-use order, and record an explicit physical-page budget with its teaching rationale before detailed page generation.

#### Scenario: Formal lesson timing is available or unknown
- **WHEN** the content planner receives the formal teaching plan
- **THEN** its narrative duration equals the supplied lesson duration
- **AND** missing timing stays unknown rather than becoming an invented standard lesson length
- **AND** contiguous numbered source ranges compile into exact source identities, rejecting gaps, reversed ranges and incomplete first-use coverage

#### Scenario: Related explanation and example belong to different source units
- **WHEN** one page goal needs both adjacent sources
- **THEN** planning may use both while retaining each complete source and exact citations in notes
- **AND** the first source unit remains the compatibility navigation anchor without becoming the only permitted source owner

#### Scenario: Local capacity repair would expand the lesson
- **WHEN** one task requires additional content or reveal pages
- **THEN** it first reduces optional screen exposition and counts all proposed physical pages against the remaining lesson budget
- **AND** a split identifies the distinct teaching need rather than expanding without bound

#### Scenario: Repairing one field must preserve healthy page content
- **WHEN** a model returns a field patch for a failing single page or subpage
- **THEN** omitted fields and other subpages remain unchanged, and the complete merged page is validated again
- **AND** unknown fields and expression-kind changes through a partial patch are rejected
- **AND** original narration IDs remain available for checkpoint selection without concatenating separate notes into an oversized note

#### Scenario: An ordinary page has several narration steps
- **WHEN** its presentation mode is complete
- **THEN** only its complete canvas is exported and every narration note is retained
- **AND** question-answer pages retain an answer-free problem view and a complete answer view
- **AND** key-step pages require ordered checkpoint IDs and teaching reasons and retain all required elements and question context

#### Scenario: A manuscript exceeds its budget or repeats a canvas
- **WHEN** whole-lesson review detects excess physical pages or identical adjacent exported canvases
- **THEN** the draft contains blocking page-scoped or lesson-scoped diagnostics and is not confirmable
- **AND** saving a reviewable draft preserves the last confirmed and published versions
- **AND** editing the budget or display policy recalculates diagnostics and invalidates confirmation without a model call

#### Scenario: A historical confirmed manuscript has no pacing policy
- **WHEN** it is read or exported
- **THEN** its historical states and serialized fields are not silently normalized into the new policy
- **AND** explicit draft editing is required to change its page sequence
