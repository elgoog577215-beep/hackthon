## ADDED Requirements

### Requirement: Courseware opens in a dedicated workbench
The learning page MUST expose a courseware action adjacent to the existing AI teacher action. It MUST open `/course/:courseId/deck` or `/course/:courseId/deck/:deckId` as a full workbench using the approved top toolbar, hierarchy bar, large left preview and fixed right AI panel structure.

#### Scenario: A user opens courseware from the current course
- **WHEN** the user activates the courseware action
- **THEN** the application MUST open the dedicated workbench
- **AND** MUST NOT open a modal, CourseTaskCenter, or Markdown/JSON export flow

### Requirement: Deck drafts remain independent from course text
The system MUST store deck drafts outside CourseDocument, bind them to an immutable source snapshot, and preserve the original course when a deck is generated or edited.

#### Scenario: A user applies a slide edit
- **WHEN** the user applies an AI proposal to a slide
- **THEN** the system MUST append a deck revision
- **AND** MUST NOT mutate the source course or its active course version

### Requirement: Workbench state survives refresh
The system MUST persist the deck manifest, generation working snapshot, active immutable revision, quality summary and artifact status so the workbench can recover after a browser refresh.

#### Scenario: The page reloads during generation
- **WHEN** the workbench reloads while a generation is active
- **THEN** it MUST restore the current outline and generated slides from the working snapshot
- **AND** MUST resume events after the last acknowledged event sequence without duplicating slides

### Requirement: AI edits are scoped, explicit and reversible
The preview MUST report the selected slide to the workbench. The AI panel MUST show its target, create a proposal against the active revision, display impact and diff, and require user apply before writing a new revision. Applied changes MUST be restorable.

#### Scenario: A selected slide receives a concise-edit request
- **WHEN** slide 2 is selected and the user asks to simplify the current page
- **THEN** the proposal MUST be limited to slide 2 allowed fields
- **AND** MUST NOT modify any other slide or source reference
- **AND** apply MUST create a child revision that can be undone by a new restore revision

#### Scenario: A proposal is based on an old revision
- **WHEN** another command has already advanced the active revision
- **THEN** applying the old proposal MUST fail with `409 stale_proposal`
- **AND** MUST leave the active deck unchanged

### Requirement: Preview communication is bounded
The preview and workbench MUST communicate through a versioned message channel inside an opaque sandbox and validate source window, expected sandbox origin, deck id, revision id and revision checksum before accepting selection or render measurements. A measurement MUST explicitly report slide count, overflow and collision for that revision.

#### Scenario: An unrelated frame posts a slide selection
- **WHEN** a message does not match the expected source, sandbox origin, channel, deck, revision or checksum
- **THEN** the workbench MUST ignore it

### Requirement: Formal download follows finalize
The workbench MUST keep download disabled until the active revision has a non-stale artifact receipt produced by a successful finalize. Applying a later revision MUST make the previous artifact stale.

#### Scenario: The user edits an exported deck
- **WHEN** a new deck revision becomes active after export
- **THEN** the previous artifact MUST remain auditable
- **AND** formal download MUST remain disabled until the new revision is finalized

### Requirement: Narrow screens use one active surface
At narrow widths the workbench MUST provide a Preview/AI switch and MUST NOT require both panes to remain visible.

#### Scenario: A user opens the workbench on a narrow viewport
- **WHEN** the viewport cannot support the desktop split
- **THEN** one surface MUST remain usable at a time
- **AND** the current deck and selected slide state MUST survive switching surfaces
