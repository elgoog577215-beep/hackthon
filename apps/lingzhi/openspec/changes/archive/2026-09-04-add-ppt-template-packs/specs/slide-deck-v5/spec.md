## ADDED Requirements

### Requirement: V5 locks one template version across planning and rendering
The system SHALL include the resolved template pack ID, immutable version and manifest digest in the build signature and final representation. Browser preview and PPTX export MUST consume that same template snapshot.

#### Scenario: Personal template is updated after generation starts
- **WHEN** a V5 build has locked version 1 and the teacher publishes version 2
- **THEN** the in-flight build and its export continue using version 1, while a new build may select version 2

### Requirement: Final layouts do not expose empty template affordances
The V5 final layout selector SHALL reject layouts whose required slots cannot be populated, SHALL fall back to a text-first layout when no real visual exists and SHALL merge adjacent sparse continuations when the merged semantic unit stays inside the selected template capacity.

#### Scenario: One content item reaches a multi-card candidate
- **WHEN** a page contains one usable content item and a three-card layout is considered
- **THEN** the selector chooses a one-item layout and the final page contains no empty cards

#### Scenario: Figure slot has no real visual
- **WHEN** a figure-text layout has no source, retrieved or generated visual
- **THEN** the final candidate uses a compatible text-first layout and does not render a generic placeholder illustration
