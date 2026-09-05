## MODIFIED Requirements

### Requirement: Visual expressions are source-bound candidates

The system SHALL expose diagrams and AI-generated illustrations as the active teacher-script visual expressions. Each candidate SHALL bind to the current script revision, section, block, and content fingerprint and SHALL NOT modify formal script Markdown. Animation code and historical specifications MAY remain stored, but animation SHALL be unavailable to recommendations, ordinary generation requests, teacher-script views, candidate resolution, and accepted downstream consumer projections while its runtime flag is disabled.

#### Scenario: Teacher creates a diagram candidate

- **WHEN** the teacher requests a diagram for a current structured script block
- **THEN** the system returns a valid `diagram_spec_v1` candidate with exact source bindings
- **AND** the formal script remains unchanged

#### Scenario: Script changes after candidate creation

- **WHEN** the current script revision no longer matches a candidate or accepted expression
- **THEN** the system marks that expression stale
- **AND** prevents the stale candidate from being accepted

#### Scenario: Teacher opens a script block visual workspace

- **WHEN** teacher-script animation is disabled
- **THEN** the workspace offers diagram and AI illustration generation only
- **AND** no animation recommendation or historical animation is returned into the active view

#### Scenario: A client directly requests animation

- **WHEN** the animation runtime flag is disabled
- **THEN** the API rejects the request without calling the text model or publishing a candidate

### Requirement: Image generation fails honestly

The system SHALL create only AI-generated illustration candidates for teacher-script images and SHALL label every candidate and asset as AI-generated. An illustration MAY provide explanation, visual association, humor, or editorial rhythm, but SHALL NOT be described as a source photograph, archival record, or historical evidence. The system SHALL persist the prompt before provider execution. When no provider is configured or execution fails, it SHALL return an explicit retryable provider state and SHALL NOT create or accept a placeholder image.

#### Scenario: Teacher generates a historical-scene illustration

- **WHEN** the current block benefits from an imagined historical scene
- **THEN** the candidate is identified as an AI-generated illustration
- **AND** it is not presented as a historical source image

#### Scenario: Image provider is not configured

- **WHEN** the teacher requests an AI illustration without a configured image provider
- **THEN** the system returns `provider_unavailable` with the saved prompt and retry action
- **AND** no asset ID or synthetic placeholder is reported

## ADDED Requirements

### Requirement: Diagram generation is model-planned and renderer-bounded

The system SHALL ask the configured private text model to plan the concepts, formulas, and relationships of a requested diagram as bounded JSON. The backend SHALL supply all source bindings, validate the resulting `diagram_spec_v1`, and fall back to deterministic source compilation when model planning or validation fails. The renderer SHALL NOT execute model-returned Mermaid, JavaScript, or Python.

#### Scenario: Model returns a valid relationship plan

- **WHEN** the teacher requests a diagram for a current block
- **THEN** the resulting candidate preserves the model-planned source-bound nodes and relationships in a valid `diagram_spec_v1`

#### Scenario: Model planning fails

- **WHEN** the model is unavailable or returns invalid diagram JSON after bounded repair
- **THEN** the system publishes a deterministic diagram candidate from the same source block
- **AND** the script remains readable and unchanged

## REMOVED Requirements

### Requirement: Animation is a continuous inspectable teaching scene

The system SHALL use the configured text model to plan new animations as `scene_spec_v2` with bounded SVG primitives, continuous motion paths, rotation, tracing, timing, checkpoints, and a static fallback. A `scene_spec_v2` SHALL contain actual motion, rotation, or path tracing; a physical-motion scene SHALL contain continuous movement and SHALL NOT pass validation as text-card reveals only. The player SHALL support play, pause, previous step, next step, and replay without executing generated JavaScript or Python. Existing `scene_spec_v1` expressions SHALL remain readable as legacy step diagrams.

#### Scenario: Teacher reviews an animation candidate

- **WHEN** an animation candidate is shown
- **THEN** the teacher can pause it and move between checkpoints
- **AND** reduced-motion preferences disable smooth automatic transitions

#### Scenario: Teacher requests a ball rolling down a slope

- **WHEN** the current script describes a ball rolling down an inclined plane
- **THEN** the generated scene contains a slope primitive and a ball primitive
- **AND** the ball continuously moves along the slope with accelerating easing and visible rotation
- **AND** the candidate remains a validated scene specification rather than executable model code

#### Scenario: Model returns only a playing diagram

- **WHEN** an AI-planned scene contains only text-card reveal or focus actions
- **THEN** validation rejects that result as an animation
- **AND** no candidate is published unless an explicit validated motion template is available
