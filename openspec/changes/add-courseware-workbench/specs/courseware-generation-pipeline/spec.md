## ADDED Requirements

### Requirement: Deck generation uses an immutable source snapshot
Creating a deck MUST project the selected course scope into a source snapshot containing version identity, sections, blocks, block revisions, objectives, practices, misconceptions and asset references. Every slide source reference MUST resolve inside that snapshot.

#### Scenario: The source course changes after deck creation
- **WHEN** the active course version advances after a deck was created
- **THEN** the existing deck MUST keep its original source snapshot and digest
- **AND** MUST be marked as based on an older course version without being silently regenerated

### Requirement: Generation streams structured draft events
Generation MUST stream `deck_outline`, zero or more `slide_upsert`/`slide_patch`, `progress`, `quality_report`, and `generation_complete` events with a monotonic event sequence. It MUST NOT stream PPTX binary data and MUST NOT emit `export_ready` before finalize.

#### Scenario: Chapter deck generation starts
- **WHEN** the user starts a deck generation
- **THEN** the outline MUST be persisted and emitted before filled slides
- **AND** each completed slide MUST be persisted before its `slide_upsert` event
- **AND** generation MUST end with `generation_complete` or `error`

### Requirement: Generation handles reconnects and concurrent commands
Generation events MUST use a stable generation id and sequence, support replay after a known sequence, deduplicate repeated request ids, and reject a second incompatible active generation.

#### Scenario: The SSE connection drops after three slides
- **WHEN** the client reconnects with the last acknowledged event sequence
- **THEN** the service MUST replay only later events or hydrate the equivalent current snapshot
- **AND** MUST NOT duplicate or reorder already applied slides

### Requirement: Generation-time outline edits do not revive cancelled pages
The workbench MAY delete a planned page or reorder the outline during generation. A cancelled page MUST have a tombstone bound to the outline revision, and a late worker result MUST be discarded.

#### Scenario: A user deletes a page while its worker is running
- **WHEN** the worker later completes the deleted page
- **THEN** the service MUST discard that result
- **AND** MUST NOT restore the deleted page to the outline

### Requirement: Models only produce typed content for registered layouts
The generator MUST use typed JSON/page briefs and select only registered style and layout identifiers. The registry MUST define `lingzhi-classroom`, `lingzhi-engineering`, `lingzhi-academic`, and L01 cover, L02 agenda, L03 section, L04 concept, L05 comparison, L06 process, L07 code_annotation, L08 misconception, L09 practice and L10 summary.

#### Scenario: The model returns an unknown layout
- **WHEN** a generated page references a layout not present in the registry
- **THEN** the page MUST be marked failed with a blocking schema issue
- **AND** MUST NOT silently fall back to a generic content layout

### Requirement: Page generation is source-aware and failure-visible
Each page filler MUST receive the relevant source blocks/objectives/assets for that page rather than one clipped global document. A failed page MUST remain failed and block export instead of becoming an empty ready page.

#### Scenario: The LLM provider fails while filling one page
- **WHEN** a page cannot be filled after bounded retries
- **THEN** the working snapshot MUST preserve other successful pages
- **AND** the failed page MUST expose a repairable `model_unavailable` or generation issue
- **AND** formal export MUST remain blocked

### Requirement: Revisions and commands are immutable and idempotent
Every applied proposal or restore MUST create a new full revision. Apply, restore and finalize commands MUST accept an expected revision and command id; repeated command ids MUST return the original receipt and stale revisions MUST conflict.

#### Scenario: The client repeats an apply command after a timeout
- **WHEN** the same command id is submitted again
- **THEN** the service MUST return the original applied revision receipt
- **AND** MUST NOT create a duplicate revision

### Requirement: Finalize enforces deterministic quality and publication gates
Finalize MUST block unless the bound source was formally publishable and the active deck passes schema/layout, ready-state, traceability, objective coverage, misconception/practice, capacity, render measurement and HTML/PPTX parity checks. LLM semantic review MAY advise but MUST NOT be the MVP blocking authority.

#### Scenario: The source course is quality-blocked
- **WHEN** the user finalizes a deck whose bound source failed the formal publication gate
- **THEN** draft preview MAY remain available
- **AND** finalize MUST return structured blocking issues with fix actions
- **AND** MUST NOT create a downloadable artifact

### Requirement: Finalize creates a complete artifact transaction
Finalize MUST render HTML and PPTX from the same active revision, verify PPTX reload plus page/title parity, compute checksums, write both files and receipt, and only then update the manifest and emit `export_ready`.

#### Scenario: PPTX rendering fails after HTML rendering
- **WHEN** one output fails or parity validation fails
- **THEN** the manifest MUST NOT point to a partial artifact
- **AND** the deck MUST remain editable with a structured quality/render issue

### Requirement: Artifact downloads are receipt-bound
Artifact endpoints MUST resolve files only through a validated artifact receipt and safe repository identifiers.

#### Scenario: A caller supplies a path-like artifact id
- **WHEN** an artifact id contains an invalid or traversal-like identifier
- **THEN** the service MUST reject the request
- **AND** MUST NOT access a path outside the presentation repository
