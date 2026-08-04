# Upgrade Slide Deck V5 Teaching Semantics

## Why

Course generation V16 emits explicit pedagogy modules, block roles, composition
contracts, lesson archetypes, knowledge references, and feedback structure. The
current V5 slide compactor discards most of that contract and reclassifies
content from Markdown headings. Long decks also skip AI visual planning as one
whole unit. These wrapper regressions make new structured courses less coherent
than legacy prose-heavy courses and turn repairable page issues into failed
builds.

## What Changes

- Normalize V16 and legacy courses into one typed PPT teaching-semantic protocol.
- Compile teaching episodes from explicit roles and module metadata before using
  heading inference.
- Add data-driven, cross-subject presentation profiles outside the renderer.
- Pair learner actions with their source or generated feedback contract.
- Plan visuals in bounded chapter batches with per-batch fallback diagnostics.
- Recompute final V5 page contracts after deterministic repair and discard stale
  intermediate capacity findings.

## Impact

The public representation remains `slide_deck_v5`. Existing stored decks remain
readable, while compiler and policy signature changes force a rebuild before a
deck is considered current.
