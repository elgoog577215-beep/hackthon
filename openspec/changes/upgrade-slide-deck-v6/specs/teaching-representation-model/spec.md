## ADDED Requirements

### Requirement: Teaching Representations Preserve The Last Published Deck
The system SHALL store V6 candidates separately from the latest published representation and SHALL update the published pointer only after atomic V6 publication.

#### Scenario: V6 story planning fails
- **WHEN** the candidate ends as `v6_failed`
- **THEN** the representation API reports the structured candidate failure
- **AND** the latest published V5 or V6 deck remains readable and exportable

#### Scenario: V6 requires visual review
- **WHEN** every hard gate passes but an allowed visual degradation exists
- **THEN** the candidate publishes as `v6_needs_manual_edit`
- **AND** the quality panel names each degraded page and reason

### Requirement: AI Planning Status Is Truthful
The system SHALL distinguish AI-completed, AI-degraded and unavailable planning stages in representation metadata.

#### Scenario: A deterministic compatibility artifact exists
- **WHEN** no V6 story AI batch completed
- **THEN** the UI does not label story AI as completed
- **AND** a V6 candidate cannot publish from that artifact
