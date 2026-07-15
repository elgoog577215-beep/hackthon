# Eval Contract — add-courseware-workbench

## Outcome

From a published Lingzhi course, a user can create a source-bound deck, watch outline/pages appear, edit the selected slide through proposal/diff/apply/undo, finalize the active revision, and open matching HTML/PPTX artifacts. A quality-blocked course can preview a draft but cannot export.

## Hard Gates

| Gate | Evidence | Failure meaning |
| --- | --- | --- |
| G1 Contract | backend/frontend schema fixture and OpenSpec strict validation | shared contract is inconsistent |
| G2 Persistence | repository targeted tests | revisions/source/artifacts are unsafe or not recoverable |
| G3 Generation | ordered SSE/API targeted tests | outline/page stream or reconnect is incorrect |
| G4 Patch isolation | proposal/apply/restore targeted tests | AI can overwrite unintended data or duplicate revisions |
| G5 Quality/export | blocked and successful finalize tests | formal download can bypass gates or artifact transaction is partial |
| G6 Render parity | representative HTML/PPTX fixture, PPTX reload, page/title/notes checks | export is unusable or inconsistent |
| G7 Workbench | one real desktop browser main path with console/network inspection | entry, preview, scope or apply flow is broken |
| G8 Source integrity | test proving CourseDocument digest unchanged after deck edits | deck editing mutates course truth |

## Acceptance Criteria

- AC-01: LearningView exposes the courseware entry and both workbench routes resolve.
- AC-02: Deck creation stores an immutable source snapshot and refresh restores working/active state.
- AC-03: Generate emits outline before pages, persists before emit, supports replay and never emits export_ready.
- AC-04: Three template ids and ten layout ids are registered; unknown ids block rather than fall back.
- AC-05: Selected-slide proposal affects only its allowed slide fields; apply and restore append revisions and are idempotent.
- AC-06: Quality-blocked source/deck cannot finalize; issues include code, slide/source target and fix action.
- AC-07: Successful finalize produces receipt-bound HTML/PPTX with matching page count/titles and speaker notes.
- AC-08: Applying any later revision makes the previous artifact stale and disables formal download.
- AC-09: Approved initial visual baseline is retained; desktop uses left preview + fixed 400px AI, narrow uses Preview/AI switch.
- AC-10: CourseDocument/source snapshot digests remain unchanged through deck generate/edit/export.

## Light Evaluator

The goal evaluator runs only:

1. presentation-specific backend tests;
2. presentation-specific frontend tests plus one frontend build;
3. representative render fixture (L01/L04/L07/L08/L09/L10 across the three styles, not every combination);
4. one Playwright desktop main path and one narrow viewport smoke;
5. `openspec validate add-courseware-workbench --strict`.

No full test suite, cross-browser matrix, 3×10 screenshot matrix, multi-provider live generation or performance benchmark is required for this delivery.

## Stop Rule

The GOAL is ready for final verification when all eight hard gates pass and every AC has current evidence. Any source integrity, path traversal, stale-write, partial artifact or publication bypass failure is critical and stops completion.
