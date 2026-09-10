# ppt-template-packs Specification

## Purpose
为内置主题和教师个人模板建立可版本化、可追溯的页面构造、槽位、容量与渲染合同，保证页面内容稿、浏览器预览和 PPTX 导出始终解析到同一模板版本，并在模板不完整时阻止错误发布。

## Requirements

### Requirement: Every selectable built-in theme is a complete template pack
The system SHALL provide seven background roles, ten editable text-box styles, eighteen semantic role mappings, version metadata, preview metadata and a reference deck for every selectable built-in PPT theme.

#### Scenario: Teacher selects any built-in theme
- **WHEN** the teacher opens the PPT generator and selects one of the five built-in themes
- **THEN** browser preview and PPTX export resolve the same complete template version and role assets

### Requirement: Teacher can compile a personal template without authoring a pack
The system SHALL let a teacher create a personal template draft from a reference PPTX/POTX or brand fields, inspect extracted style choices and publish an immutable version without editing a Manifest file.

#### Scenario: Import one reference PPTX or POTX
- **WHEN** a teacher uploads a valid reference PPTX or POTX
- **THEN** the system extracts safe colors, fonts, ratio, Slide/Layout relations, normalized fill frames and representative page candidates, creates a 16:9 draft preview and does not execute macros or external content

#### Scenario: Imported template contains reusable page constructions
- **WHEN** the reference PPTX provides slide-level text regions or inherited Layout placeholders
- **THEN** deterministic parsing produces source-linked page constructions with normalized slot frames and a declared fill strategy instead of replacing them with built-in layout topology

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

### Requirement: Template and PPT manuscript constrain each other
The system SHALL expose the selected immutable template's construction, slot and capacity contract to the AI manuscript planner. The planner MUST select only permitted construction IDs, while deterministic code MUST validate capacity and source binding without rewriting teaching content.

#### Scenario: AI plans a page from confirmed script content
- **WHEN** the manuscript planner receives one teaching unit and a personal template contract
- **THEN** it selects one source-linked construction exposed by that contract and the resulting manuscript records the exact template layout ID

#### Scenario: Content exceeds a selected construction
- **WHEN** deterministic capacity checks show that a semantic unit cannot fit the selected construction
- **THEN** the system paginates into a permitted continuation or asks the AI to choose another permitted construction; it does not shrink, truncate or silently switch templates

### Requirement: Manuscript and final PPT share one frozen template version
In the no-original-PPT branch, the system SHALL persist the template ID, immutable version and contract digest with the PPT manuscript. Final PPT generation MUST resolve and verify that exact version and MUST reject a missing or drifted contract.

#### Scenario: Teacher publishes a newer template after confirming the manuscript
- **WHEN** the manuscript is locked to personal template version 1 and version 2 is later published
- **THEN** final generation still compiles version 1 and produces the same template digest used by the manuscript

#### Scenario: Locked template digest does not match
- **WHEN** final generation resolves a contract whose ID, version or digest differs from the confirmed manuscript lock
- **THEN** generation stops with a recoverable template-lock error and asks the teacher to regenerate the manuscript

### Requirement: Page recovery preserves source content and accepted work
The system SHALL record `ppt_page_recovery_v3` on newly recovered blocks. Fixed-handout completion MUST preserve the source revision and accepted pages, repair only failed pages or source ranges, and withhold publication while required pages remain invalid or missing.

#### Scenario: A source code excerpt exceeds the real code frame
- **WHEN** measured code exceeds the frozen template's frame capacity
- **THEN** contiguous continuations retain the exact complete excerpt in order, pass the same font and geometry checks, and remain stable when the checkpoint is resumed

#### Scenario: The repair model returns an unusable response
- **WHEN** the response is empty, truncated, non-object JSON, or contains no pages
- **THEN** recovery preserves both the original page error and the repair error, bounds retries, and does not publish a partial fallback as a complete manuscript

#### Scenario: The provider is temporarily unavailable
- **WHEN** a page repair encounters a provider timeout or unavailability
- **THEN** the current checkpoint is retained and recovery performs at most one delayed provider recovery window per bundle; a gateway-rejected source unit may be split once into smaller exact ranges, while repeated failure switches the current and remaining ranges to complete source-grounded local pages without further model calls

#### Scenario: Source-grounded local page fallback is required
- **WHEN** the model remains unavailable after the bounded recovery window
- **THEN** code ranges compile into measured code continuations and prose ranges compile into ordered short exact-source points whose source quotes concatenate to the complete range; the system does not publish a truncated summary or invent teaching content

#### Scenario: A repair source unit is code dense
- **WHEN** page repair prepares a prompt for a code source range
- **THEN** the system compiles exact code ranges directly into measured code continuations without a model call; prompts for remaining mixed or prose ranges include at most three role-appropriate page forms, a bounded literal-source catalog including the exact full range, and an output budget derived from that range instead of the complete teaching block

#### Scenario: A missing page group owns a large or code-dense source block
- **WHEN** the frozen handout block exceeds the bounded page-repair input threshold
- **THEN** the system creates stable contiguous source-range units, requests pages for one unit at a time, preserves exact source text, and resumes without calling the model again for units whose pages already passed validation

#### Scenario: A bounded page-repair request times out twice
- **WHEN** one source-range unit does not return a complete response within both allowed requests
- **THEN** the task fails at the PPT page-generation step with the failed block and repair-unit identity, while accepted pages, source ranges and the handout remain available for retry
