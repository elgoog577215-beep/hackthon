## ADDED Requirements

### Requirement: Published Templates Declare V6 Layout Contracts
The system SHALL publish `template_layout_contract_v1` entries containing layout identity, teaching intent, artifact kinds, typed slots, capacities, safe continuations and Web/PPTX adapters.

#### Scenario: A built-in template is selected for V6
- **WHEN** its version is frozen
- **THEN** every required V6 teaching intent resolves to a declared layout or explicit base-layout inheritance
- **AND** the template digest covers the layout contracts and assets

#### Scenario: A practice task contains ordered actions
- **WHEN** `practice-prompt` receives a typed `steps` slot
- **THEN** its Web and PPTX adapters resolve to the published `practice-sequence` composition
- **AND** the composition provides one readable numbered row per source action

#### Scenario: A dense table has three or more columns
- **WHEN** a split interpretation panel would make complete cells unreadable
- **THEN** the template selects its declared full-width table plus summary-band variant
- **AND** row heights and continuation pages adapt without reducing body text below the declared minimum

#### Scenario: Complete source requires many continuation pages
- **WHEN** draft-selected code, steps, table rows or approved screen copy exceed one layout's declared capacity
- **THEN** the pack's finite safe-continuation graph remains reusable for every required page
- **AND** the template contract does not impose a teaching page-count limit or require smaller text to force content into fewer pages

#### Scenario: A personal template is published for V6
- **WHEN** representative-page mapping, capacity declarations or required layout coverage are incomplete
- **THEN** V6 publication is rejected with structured template diagnostics
- **AND** the template may remain a draft without affecting prior versions

### Requirement: Legacy Layout Names Are Read-Only
The system SHALL keep legacy layout aliases outside the V6 candidate registry.

#### Scenario: A V5 deck is opened
- **WHEN** it contains a legacy renderer layout
- **THEN** the compatibility reader may map it for display/export
- **AND** the mapping does not make that alias eligible for a new V6 story plan

### Requirement: Enhanced Layouts Have Certified Execution Bindings
The system SHALL add `capability_contract_version=teaching_layout_v2` to enhanced published template contracts and SHALL certify each eligible layout using real filled samples.

#### Scenario: A built-in comparison template is registered
- **WHEN** its template version is prepared for publication
- **THEN** it declares compatible expression structures, subject/dimension constraints, semantic slots, object or component targets, capacity, font floor and supported editability
- **AND** source files, bindings, component versions, font policy and sample results contribute to its immutable digest

#### Scenario: The template uses native slide objects
- **WHEN** a slot is marked `native_fill`
- **THEN** its target resolves by source slide part, stable shape/group identity, cell or chart target as appropriate
- **AND** missing or ambiguous targets block template certification
- **AND** the renderer preserves declared static artwork rather than clearing the page and claiming faithful filling

#### Scenario: The template uses controlled drawing components
- **WHEN** a slot is marked `component_render`
- **THEN** the template names a versioned component with explicit typed inputs and supported geometry
- **AND** both preview and export use the same resolved scene
- **AND** no model-generated executable code is accepted as a component

#### Scenario: A source PPTX requires inference
- **WHEN** import guesses a layout role or content rectangle from geometry
- **THEN** the result remains a draft with provenance and confidence information
- **AND** certification requires the appropriate maintainer to validate the semantic mapping and filled result
- **AND** an unsupported SmartArt or chart remains explicitly unsupported instead of being labeled editable

### Requirement: Template Capacity Is Measured With Actual Output
The system SHALL validate short, normal and long text, Chinese fonts, formulas, repeated items and graphical relations against actual filled and rendered pages before certifying a layout.

#### Scenario: Character count fits but actual text wraps excessively
- **WHEN** a real rendered sample clips or exceeds the declared font floor
- **THEN** certification fails and the capacity or layout is corrected
- **AND** estimated character count cannot override the real render result

#### Scenario: A core visual works without an image service
- **WHEN** a comparison, flow or hierarchy template uses native graphic primitives
- **THEN** certification and production rendering require no image-generation provider
- **AND** an optional illustration can be omitted only through a declared compatible draft layout

### Requirement: Themes And Expression Structures Are Independent
The system SHALL publish themes separately from the semantic structures they style and SHALL expose only certified compatible layouts to content planning.

#### Scenario: A lesson uses two comparison forms
- **WHEN** one page needs a pair of aligned diagrams and another needs a dimension matrix
- **THEN** they select distinct certified comparison layouts under the same theme
- **AND** the system does not use one generic two-body layout for every comparison

#### Scenario: A second theme is applied
- **WHEN** the teacher changes the chosen template or theme
- **THEN** a new draft binding is capacity-checked and reviewed before confirmation
- **AND** source facts and expression relations remain intact
- **AND** an incompatible layout reports a gap rather than silently modifying content
