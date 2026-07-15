## Stable Work Packages

`tasks.md` defines stable scope and dependencies. Execution progress lives only in `plan.md`.

### WP0 — Freeze shared contracts and renderer spike

- Scope: source identity, domain schemas, state transitions, event envelope, API bodies/errors, postMessage channel, style/layout registry metadata.
- Files: presentation model/template modules, frontend presentation types, eval fixture.
- Dependency: none; all later work depends on this package.
- Acceptance: typed backend/frontend fixtures agree; unknown layout fails; a six-page Chinese fixture containing code and speaker notes renders to HTML/PPTX and reloads with matching page count/title.
- Rollback: no product route is exposed until this package passes.

### WP1 — Deck repository and source projection

- Scope: safe-id repository, source snapshot projection/digest, manifest, working snapshot, immutable revisions, proposal/artifact records, locks, atomic pointer switch, idempotency and stale revision conflicts.
- Files: `presentation_repository.py`, `presentation_source.py`, repository tests.
- Dependency: WP0 schemas.
- Acceptance: create/reload, append revision, restore-as-new-revision, duplicate command receipt, stale conflict, invalid id/path and simulated failed pointer switch are covered.
- Rollback: presentation data is isolated under `backend/data/presentation_decks/`; no CourseDocument migration is required.

### WP2 — Generation, quality and rendering services

- Scope: curator/outline/page fill pipeline, bounded async concurrency, working snapshot updates, tombstones, three styles/ten layouts, deterministic draft/final quality, HTML/PPTX render and artifact receipt.
- Files: `presentation_generation.py`, `presentation_quality.py`, `presentation_render.py`, `presentation_templates.py`, `requirements.txt`, targeted tests/fixtures.
- Dependency: WP0 and WP1.
- Acceptance: outline precedes pages; failed page is visible and blocks export; L08/L09 requirements work; finalize creates both verified files or neither.
- Rollback: disable presentation router; repository state remains inspectable.

### WP3 — Presentation API and event stream

- Scope: create/list/get, generate fetch-SSE, replay, proposal, apply, restore, finalize and artifact download; request/command idempotency and expected revision conflicts.
- Files: `routers/presentations.py`, `main.py`, `routers/__init__.py`, API tests.
- Dependency: WP1 and service interfaces from WP2.
- Acceptance: one happy generation stream has ordered ids; reconnect/replay is deterministic; concurrent generation and stale apply return 409; blocked finalize creates no artifact.
- Rollback: unregister the router without affecting current course/AI endpoints.

### WP4 — Workbench shell and preview

- Scope: learning entry, routes, create/select flow, approved visual baseline, toolbar/stepper, left preview, 400px right pane, loading/generating/editing/final states, postMessage validation, narrow Preview/AI switch.
- Files: router, `LearningView.vue`, `CourseLibraryView.vue`, `PresentationStudioView.vue`, presentation preview/launch/quality components.
- Dependency: WP0 frontend contracts; may use fixture store before WP3 integration.
- Acceptance: route opens from current course; outline/pages appear incrementally; selected slide updates AI scope; refresh hydrates current deck; narrow switch preserves selection.
- Rollback: remove route/entry; no shared App shell contract changes are required.

### WP5 — Courseware AI proposal workflow

- Scope: deck-specific AI aside, quick actions, chat proposal, diff, apply/cancel/undo, source display, artifact stale state.
- Files: `PresentationAiAside.vue`, `PresentationPatchProposal.vue`, `stores/presentation.ts`, `usePresentationEvents.ts`.
- Dependency: WP3 proposal/apply contracts and WP4 shell.
- Acceptance: current-page request changes only that slide; apply creates one revision; repeated apply is idempotent; undo creates a restore revision; download disables after a new revision.
- Rollback: retain read-only generation/preview while hiding deck chat actions.

### WP6 — Light integration release gate

- Scope: targeted backend tests, targeted frontend tests, one desktop browser main path, one narrow-screen smoke, representative render fixtures and concise proof.
- Dependency: WP0–WP5.
- Acceptance: all ACs in `eval-contract.md` have current evidence; related tests/build pass; approved visual baseline is recognizable; no new console/network error occurs in the main path.
- Explicitly excluded: full repository suite, multi-browser matrix, 3×10 visual screenshot matrix, multiple live LLM providers and exhaustive performance benchmarking.
