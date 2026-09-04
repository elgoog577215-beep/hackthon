## Why

V5 story planning already executes independent bounded requests with controlled
parallelism, but visual planning still awaits every chapter batch serially. A
representative production chapter therefore continued issuing successful model
requests until the 25-minute workflow ceiling even though the provider returned
no authentication, quota, or rate-limit error. Increasing the workflow timeout
would hide the bottleneck without improving the user-visible generation time.

## What Changes

- Execute independent visual-planning batches with bounded concurrency while
  retaining the existing chapter and page-count isolation boundaries.
- Merge accepted and fallback pages in canonical allocation order regardless of
  provider completion order.
- Record total visual-planning duration, configured and observed concurrency,
  and per-batch timing/status diagnostics.
- Preserve the existing V5 page count, source bindings, visual coverage,
  validation, page-level fallback, and publication quality gates.
- Verify the rule with a non-mathematics course fixture so the optimization
  cannot depend on a particular course, subject, artifact, or chapter shape.

## Capabilities

### Modified Capabilities

- `slide-deck-v5`: visual-planning chapter batches become capacity-bounded
  concurrent work units with deterministic ordered merge and latency telemetry.

## Impact

- Backend: `slide_visuals.plan_slide_visuals` scheduling and diagnostics.
- Configuration: optional `AI_VISUAL_PLAN_CONCURRENCY`, bounded by the compiler.
- Compatibility: no persisted schema or rendered-page contract changes.
- Deployment: one production chapter smoke after all automated gates pass.

