## MODIFIED Requirements

### Requirement: Long Deck Visual Planning Is Chapter-Batched

The system SHALL split visual planning into bounded chapter batches instead of
disabling AI for the entire long deck. Independent batches SHALL execute with a
bounded concurrency budget, and their results SHALL be merged in canonical
allocation order without changing page count, source ownership, visual quality
requirements, or final publication gates.

#### Scenario: Independent visual batches complete out of order
- **WHEN** multiple source-bounded chapter batches are eligible for planning
- **THEN** the planner executes no more than the configured bounded concurrency
- **AND** final pages and diagnostics are merged in batch and allocation order

#### Scenario: One visual batch fails
- **WHEN** other chapter batches return valid source-bound plans
- **THEN** accepted batches remain AI planned
- **AND** only the failed batch uses deterministic pages with explicit diagnostics

#### Scenario: Latency optimization is applied to a long deck
- **WHEN** the planner reduces wall-clock waiting through concurrent scheduling
- **THEN** it does not remove source pages, required subject artifacts, or visual checks
- **AND** it records total duration, configured and observed concurrency, and
  per-batch duration and status

