# teacher-script-multimodal-expressions Specification

## Purpose
让图解和 AI 生成插图以绑定当前讲义修订的候选形式生成、审阅、采用和回退，使教师能够补充视觉表达，同时不让失败媒体、过期来源或模型输出污染正式讲义与下游课件。

## Requirements

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

### Requirement: Teacher acceptance controls downstream reuse

The system SHALL add an expression to the block's shared `RepresentationSet` only after teacher acceptance. An accepted diagram or illustration SHALL render directly in the reading flow immediately after its source-bound script block, without being hidden behind a separate visual-expression heading or disclosure control. Candidate, stale, loading, and failure states SHALL remain visually distinct from accepted inline content. Rejection and regeneration SHALL archive the superseded candidate without modifying the script.

#### Scenario: Teacher accepts one expression

- **WHEN** a teacher accepts a current, complete visual candidate
- **THEN** it becomes an accepted member of the block's `RepresentationSet`
- **AND** the same representation ID is available to script, PPT, and learner consumers
- **AND** the teacher script displays it inline immediately after the bound block content
- **AND** no extra disclosure action is required to see it

#### Scenario: Teacher rejects one expression

- **WHEN** a teacher rejects a candidate
- **THEN** it becomes archived
- **AND** it is absent from the shared representation set

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

### Requirement: Visual failures never block core teaching artifacts

The system SHALL keep the current script and last accepted representation readable when diagram or image generation fails.

#### Scenario: A media provider fails

- **WHEN** visual generation returns a provider or validation failure
- **THEN** the failure is scoped to that block's visual workspace
- **AND** script reading, editing, and downstream artifact workflows remain available

### Requirement: Diagram generation is model-planned and renderer-bounded

The system SHALL ask the configured private text model to plan the concepts, formulas, and relationships of a requested diagram as bounded JSON. The backend SHALL supply all source bindings, validate the resulting `diagram_spec_v1`, and fall back to deterministic source compilation when model planning or validation fails. The renderer SHALL NOT execute model-returned Mermaid, JavaScript, or Python.

#### Scenario: Model returns a valid relationship plan

- **WHEN** the teacher requests a diagram for a current block
- **THEN** the resulting candidate preserves the model-planned source-bound nodes and relationships in a valid `diagram_spec_v1`

#### Scenario: Model planning fails

- **WHEN** the model is unavailable or returns invalid diagram JSON after bounded repair
- **THEN** the system publishes a deterministic diagram candidate from the same source block
- **AND** the script remains readable and unchanged
