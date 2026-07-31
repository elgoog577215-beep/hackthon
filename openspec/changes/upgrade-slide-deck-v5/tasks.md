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
