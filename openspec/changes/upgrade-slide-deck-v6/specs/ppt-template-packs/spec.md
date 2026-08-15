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
- **WHEN** code, steps, table rows or prose exceed one layout's declared capacity
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
