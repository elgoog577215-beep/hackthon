# teacher-script-multimodal-expressions Specification

## ADDED Requirements

### Requirement: Visual expressions are source-bound candidates

The system SHALL create diagram, image, and animation expressions as `TeachingRepresentation` candidates bound to the current teacher-script revision, section, block, and content fingerprint. It SHALL NOT embed candidate media into the formal script Markdown.

#### Scenario: Teacher creates a diagram candidate

- **WHEN** the teacher requests a diagram for a current structured script block
- **THEN** the system returns a valid `diagram_spec_v1` candidate with exact source bindings
- **AND** the formal script remains unchanged

#### Scenario: Script changes after candidate creation

- **WHEN** the current script revision no longer matches a candidate or accepted expression
- **THEN** the system marks that expression stale
- **AND** prevents the stale candidate from being accepted

### Requirement: Teacher acceptance controls downstream reuse

The system SHALL add an expression to the block's shared `RepresentationSet` only after teacher acceptance. Rejection and regeneration SHALL archive the superseded candidate without modifying the script.

#### Scenario: Teacher accepts one expression

- **WHEN** a teacher accepts a current, complete visual candidate
- **THEN** it becomes an accepted member of the block's `RepresentationSet`
- **AND** the same representation ID is available to script, PPT, and learner consumers

#### Scenario: Teacher rejects one expression

- **WHEN** a teacher rejects a candidate
- **THEN** it becomes archived
- **AND** it is absent from the shared representation set

### Requirement: Image generation fails honestly

The system SHALL persist an image prompt before provider execution. When no provider is configured or execution fails, it SHALL return an explicit retryable provider state and SHALL NOT create or accept a placeholder image.

#### Scenario: Image provider is not configured

- **WHEN** the teacher requests an illustration without a configured image provider
- **THEN** the system returns `provider_unavailable` with the saved prompt and retry action
- **AND** no asset ID or synthetic image is reported

### Requirement: Animation is an inspectable scene specification

The system SHALL represent animation as `scene_spec_v1` with bounded objects, actions, timing, focus, checkpoints, and a static fallback. The player SHALL support play, pause, previous step, next step, and replay without executing generated JavaScript.

#### Scenario: Teacher reviews an animation candidate

- **WHEN** an animation candidate is shown
- **THEN** the teacher can pause it and move between checkpoints
- **AND** reduced-motion preferences disable smooth automatic transitions

### Requirement: Visual failures never block core teaching artifacts

The system SHALL keep the current script and last accepted representation readable when diagram, image, or animation generation fails.

#### Scenario: A media provider fails

- **WHEN** visual generation returns a provider or validation failure
- **THEN** the failure is scoped to that block's visual workspace
- **AND** script reading, editing, and downstream artifact workflows remain available
