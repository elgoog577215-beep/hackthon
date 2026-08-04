## ADDED Requirements

### Requirement: Teacher can import an entire local course folder
The system SHALL accept a batch of permitted course files with client-provided relative paths, validate each file and retain the valid original files. The server MUST reject absolute, empty and traversal relative paths and MUST report per-file failures without discarding successfully imported files.

#### Scenario: Import a course folder
- **WHEN** a teacher submits PPT, DOCX, XLSX and PDF files from a folder with their relative paths
- **THEN** the system creates an import batch, stores permitted files and returns the classified asset tree and per-file outcomes

#### Scenario: Reject unsafe path
- **WHEN** an import item contains `../` or an absolute path
- **THEN** that item is rejected and no file is written outside the work package storage root

### Requirement: System recommends an explainable category
The system SHALL classify imported assets into teaching-design, lesson-materials, homework-labs, school-materials, course-archive or uncategorized using deterministic filename/path rules and return the rule reason.

#### Scenario: Classify teaching calendar
- **WHEN** an imported filename includes “教学日历”
- **THEN** it is suggested as school-materials with the matching rule reason

### Requirement: Teacher can download original assets and complete package
The system SHALL let the owning teacher download a single original asset and export a work package as a ZIP while preserving original editable Office files. The ZIP MUST contain a manifest describing categories and source paths.

#### Scenario: Export a complete course package
- **WHEN** the teacher requests work package export
- **THEN** the browser receives a ZIP containing the retained original files organized by category and a UTF-8 manifest
