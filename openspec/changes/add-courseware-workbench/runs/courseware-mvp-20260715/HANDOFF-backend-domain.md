# Handoff — backend-domain (P1)

## Ownership and contract

- Change/run: `add-courseware-workbench` / `courseware-mvp-20260715`
- Contract version: `presentation-event/v1`, `presentation-source/v1`, backend DTOs from frozen P0.
- Owned implementation files:
  - `backend/presentation_repository.py`
  - `backend/presentation_source.py`
  - `backend/tests/test_presentation_repository.py`
- No router, generation, render, quality, shared model/template, registration, dependency or frontend file was edited.
- OpenSpec 1.5.0 was bound to the repo/change. Its stock apply parser reports zero tasks because this Harness deliberately keeps checkbox progress only in `plan.md`; P1 implementation followed `plan.md` and the explicit Authority scope.

## Delivered behavior

### Repository

- Isolated layout: `backend/data/presentation_decks/{course_id}/{deck_id}` (configurable in tests).
- Safe identifiers, root containment checks and per-deck `RLock`.
- Unique temporary JSON files with flush/fsync + `os.replace`.
- Entity-first / manifest-pointer-last writes. Manifest loads verify every active pointer exists.
- Create/list/get deck; create `request_id` idempotency; immutable source snapshot and digest verification.
- Working snapshots set the active generation; incompatible concurrent generations conflict; generation completion/error events clear the active generation.
- Monotonic event streams with exact duplicate acceptance, gap/conflict rejection and `after_seq` replay.
- Append-only revisions with expected-revision conflict, immutable revision files, command idempotency and restore-as-new-revision.
- Request/command receipts bind both an operation name and stable JSON SHA-256 intent fingerprint. Reusing one key across operations or with changed intent raises `IdempotencyKeyReuseConflict` instead of returning an unrelated result.
- `append_revision` accepts `command_operation` and `command_metadata`, and writes the final operation/fingerprint/result receipt within its deck lock. `restore_revision` uses this path directly; there is no generic-receipt then metadata-overwrite window.
- Proposal records with request idempotency and controlled status-only lifecycle transitions.
- Quality reports with manifest pointer and a narrow passed-to-blocked render-failure transition that may only append issues.
- Artifact directory staging, passed-quality requirement, checksum verification, receipt-first/manifest-last commit and dynamic stale detection after later revisions.
- Download resolution accepts only receipt-bound `deck.html` / `deck.pptx`, rejects stale, missing, checksum-mismatched or escaping paths.
- Request/command receipt filenames are SHA-256 of the raw key, so transport ids never become paths.

### Public repository interfaces

- Exceptions: `PresentationRepositoryConflict`, `IdempotencyKeyReuseConflict`, `StaleRevisionConflict`, `ArtifactAccessError`.
- Deck/source: `create_deck`, `list_decks`, `load_manifest`, `get_deck`, `load_source_snapshot`.
- Generation/replay: `save_working`, `load_working`, `clear_active_generation`, `append_event`, `replay_events`.
- Revisions: `append_revision`, `get_revision`, `restore_revision`.
- Proposal/quality: `save_proposal`, `get_proposal`, `update_proposal_status`, `save_quality`, `get_quality`.
- Artifacts: `artifact_directory`, `save_artifact`, `get_artifact`, `resolve_artifact_file`.
- Idempotency: `get/save_request_receipt` and `get/save_command_receipt` retain their old calls and additionally accept `operation` plus `fingerprint_payload`. `append_revision` additionally accepts `command_operation` plus `command_metadata`.
- Module singleton: `presentation_repository`.

### Source projection

- `project_presentation_source(course_data, scope, *, course_id=None) -> (snapshot, SourceRef)`.
- Supports canonical `course_document_v1` and deterministic legacy projection without mutating the input.
- Chapter scope includes the selected sections and descendants, rejects unknown/empty chapter scope, and filters blocks/objectives/questions/misconceptions/assets.
- Persists canonical/legacy identity, version/document/blueprint/asset revisions, sections, blocks (including internal block revisions), objectives, practices, questions, misconceptions, assets and a full SHA-256 digest.
- Formal publication status and blocking issues are frozen into the snapshot and packet; imported courses preserve the existing `Storage.list_courses` compatibility rule.
- `source_packet`, `validate_source_snapshot`, `source_snapshot_sha256` are available to generation/quality code.

## Verification

Commands run from project root:

```text
python -m py_compile backend/presentation_repository.py backend/presentation_source.py
PASS (exit 0)

python -m pytest backend/tests/test_presentation_repository.py -q
9 passed in 0.85s

python -m pytest backend/tests/test_presentation_repository.py backend/tests/test_presentation_contracts.py -q
14 passed in 1.32s

python -m pytest backend/tests/test_presentation_repository.py backend/tests/test_presentation_contracts.py backend/tests/test_presentation_services.py -q
25 passed in 7.66s
```

Covered: canonical/legacy source projection and immutability, scope filtering, create/reload/list, request/command operation/fingerprint idempotency, cross-operation key rejection, invalid identifiers, active-generation conflict, ordered replay, generation state close, immutable/stale revisions, restore as new revision, simulated manifest pointer failure, proposal status, quality binding, artifact checksum/path/stale safety.

## Integration notes and residual risks

- `append_revision(..., activate=True)` clears active generation, but generation service persists quality/completion events afterward; `append_event(generation_complete|error)` therefore performs the final active-generation clear as the authoritative close.
- Apply integration MUST pass `command_operation="apply_proposal"` and `command_metadata={"proposal_id": ..., "expected_revision_id": ...}` into `append_revision`, then use the returned final receipt without a second overwrite. Restore already does so internally.
- Generation request integration SHOULD pass `operation="generate_presentation"` and the stable serialized generate request as `fingerprint_payload` to both `get_request_receipt` and `save_request_receipt`. Proposal persistence already binds `create_proposal` intent internally.
- `save_artifact` expects both fixed files already staged under `artifact_directory`, and a saved `passed` quality report bound to the current revision. Render failure may leave unreferenced staged files, but never a manifest-visible partial artifact.
- Filesystem transactions are crash-consistent at the entity/pointer level, not a general multi-file WAL. Orphaned entity/staging files may remain after a process crash and are intentionally invisible; cleanup can be added later.
- Deck lookup without `course_id` scans course directories and rejects ambiguous deck ids. UUID-style deck ids make ambiguity unlikely, but callers that already know the course should pass it.
- Verification is intentionally Light and presentation-targeted; no full backend suite or process-crash fault injection was run.

## Boundary confirmation

P1 stayed within the four assigned files, did not mutate CourseDocument storage, did not write product presentation data during tests, and did not modify another worker's files.
