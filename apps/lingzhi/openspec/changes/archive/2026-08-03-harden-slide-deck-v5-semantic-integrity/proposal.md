## Why

Production V5 course decks can pass structural quality checks while still losing
teaching meaning: a classification diagram may omit one sibling, unrelated
evidence may be rendered as a direct answer, a low-information transition may
consume a full page, a definition may be split into visually inconsistent
blocks, and recap copy may end mid-clause.

These are publication-integrity failures rather than cosmetic defects. They
must be prevented in the semantic compiler and quality gate before web preview
or PPTX export.

## What Changes

- Make hierarchy and classification diagrams cover every required source item.
- Give every practice question a stable ID and bind direct answers explicitly.
- Use source answers first and permit the configured LLM to synthesize missing
  answers from bounded course context; label provenance and never disguise
  shared evidence as a direct answer.
- Remove standalone micro-transition pages and retain the bridge as metadata on
  the preceding checkpoint or the following section entry.
- Normalize concept pages into aligned definition and explanation groups, and
  reject incomplete audience-facing titles.
- Build chapter recaps from complete claims and render them as a balanced 2x2
  memory grid instead of narrow prose columns.
- Bump the V5 compiler, final-page contract, and visual-policy versions so
  existing decks become stale and must be regenerated.

## Impact

- Backend story planning, visual planning, V5 materialization, quality gates,
  build signatures, and PPTX rendering.
- Frontend practice-feedback, editorial-body, and chapter-recap rendering.
- Existing V5 decks will be regenerated because their build signature changes.
