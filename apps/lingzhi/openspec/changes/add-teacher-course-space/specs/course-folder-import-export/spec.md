## ADDED Requirements

### Requirement: Teacher can import an entire local course folder
The system SHALL accept a batch of permitted course files with client-provided relative paths, validate each file and retain the valid original files. The server MUST reject absolute, empty and traversal relative paths and MUST report per-file failures without discarding successfully imported files.

#### Scenario: Import a course folder
- **WHEN** a teacher submits PPT, DOCX, XLSX and PDF files from a folder with their relative paths
- **THEN** the system creates an import batch, stores permitted files and returns the classified asset tree and per-file outcomes

#### Scenario: Reject unsafe path
- **WHEN** an import item contains `../` or an absolute path
- **THEN** that item is rejected and no file is written outside the work package storage root

### Requirement: Both import entries use one batch-understanding contract
The system SHALL use the same import endpoint and persisted work-package analysis whether the teacher imports during first-use preparation or later from the course file system. The batch result MUST include every valid asset already in the package so later imports can be related to earlier originals.

#### Scenario: Add more materials after entering the workbench
- **WHEN** a teacher imports another group of files from the course file system
- **THEN** the system runs the same parsing and understanding pipeline used by the preparation dialog and returns one updated package structure

### Requirement: System returns explainable four-dimensional material understanding
The system SHALL parse supported document content and combine deterministic evidence with one bounded batch AI analysis. The persisted result MUST cover document purpose, course/section placement, version or material role, and relationships among uploaded originals. Each asset MUST include a reason, confidence and analysis source.

#### Scenario: Understand an ambiguously named lesson plan
- **WHEN** an imported file has a generic filename but its parsed content contains a lesson objective, teaching focus and teaching process
- **THEN** the system recognizes it as a lesson plan, records the content evidence and places it against the matching course structure when possible

#### Scenario: Classify teaching calendar
- **WHEN** an imported filename includes “教学日历”
- **THEN** the deterministic evidence keeps it under school-materials and the result records the matching reason

#### Scenario: AI provider is unavailable
- **WHEN** parsing succeeds but the semantic model request fails
- **THEN** the import still succeeds with an explicit rule-fallback status and does not label the result as AI-completed

### Requirement: Teacher can download original assets and complete package
The system SHALL let the owning teacher download a single original asset and export a work package as a ZIP while preserving original editable Office files. The ZIP MUST contain a manifest describing categories and source paths.

#### Scenario: Export a complete course package
- **WHEN** the teacher requests work package export
- **THEN** the browser receives a ZIP containing the retained original files organized by category and a UTF-8 manifest
