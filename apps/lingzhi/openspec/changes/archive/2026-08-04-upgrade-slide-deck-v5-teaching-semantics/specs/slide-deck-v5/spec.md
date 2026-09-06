## ADDED Requirements

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
