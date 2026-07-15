# HANDOFF: Frontend courseware workbench

## File ownership respected

Only the delegated frontend presentation surface and this handoff were edited:

- `frontend/src/services/presentations.ts`
- `frontend/src/stores/presentation.ts`
- `frontend/src/composables/usePresentationEvents.ts`
- `frontend/src/views/PresentationStudioView.vue`
- `frontend/src/components/presentation/PresentationPreview.vue`
- `frontend/src/components/presentation/PresentationAiAside.vue`
- `frontend/src/components/presentation/PresentationPatchProposal.vue`
- `frontend/src/components/presentation/PresentationQualityPanel.vue`
- `frontend/src/__tests__/presentation/service.test.ts`
- `frontend/src/__tests__/presentation/preview.test.ts`
- `frontend/src/__tests__/stores/presentation.test.ts`

Shared router, App shell, learning entry, course library and backend files were not edited by this worker.
Two `output/playwright/*.png` files are verification artifacts, not source edits. Temporary Playwright CLI snapshots created by this worker were removed after the screenshots were captured.

## Implemented contract

- Dedicated presentation service for create/list/get, fetch-SSE generate/replay, proposal/apply, restore, finalize and receipt-bound artifact URLs.
- Independent Pinia reducer with `activeGenerationId`, `lastSequence`, duplicate/old-generation rejection, sequence-gap refresh, and `slide_id` upsert. Failed requests keep the last deck/revision instead of fabricating local persistence.
- Generation and export remain separate: `generation_complete` enters editing; only a current, non-stale artifact receipt enables download.
- Proposal flow is explicit `propose -> diff -> apply/cancel -> append revision`; `409` marks a proposal stale and does not mutate the deck. Undo calls server restore and never rewinds a local pointer.
- Approved workbench surface: independent toolbar and hierarchy bar, large left preview, fixed 400px right AI, original light Lingzhi styling and original-size quick actions. No rejected brand header, dark code card or three-column thumbnail variant was added.
- `srcdoc` preview escapes all deck text and runs in an opaque-origin `sandbox="allow-scripts"` frame. Message acceptance checks exact iframe source, opaque `null` origin, channel version, deck id, revision id and revision checksum. Typed overflow/collision/slide-count measurements are passed to finalize only while still bound to that revision checksum.
- Below 1180px, Preview/AI is a one-surface switch implemented with `v-show`, so deck and selected slide state survive switching.

## API response boundary

The client consumes the shared response envelope:

```text
{ deck, revision, revision_checksum, working?, quality?, artifact? }
```

List accepts either `PresentationDeck[]` or `{ decks }`. SSE event payloads consumed are `deck_outline:{slide_order,slides}`, `slide_upsert:{slide}`, `quality_report:{report}`, `generation_complete:{revision}` and `export_ready:{artifact}`. Artifact UI needs `artifact_id/deck_id/revision_id/page_count/stale`; URLs are constructed through the receipt-bound artifact routes, so filesystem paths are never accepted from the API.

The backend worker confirmed this envelope in its router and subsequently added the required top-level `revision_checksum`; `generation_complete` carries the same field in its payload. Apply/restore may include an extra command receipt, and finalize may include `event=export_ready`; these additive fields are intentionally ignored by the reducer after the authoritative deck/revision/checksum/quality/artifact snapshot is applied.

## Verification

- `npm test -- --run src/__tests__/presentation src/__tests__/stores/presentation.test.ts` — PASS, 3 files / 13 tests, including opaque-frame validation, checksum-bound measurement, stale-measurement invalidation, finalize wait gate and structured quality failure rendering.
- `npm run build` — PASS (`vue-tsc -b && vite build`). Existing Browserslist-age and large-chunk warnings remain non-blocking.
- Real-browser desktop route at 5173 — workbench toolbar, empty preview and 400px configuration aside rendered; no duplicate global header.
- Real-browser 960px route — Preview/AI switch rendered and successfully switched to AI without route reload.
- Screenshots:
  - `output/playwright/presentation-studio-config-desktop.png`
  - `output/playwright/presentation-studio-narrow-ai.png`

The browser observed one expected 404 from the still-running pre-integration backend process. The UI showed the explicit service error and did not create localStorage/mock deck data.

## Integration notes / risks

- Main task must keep route names/paths consistent with `/course/:courseId/deck` and `/course/:courseId/deck/:deckId`; the view itself uses paths, not a private route name.
- The active backend process must be restarted after router registration before browser E2E; the 404 above is not a frontend fallback.
- If the final backend returns a raw manifest instead of the frozen response envelope, adapt the service once at its boundary; do not spread response-shape branching through components.
- `srcdoc` deliberately remains opaque-origin with `sandbox="allow-scripts"`; it posts to `*` because opaque frames cannot target the parent origin, while the parent requires exact `event.source`, `event.origin === "null"`, channel/deck/revision/checksum matches before accepting a message. All injected slide content is HTML-escaped and no model-provided CSS/script is accepted.
- Every snapshot and `generation_complete` event carries `revision_checksum`. A revision/checksum transition clears the old render measurement; finalize is not sent until the preview reports a typed measurement for the current pair.
