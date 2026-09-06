# Proposal: Harden Markdown math rendering

## Why

Imported and generated course Markdown can contain multiline display formulas and legacy mixed prose/formula forms. The reader must render these inputs without leaking delimiters, corrupting LaTeX, or weakening HTML sanitization.

## What Changes

- Treat valid multiline `$$ ... $$` input as display math before inline parsing.
- Tolerate narrowly defined legacy escaping and mixed prose/formula forms.
- Route inline learning-record summaries through the shared sanitized Markdown/KaTeX renderer.
- Preserve existing Markdown, Mermaid, code, and security behavior.

## Impact

- Affected capability: `learning-experience-shell`
- Affected frontend: shared Markdown renderer and its regression tests
