# HANDOFF — backend-service

## Boundary

- Contract: `add-courseware-workbench` / `presentation-event/v1` / run `courseware-mvp-20260715`.
- Owned implementation: `backend/presentation_generation.py`, `backend/presentation_quality.py`, `backend/routers/presentations.py`, `backend/tests/test_presentation_services.py`, `backend/tests/test_presentations_api.py`.
- No edits to CourseDocument, shared presentation models/templates/render, repository/source, main registration, requirements, ports, or existing course AI protocols.

## Delivered behavior

- Teaching curator → registered outline → bounded async page fill (max 3), using the active `AIBase` profile when available and an explicitly labelled deterministic source fallback when unavailable.
- Persist-before-emit working snapshots and monotonic SSE event logs; replay by generation/sequence; request fingerprint idempotency; incompatible active generation and stale revision conflicts.
- Visible failed pages, tombstone check before late worker commit, draft quality report, immutable initial revision, and `generation_complete` as the only normal generate terminal event.
- Deterministic quality authority for ready/schema/layout/source refs/objective coverage/L08/L09/capacity/publication/render checksum/overflow/collision/page count. LLM advice does not override blockers.
- Current-page or explicit deck-scope proposals with an AI-first, whitelist-only patch contract; deterministic proposal fallback; proposal → apply → append-only revision; idempotent apply intent bound to proposal id; restore delegated to append-only repository behavior.
- Separate finalize transaction: current revision + browser measurement + publication gate → HTML/PPTX render/parity → passed quality receipt → artifact receipt → `export_ready`. No partial artifact receipt on render failure.
- API routes for create/list/get/generate/events/chat/apply/restore/finalize and receipt-bound HTML/PPTX download. Standard client envelope is `{deck, revision, working, quality, artifact}`; artifact URLs are server-generated.

## Repository/source interface consumed

- Repository: `create_deck`, `list_decks`, `load_manifest`, `get_deck`, `load_source_snapshot`, `save_working`, `load_working`, `clear_active_generation`, `append_event`, `replay_events`, `append_revision`, `get_revision`, `restore_revision`, `save_proposal`, `get_proposal`, `update_proposal_status`, `save_quality`, `artifact_directory`, `save_artifact`, `get_artifact`, `resolve_artifact_file`, and request/command receipt APIs.
- Source: `project_presentation_source(course, scope, course_id=...)` and `source_packet(snapshot)`.
- Generation request receipts use operation `generate_presentation` plus full request fingerprint. Apply command receipts use operation `apply_proposal` plus proposal/revision metadata.

## Evidence

- `python -m pytest backend/tests/test_presentations_api.py backend/tests/test_presentation_services.py backend/tests/test_presentation_repository.py backend/tests/test_presentation_contracts.py -q`
- Latest result: **27 passed in 11.28s**.
- During lead integration an earlier combined run hit one transient Windows temporary-manifest `PermissionError`; the identical command immediately reran **20/20 PASS**, and the later expanded run above passed **27/27**. This is recorded as a Windows file-lock risk, not hidden as a clean first-run claim.
- Focused frontend G5 follow-up (separate parent assignment): preview measurement tests **7/7 PASS** and `vue-tsc -b` PASS.

## Risks / integration notes

- Lead must register `routers.presentations.router` under `/api`; this worker intentionally did not edit `main.py` or router package registration.
- Background generation survives client disconnect inside the running process and replay is durable. A process crash preserves working/event state but does not automatically restart unfinished page workers; retry/recovery can be a later enhancement.
- Generation-time tombstones are honored by the worker, but this delivery does not add a new public outline-edit endpoint beyond the frozen API surface.
- HTML is the visual truth; PPTX remains editable and may vary with host fonts.
