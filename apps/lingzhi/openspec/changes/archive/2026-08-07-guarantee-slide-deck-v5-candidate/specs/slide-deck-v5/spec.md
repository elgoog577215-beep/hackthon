## ADDED Requirements

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

