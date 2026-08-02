## ADDED Requirements

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
