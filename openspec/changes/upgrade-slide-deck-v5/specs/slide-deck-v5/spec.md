## ADDED Requirements

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

### Requirement: AI Refines the Compact Source-Bound Story

When an AI provider is configured and the explicit planner kill switch is not
disabled, the system SHALL refine the deterministic V5 compact story with
chapter-scoped, source-bound directives before page allocation.

#### Scenario: A configured provider refines a multi-chapter course
- **WHEN** V5 has already selected complete semantic groups
- **THEN** the planner receives bounded chapter requests instead of one full-deck
  rewrite request
- **AND** it may select only supplied beat IDs, headline fragment IDs, and
  capacity-compatible layout IDs
- **AND** compilation preserves the accepted AI decisions through final
  materialization

#### Scenario: AI returns an invalid or failed refinement
- **WHEN** the configured provider times out, invents an ID, changes source
  claims, or returns an invalid contract
- **THEN** the system retains the deterministic source-bound story
- **AND** the V5 publication gate reports the failed AI planning stage instead
  of presenting the fallback as an AI-quality result

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
- **AND** neither renderer shrinks body text below 14 pt or titles below 24 pt

#### Scenario: Visible claim promises more members than the page contains
- **WHEN** the title or body promises `N` classes, steps, parts, or alternatives
  but fewer than `N` list members are visible
- **THEN** publication is blocked with
  `enumeration_cardinality_mismatch`
- **AND** the incomplete page is not treated as a quality-equivalent fallback
