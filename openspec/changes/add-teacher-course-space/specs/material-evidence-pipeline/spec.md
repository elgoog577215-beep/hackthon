## ADDED Requirements

### Requirement: Course-space assets can be selected as generation evidence
The system SHALL expose a stable asset reference for each imported course-space file so a later course-generation flow can explicitly bind selected materials without copying the original file.

#### Scenario: Later generation reads a selected asset reference
- **WHEN** a teacher selects an imported source file for a future generation request
- **THEN** the request can reference its stable asset identifier and source metadata without duplicating the original file
