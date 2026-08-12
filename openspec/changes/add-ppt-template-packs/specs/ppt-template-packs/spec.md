## ADDED Requirements

### Requirement: Every selectable built-in theme is a complete template pack
The system SHALL provide seven background roles, ten editable text-box styles, eighteen semantic role mappings, version metadata, preview metadata and a reference deck for every selectable built-in PPT theme.

#### Scenario: Teacher selects any built-in theme
- **WHEN** the teacher opens the PPT generator and selects one of the five built-in themes
- **THEN** browser preview and PPTX export resolve the same complete template version and role assets

### Requirement: Teacher can compile a personal template without authoring a pack
The system SHALL let a teacher create a personal template draft from a reference PPTX or brand fields, inspect extracted style choices and publish an immutable version without editing a Manifest file.

#### Scenario: Import one reference PPTX
- **WHEN** a teacher uploads a valid reference PPTX
- **THEN** the system extracts safe colors, fonts, ratio and representative page candidates, creates a 16:9 draft preview and does not execute macros or external content

#### Scenario: Image generation is unavailable
- **WHEN** the optional image provider is not configured or fails
- **THEN** draft compilation still succeeds using extracted/uploaded assets, theme tokens and editable shape recipes

### Requirement: Personal templates are owner isolated and versioned
The system SHALL return, modify, publish and serve personal template assets only to the owning request identity. Published versions MUST be immutable and soft deletion MUST NOT break an existing representation that locked that version.

#### Scenario: Other teacher requests a template asset
- **WHEN** a different user requests a personal template or asset identifier
- **THEN** the system returns not found without exposing metadata or physical paths

#### Scenario: Teacher republishes a template
- **WHEN** the teacher changes a draft and publishes again
- **THEN** the system creates a new version while existing slide decks retain the old locked version

### Requirement: Template images never own teaching text
The system SHALL keep slide titles, body text, formulas, code, tables and citations editable in both browser and PPTX output. Background and decoration images MUST NOT contain embedded teaching text.

#### Scenario: Render a styled callout
- **WHEN** a semantic text-box style uses a decorative image
- **THEN** the image remains behind or beside the editable text and exactly one component owns the accent rail
