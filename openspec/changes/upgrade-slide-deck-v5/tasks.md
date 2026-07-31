## 1. Contracts and Specification

- [x] 1.1 Define the V5 deck-level narrative, title, slot-binding, final-layout,
      rendering, and quality contracts
- [ ] 1.2 Add `DeckOutlineV5`, `FinalPageContractV5`, and V5 build signature
- [ ] 1.3 Add V5 schema compatibility to representation storage and frontend

## 2. Test-Driven V5 Foundation

- [ ] 2.1 Add failing tests for deterministic 3-6 section agenda extraction
- [ ] 2.2 Add failing tests for two-level headings and explicit-title priority
- [ ] 2.3 Add failing tests rejecting one-group two-column layouts
- [ ] 2.4 Add failing tests reflowing visual layouts after visual rejection
- [ ] 2.5 Add failing tests proving web and PPT use the same resolved layout

## 3. Implement the First V5 Vertical Slice

- [ ] 3.1 Compile `DeckOutlineV5` from the communication brief and chapter story
- [ ] 3.2 Materialize minimal cover, linear agenda, required chapter entry/recap,
      and course synthesis pages
- [ ] 3.3 Normalize semantic groups and bind layout slots
- [ ] 3.4 Resolve final layout/composition after visual resolution
- [ ] 3.5 Update Vue and PPT renderers to consume resolved fields

## 4. Presentation-Native Layouts

- [ ] 4.1 Implement minimal cover and linear agenda without UI-card styling
- [ ] 4.2 Implement classification, comparison, process, and formula layouts
- [ ] 4.3 Implement worked-example, practice-feedback, recap, and synthesis layouts
- [ ] 4.4 Enforce title and density budgets without shrinking below minimums

## 5. Quality and Rollout

- [ ] 5.1 Add slot occupancy, empty-region, title duplication, and orphan-formula
      publication gates
- [ ] 5.2 Add browser/PPT contract parity tests and rendered-slide review fixtures
- [ ] 5.3 Evaluate representative quantitative, programming, humanities, business,
      and medical/structural courses
- [ ] 5.4 Enable `slide_deck_v5` as the target schema with explicit V4 fallback
- [ ] 5.5 Run backend, frontend, build, OpenSpec, and real-course verification

