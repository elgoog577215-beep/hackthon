## ADDED Requirements

### Requirement: Markdown Mermaid Blocks Preserve Surrounding Markdown Structure
The system SHALL render Mermaid code fences inside Markdown content without exposing surrounding Markdown headings, lists, or prose as raw source text in the rendered UI.

#### Scenario: Heading before Mermaid block remains rendered as Markdown
- **WHEN** imported Markdown contains a heading immediately followed by a Mermaid code fence
- **THEN** the heading is rendered as a heading element and not displayed with raw Markdown markers such as `###`

#### Scenario: Text after Mermaid block remains rendered as Markdown
- **WHEN** imported Markdown contains normal prose after a Mermaid code fence
- **THEN** the prose is rendered as Markdown content and not merged into or corrupted by the Mermaid render output

### Requirement: Mermaid Rendering Uses One Canonical Frontend Pipeline
The system SHALL apply one shared Mermaid sanitization, rendering, and SVG post-processing pipeline across all frontend code paths that render Markdown-originated Mermaid diagrams.

#### Scenario: Direct renderer and queued renderer use the same cleanup behavior
- **WHEN** the same Mermaid source is rendered through component-local rendering and DOM-scan rendering paths
- **THEN** both paths produce equivalent cleaned Mermaid input and equivalent rendered SVG safeguards

#### Scenario: Direct renderer and queued renderer use the same Mermaid configuration
- **WHEN** Mermaid diagrams are rendered from different frontend entry points
- **THEN** both entry points use the same Mermaid initialization settings for theme, security level, and font configuration

### Requirement: Mermaid Syntax Repair Preserves Label Meaning
The system SHALL repair known malformed Mermaid label quoting patterns without changing the intended visible meaning of formulas or mixed text labels.

#### Scenario: Formula label with nested quote pattern stays semantically correct
- **WHEN** a Mermaid node label contains an invalid nested double-quote pattern around a formula such as `E = E₀ cos("ωt - kz")`
- **THEN** the repaired render output preserves the formula as a formula-style parenthesized expression instead of converting it into visibly single-quoted arguments

#### Scenario: Mixed-width label with parentheses remains readable
- **WHEN** a Mermaid node label includes Chinese text, Latin symbols, and parenthesized math fragments
- **THEN** the repaired render output keeps the full label content readable without dropping or rewriting significant characters

### Requirement: Rendered Mermaid SVG Prevents Label Clipping
The system SHALL post-process rendered Mermaid SVG output so node labels with Chinese text, mixed-width text, or long right-edge content are not visibly clipped.

#### Scenario: Rightmost Chinese character is fully visible
- **WHEN** a Mermaid node label ends with Chinese text near the right edge of a node
- **THEN** the rendered SVG provides enough width and overflow allowance for the final character to remain fully visible

#### Scenario: Mixed Chinese and Latin math label is fully visible
- **WHEN** a Mermaid node label contains mixed Chinese text and Latin formula notation such as `坡印廷矢量 S = E × H`
- **THEN** the final Latin characters at the right edge are fully visible in the rendered diagram

### Requirement: Backend Mermaid Guidance Avoids Ambiguous Nested Quotes
The system SHALL provide Mermaid prompt guidance that discourages nested unescaped double quotes inside node labels and directs formula labels toward Mermaid-safe formatting.

#### Scenario: Prompt guidance covers formula labels
- **WHEN** the backend composes Mermaid generation instructions for the LLM
- **THEN** the instructions explicitly tell the model to avoid nested unescaped double quotes in labels that contain formulas or parentheses

#### Scenario: Prompt guidance remains compatible with quoted labels
- **WHEN** the backend instructs the LLM on Mermaid node formatting
- **THEN** the instructions still require Mermaid-safe labels while allowing formulas and parentheses to render without frontend meaning-changing rewrites

### Requirement: Mermaid Rendering Regressions Are Covered by Automated Tests
The system SHALL include automated regression coverage for the known Mermaid import failure patterns and canonical label edge cases.

#### Scenario: Imported Markdown regression is covered
- **WHEN** the Mermaid regression suite runs
- **THEN** it includes a case derived from the imported Markdown fixture that previously produced raw headings, clipped labels, or malformed formula labels

#### Scenario: Canonical edge cases are asserted
- **WHEN** the Mermaid regression suite runs
- **THEN** it verifies render success, absence of the Mermaid error UI, and preservation of expected label text for quote-heavy and multilingual diagrams
