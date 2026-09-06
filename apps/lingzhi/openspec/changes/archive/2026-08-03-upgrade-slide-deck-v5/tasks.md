## 1. Contracts and Specification

- [x] 1.1 Define the V5 deck-level narrative, title, slot-binding, final-layout,
      rendering, and quality contracts
- [x] 1.2 Add `DeckOutlineV5`, `FinalPageContractV5`, and V5 build signature
- [x] 1.3 Add V5 schema compatibility to representation storage and frontend

## 2. Test-Driven V5 Foundation

- [x] 2.1 Add failing tests for deterministic 3-6 section agenda extraction
- [x] 2.2 Add failing tests for two-level headings and explicit-title priority
- [x] 2.3 Add failing tests rejecting one-group two-column layouts
- [x] 2.4 Add failing tests reflowing visual layouts after visual rejection
- [x] 2.5 Add failing tests proving web and PPT use the same resolved layout

## 3. Implement the First V5 Vertical Slice

- [x] 3.1 Compile `DeckOutlineV5` from the communication brief and chapter story
- [x] 3.2 Materialize minimal cover, linear agenda, required chapter entry/recap,
      and course synthesis pages
- [x] 3.3 Normalize semantic groups and bind layout slots
- [x] 3.4 Resolve final layout/composition after visual resolution
- [x] 3.5 Update Vue and PPT renderers to consume resolved fields

## 4. Presentation-Native Layouts

- [x] 4.1 Implement minimal cover and linear agenda without UI-card styling
- [x] 4.2 Implement classification, comparison, process, and formula layouts
- [x] 4.3 Implement worked-example, practice-feedback, recap, and synthesis layouts
- [x] 4.4 Enforce title and density budgets without shrinking below minimums

## 5. Quality and Rollout

- [x] 5.1 Add slot occupancy, empty-region, title duplication, and orphan-formula
      publication gates
- [x] 5.2 Add browser/PPT contract parity tests and rendered-slide review fixtures
- [x] 5.3 Evaluate representative quantitative, programming, humanities, business,
      and medical/structural courses
- [x] 5.4 Enable `slide_deck_v5` as the target schema with explicit V4 fallback
- [x] 5.5 Run backend, frontend, build, OpenSpec, and real-course verification

## 6. Production AI Refinement

- [x] 6.1 Enable planning automatically when a provider is configured while
      retaining an explicit kill switch
- [x] 6.2 Compact the deterministic story before AI refinement
- [x] 6.3 Replace full-story rewrites with bounded chapter directive requests
- [x] 6.4 Validate headline and layout IDs against source and capacity contracts
- [x] 6.5 Preserve accepted AI decisions through idempotent V5 compilation
- [x] 6.6 Report configured AI refinement failures without granting an
      AI-quality pass

## 7. Semantic Closure and Audience Titles

- [x] 7.1 Treat counted enumerations as indivisible source-bound bundles
- [x] 7.2 Prefer required members over optional background during capacity fitting
- [x] 7.3 Replace numbered or topic-only source headings with supported visible
      claims while preserving the two-level eyebrow/title contract
- [x] 7.4 Block publication for enumeration cardinality mismatches and numbered
      source headings used as content-page titles
- [x] 7.5 Add thermodynamics regression coverage for the three-system
      classification failure

## 8. V5.5 Publication and Grounded Copy Hardening

- [x] 8.1 Reconcile durable terminal completion to the published V5 registry and
      clear stale intermediate slides atomically
- [x] 8.2 Aggregate final page-level blockers into the deck publication gate
- [x] 8.3 Allow source-faithful audience titles, summaries, and instructional
      scaffolds with explicit supporting-fragment provenance
- [x] 8.4 Reject unsupported factual tokens and preserve the exact primary claim
- [x] 8.5 Require local semantic evidence for rule-based diagrams and prefer
      `none` for ambiguous or template-shaped visual candidates
- [x] 8.6 Align browser, PPTX, and layout-contract typography floors to 35 pt
      titles and 16 pt audience body copy

## 9. Long-Course Reliability

- [x] 9.1 Isolate AI story-planning failures per chapter and preserve valid
      chapter refinements
- [x] 9.2 Persist chapter-level planning diagnostics for timeout and invalid
      response failures
- [x] 9.3 Skip unsafe single-shot AI visual planning for long decks and use the
      deterministic evidence-first visual policy
- [x] 9.4 Treat AI availability as a warning while retaining all deterministic
      publication gates
- [x] 9.5 Remove superseded V4 capacity findings after V5 final-contract
      resolution
- [x] 9.6 Verify the 8-chapter, 74-source-block thermodynamics course with both
      AI planning stages unavailable
