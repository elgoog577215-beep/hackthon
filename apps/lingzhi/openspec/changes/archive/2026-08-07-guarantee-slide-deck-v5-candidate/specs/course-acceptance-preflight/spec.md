## ADDED Requirements

### Requirement: PPT Source Preflight Produces A Read-Only Contract

The acceptance preflight SHALL produce `ppt_source_contract_v1` without
mutating course content or silently converting it to a legacy format.

#### Scenario: A new-chain course is valid for V5
- **WHEN** the canonical document, ordered blocks, course logic, references, and source revision are available
- **THEN** preflight marks the course eligible for a schema-closed V5 build
- **AND** records the immutable source revision used by the build

#### Scenario: Required V5 source facts are missing
- **WHEN** preflight cannot establish canonical ordering, course logic, reference identity, or source revision
- **THEN** it returns explicit blocker codes
- **AND** does not make the course appear eligible by downgrading to V3 or V4 assumptions

