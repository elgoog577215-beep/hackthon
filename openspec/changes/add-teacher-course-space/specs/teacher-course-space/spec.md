## ADDED Requirements

### Requirement: Teacher course work packages are isolated
The system SHALL let an authenticated teacher create and list only that teacher's course work packages. A work package MUST include course name, academic year, term, status, timestamps and an immutable owner identifier.

#### Scenario: Teacher sees only own work packages
- **WHEN** a teacher requests their work package list
- **THEN** the system returns only packages owned by that request identity

#### Scenario: Other teacher cannot read a work package
- **WHEN** a different teacher requests a work package identifier
- **THEN** the system returns not found without exposing its metadata

### Requirement: Work package preserves a course asset tree
The system SHALL store each asset under a work package with an original filename, normalized relative path, category suggestion, teacher-selected category, content hash, size, upload time and import batch identifier.

#### Scenario: Teacher creates a term workspace
- **WHEN** the teacher creates “数据结构 / 2025-2026 / 春季”
- **THEN** the system creates an empty work package that can receive assets without creating a learning course

#### Scenario: Teacher starts from the school material template
- **WHEN** the teacher chooses the school material template while creating a work package
- **THEN** the workspace displays the six real template folders numbered continuously from 0 to 5 without fake file slots, and the teacher can select a folder or create another folder before importing files

### Requirement: Workspace behaves as a navigable course file library
The system SHALL present a course work package as a nested directory workspace: the left navigation tree selects a folder, the main area lists only direct child folders and files, and create/import actions write to that current folder.

#### Scenario: Teacher enters a nested course folder
- **WHEN** the teacher opens `2、PPT` from the left tree or main file list
- **THEN** the main area shows the `2、PPT` breadcrumb and only that folder's direct contents

#### Scenario: Teacher imports into the current folder
- **WHEN** the teacher imports `第 1 讲.pptx` while viewing `2、PPT`
- **THEN** the file is saved and displayed at `2、PPT/第 1 讲.pptx` in both the work package metadata and physical `content` directory tree

#### Scenario: Teacher corrects a category
- **WHEN** the teacher changes an imported asset from “未分类” to “学校材料”
- **THEN** the asset remains at its original relative path and the updated category is returned in the asset tree
