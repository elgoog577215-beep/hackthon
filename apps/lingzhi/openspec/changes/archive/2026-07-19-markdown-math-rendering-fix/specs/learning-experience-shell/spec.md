## ADDED Requirements

### Requirement: Shared Markdown rendering must preserve valid mathematics

The frontend MUST render valid inline and display LaTeX through the shared sanitized Markdown renderer. It MUST NOT leak math delimiters, placeholder tokens, or partial KaTeX error output for supported input forms.

#### Scenario: Multiline display formula

- **WHEN** course Markdown contains a valid multiline `$$ ... $$` formula
- **THEN** the renderer MUST produce one display-math region
- **AND** the visible output MUST NOT contain raw `$$` delimiters

#### Scenario: Legacy formula followed by prose

- **WHEN** a legacy course line contains a delimiter-free equation followed by Chinese explanatory prose
- **THEN** the renderer MUST send only the equation portion to KaTeX
- **AND** MUST preserve the explanatory prose as ordinary text

#### Scenario: Sanitized shared rendering

- **WHEN** course content or an inline learning-record summary contains Markdown and mathematics
- **THEN** both surfaces MUST use the shared Markdown/KaTeX renderer
- **AND** HTML sanitization and existing code and Mermaid behavior MUST remain enabled
