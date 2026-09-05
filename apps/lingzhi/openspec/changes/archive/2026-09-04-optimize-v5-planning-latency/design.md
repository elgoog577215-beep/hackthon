## Context

The visual planner receives source-bounded batches that never mix chapters and
already validates each page independently. Those batches have no data dependency
on one another, yet the orchestration loop waits for each provider response
before starting the next. With typical model latency near 45 seconds, many
successful batches consume the entire end-to-end workflow budget.

## Goals / Non-Goals

**Goals:**

- Reduce wall-clock visual-planning time without reducing output quality.
- Keep provider load bounded and configurable.
- Preserve deterministic page ordering and isolated fallback semantics.
- Expose enough timing evidence to distinguish provider failure from capacity
  exhaustion.

**Non-Goals:**

- Reduce the number of source pages, required visuals, or subject artifacts.
- Disable AI visual planning for long decks.
- Add course-, subject-, formula-, asset-, or fixed-chapter special cases.
- Introduce a cross-user or cross-course model-response cache.

## Decisions

### Decision: Only independent visual batches execute concurrently

The existing `_visual_plan_batches` output remains the semantic and failure
isolation boundary. The scheduler uses an effective concurrency equal to the
smaller of batch count and configured capacity, clamped to the shared
provider's normal capacity range. No page within a batch is split or omitted
for latency.

### Decision: Provider completion order does not own deck order

Each task returns accepted pages, failures, and diagnostics without mutating the
final plan. The coordinator consumes task results in batch-index order and then
reconstructs pages in allocation order. Therefore different response timing
cannot reorder the deck or alter source ownership.

### Decision: Quality and fallback contracts remain unchanged

Every provider page still passes the existing source and topology validators.
Invalid pages retain deterministic source-bound visuals, one failed batch does
not invalidate accepted batches, and the same final V5 quality gate runs after
planning. Exceeding the planning budget may fail explicitly; it never triggers
V3/V4 output or silent content removal.

### Decision: Telemetry is attached to the visual plan and logs

The planner records total duration, configured concurrency, observed peak
concurrency, and ordered per-batch duration/status records. Start and completion
logs expose the stage even when an outer workflow has a hard timeout.

## Risks / Trade-offs

- Higher concurrency can increase provider pressure. The default is two and
  the compiler clamps configuration to four, matching the shared provider
  controller's default initial and maximum limits.
- Batch timing includes semaphore wait time, which represents user-visible
  latency but not pure provider latency. Provider request logs remain the source
  for transport-only timing.
- Concurrent failures can finish in a different order. Ordered aggregation keeps
  diagnostics and page output deterministic.

## Verification

- A non-mathematics software-delivery course proves multiple batches overlap,
  complete out of order, and still produce allocation-ordered pages.
- Existing long-deck, partial-failure, source-binding, visual-quality, V5
  compilation, export, and production-smoke tests remain green.
- Static review rejects course titles/IDs, fixed formulas/assets, and fixed
  chapter-structure branches.
