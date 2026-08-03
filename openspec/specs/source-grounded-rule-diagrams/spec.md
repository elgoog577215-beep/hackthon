# source-grounded-rule-diagrams Specification

## Purpose
TBD - created by archiving change integrate-source-grounded-rule-diagrams. Update Purpose after archive.
## Requirements
### Requirement: Source Fragmentation Preserves Diagram Semantics
The system SHALL preserve fenced-block language and SHALL classify Mermaid fences as diagram fragments instead of generic code fragments.

#### Scenario: Mermaid fence becomes a diagram fragment
- **WHEN** course source contains a fenced block whose language is `mermaid`
- **THEN** the fragment manifest records a diagram fragment and does not expose the fence as a code example

#### Scenario: Non-Mermaid code remains code
- **WHEN** course source contains a fenced block with another language
- **THEN** the fragment manifest records a code fragment and preserves its program text

### Requirement: Rule Diagrams Are Typed, Bounded, and Source-Grounded
The system SHALL accept only allow-listed rule-diagram templates whose visible labels and relations are bound to declared source fragments and remain within configured capacity limits.

#### Scenario: Supported Mermaid flow compiles
- **WHEN** a Mermaid diagram uses the supported graph or flowchart subset and every label is attributable to the source fragment
- **THEN** the system compiles it into a validated rule-diagram program with bounded nodes and edges

#### Scenario: Unsupported diagram fails closed
- **WHEN** a diagram contains unsupported syntax, exceeds capacity, or lacks source grounding
- **THEN** the visual decision becomes `none` and the slide uses a text-only layout without a placeholder

#### Scenario: Language model proposes coordinates or drawing code
- **WHEN** visual-planning output contains arbitrary coordinates, SVG, HTML, Mermaid, or executable drawing instructions
- **THEN** contract validation rejects those fields and no visual is rendered from them

### Requirement: Rule Diagrams Work Across Courses Through Generic Templates
The system SHALL use a course-agnostic rule-diagram core and SHALL constrain optional subject behavior to declarative template packs that cannot bypass core validation.

#### Scenario: Unknown course has no template pack
- **WHEN** a course subject has no registered domain pack
- **THEN** the planner uses eligible generic templates or selects `none`

#### Scenario: Domain pack proposes an invalid diagram
- **WHEN** a domain pack suggestion violates source binding or capacity limits
- **THEN** the generic validator rejects it and the slide falls back to text

### Requirement: Semantic Teaching Units Drive Pagination
The system SHALL keep headings, explanatory prose, formulas, diagrams, and interpretations together when they form one teaching unit and fit within page capacity.

#### Scenario: Explanation immediately precedes a formula
- **WHEN** an explanation, formula, and interpretation fit on one slide
- **THEN** they are allocated to the same slide in source order

#### Scenario: Teaching unit exceeds capacity
- **WHEN** a semantic teaching unit cannot fit on one slide
- **THEN** the allocator splits at a semantic boundary and derives each continuation title from its local source fragments

#### Scenario: Authoring-only visual marker precedes a diagram
- **WHEN** a heading only instructs the authoring system to create a visualization
- **THEN** that marker is not emitted as learner-visible slide content

### Requirement: Web and PPT Share One Rule-Diagram Contract
The system SHALL render a validated rule-diagram program through deterministic web and PPT adapters without converting it into a raster image.

#### Scenario: Rule diagram appears in web preview
- **WHEN** a slide has a validated rule-diagram anchor
- **THEN** the web preview renders its nodes, edges, and labels as accessible SVG

#### Scenario: Rule diagram is exported to PPT
- **WHEN** the same slide is exported
- **THEN** the PPT contains editable native shapes and connectors derived from the same program

### Requirement: Uncertain Visuals Degrade to Text
The system SHALL treat `none` as a successful visual decision and SHALL prefer text-only content whenever visual quality cannot be guaranteed.

#### Scenario: Raster provider is configured but generation is not enabled
- **WHEN** a deployment has raster provider credentials but the explicit illustration feature flag is disabled
- **THEN** no generated illustration request is made and the slide uses a text-only or validated rule-diagram layout

#### Scenario: Enabled raster generation fails
- **WHEN** an enabled raster request times out, is rejected, or fails quality validation
- **THEN** the slide degrades to text without a fake image, empty frame, or unbounded retry

### Requirement: Visual Integrity Is a Publication Gate
The system SHALL mark a deck unpublishable when learner-visible output contains raw diagram source, invalid visual programs, empty visual placeholders, unresolved required assets, or contextless formulas split from adjacent explanation.

#### Scenario: Raw Mermaid leaks into a slide
- **WHEN** visible slide content contains Mermaid directives such as `graph TD`, `flowchart`, or `sequenceDiagram`
- **THEN** release quality contains a critical visual-integrity issue

#### Scenario: Formula is isolated from adjacent explanation
- **WHEN** a formula-only slide has explanatory source immediately adjacent but allocated to another slide
- **THEN** release quality contains a critical orphan-formula issue

#### Scenario: All visual integrity checks pass
- **WHEN** every rendered visual is valid and source-grounded and no forbidden placeholder or raw source is visible
- **THEN** visual integrity does not prevent publication
