## ADDED Requirements

### Requirement: Quality-blocked learning assets can be repaired without regenerating course text
The system MUST expose an explicit repair operation only for a retained generation workspace whose L2 nodes are complete, whose publication is blocked, and whose blocking issues are limited to missing required `misconceptions` assets. The operation MUST preserve course text, blueprint fields and non-empty misconceptions.

#### Scenario: Missing misconceptions block an otherwise complete course
- **WHEN** a course has completed L2 nodes and its only blocking asset issue is an empty required `misconceptions` asset
- **THEN** the task MUST be eligible for a quality-repair operation
- **AND** the operation MUST NOT invoke normal node-content generation

#### Scenario: Other failures remain outside the repair scope
- **WHEN** a task has failed nodes, provider failure, a version conflict, or another blocking asset issue
- **THEN** the quality-repair operation MUST reject the request with its existing recovery or quality reason

### Requirement: Repair output must be validated and safely published
The repair operation MUST generate non-empty node-local misconception statements through the configured AI service, recompile the learning asset bundle, and rerun the existing final publication gate. It MUST publish only when that gate passes.

#### Scenario: Repair satisfies every blocking gate
- **WHEN** generated misconceptions pass validation and the recompiled asset report has no blocking issues
- **THEN** the system MUST publish the retained workspace through the existing publication path
- **AND** the task MUST report a completed, publishable result

#### Scenario: Repair does not resolve all blockers
- **WHEN** generation fails, output is invalid, or rechecking still reports a blocker
- **THEN** the system MUST keep the workspace unpublished
- **AND** return the updated exact diagnostics to the task center

### Requirement: Task center exposes the constrained repair action
The task center MUST show an “自动补齐并重新检查” action only when the server marks a quality-blocked task as repairable. It MUST show repair progress and the returned quality diagnostics.

#### Scenario: User starts an eligible repair
- **WHEN** the user activates the repair action on an eligible task
- **THEN** the client MUST request the dedicated repair endpoint and refresh the server task state
- **AND** the client MUST NOT present the action as a generic retry or full course regeneration
