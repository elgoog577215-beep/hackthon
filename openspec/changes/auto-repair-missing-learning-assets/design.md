## Context

`compile_learning_assets` deterministically projects node fields into assets. It does not generate absent `misconceptions`; a quality-blocked workspace therefore cannot become publishable without changing its node data. Existing recovery intentionally rejects a normal resume for this state.

## Goals / Non-Goals

**Goals:**
- Add one explicit, idempotent quality-repair action for a retained quality-blocked workspace.
- Generate only missing node misconceptions through the configured course AI service.
- Recompile, recheck and publish only if the existing publication gate passes.
- Keep the original node content and every already-present misconception unchanged.

**Non-Goals:**
- Do not lower the required-asset gate, regenerate course text, repair model/network failures, or offer general manual asset editing.

## Decisions

1. **Use a dedicated quality-repair endpoint rather than normal resume.** This retains the recovery contract: normal resume repairs incomplete nodes; quality repair repairs only diagnosed assets.
2. **Mutate the retained workspace in place with an audit entry.** It avoids copying large generated text and preserves the task/course identity visible to the user. The operation is rejected if a repair is already active or any node failed.
3. **Use the existing configured CourseService LLM for missing misconceptions.** The prompt is constrained to JSON and node-local facts. A deterministic generic fallback is rejected because it would satisfy counts while providing low-value learning guidance.
4. **Allow one repair pass per quality-blocked task.** A second failure remains visible with the exact diagnostics; this prevents endless provider calls.

## Risks / Trade-offs

- [Provider unavailable] → leave the workspace unpublished, record a repair-specific failure and allow a later explicit retry.
- [Model returns malformed or empty results] → validate per-node non-empty strings before saving; rerun the existing quality gate.
- [Concurrent clicks] → reject while the task is pending/running or has an active repair marker.
- [Overbroad mutation] → preserve all content fields and only fill empty `misconceptions` arrays.

## Migration Plan

No data migration. Existing retained quality-blocked workspaces become eligible only when their blockers are exclusively missing `misconceptions` and all L2 nodes completed. Rollback removes the endpoint/button; retained workspaces stay unpublished.

## Open Questions

Manual curation is deferred until users need to override generated misconception wording.
