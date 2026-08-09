## ADDED Requirements

### Requirement: Target Candidate And Published Schemas Are Distinct Facts

The system SHALL report the requested target schema, current candidate schema,
and published schema independently for a slide representation build.

#### Scenario: A V5 build is still running
- **WHEN** no final V5 candidate has passed its contracts
- **THEN** the UI shows V5 as the target and no V5 candidate yet
- **AND** it does not label internal legacy materialization as the candidate or published version

#### Scenario: A V5 candidate needs manual editing
- **WHEN** a complete readable V5 candidate contains page-level manual edit issues
- **THEN** candidate and published schema remain V5
- **AND** the representation exposes `v5_needs_manual_edit` and affected page reasons

### Requirement: Failed V5 Builds Preserve The Last Good Representation

The system SHALL build V5 candidates in shadow state and atomically replace the
current representation only after a publishable V5 terminal outcome.

#### Scenario: A rebuild fails globally
- **WHEN** a V5 rebuild ends as `v5_failed`
- **THEN** the last-good representation remains available
- **AND** the failed candidate is not partially committed or mixed with last-good pages

