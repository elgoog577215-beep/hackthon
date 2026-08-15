## ADDED Requirements

### Requirement: V6 Progress Is Derived From A Persisted Work Manifest
The system SHALL persist `slide_build_progress_v2` work items and SHALL compute progress from completed and total weighted work rather than fixed stage percentages.

#### Scenario: Initial work is known
- **WHEN** the build creates course validation, teaching unit and AI batch items
- **THEN** local items use weight 1 and AI batches use weight 10 by default
- **AND** the event reports completed/total item and weight counts

#### Scenario: Layout allocation discovers pages and assets
- **WHEN** new render pages or assets become known
- **THEN** the manifest adds render items with weight 3 and asset items with weight 5
- **AND** the displayed progress does not decrease

### Requirement: V6 Progress Is Monotonic And Publication Aware
The system SHALL preserve a monotonic displayed percentage and SHALL cap progress at 99% until atomic publication completes.

#### Scenario: Work discovery increases the total
- **WHEN** the computed raw percentage would fall below the previous displayed value
- **THEN** the displayed value remains at the high-water mark
- **AND** events expose newly discovered work instead of hiding the change

#### Scenario: Every quality item is complete but publication is pending
- **WHEN** the registry pointer has not been atomically updated
- **THEN** progress remains at or below 99%
- **AND** only the published terminal event reports 100%

### Requirement: V6 Emits Liveness And Provider Diagnostics
The system SHALL emit an event or heartbeat at least every five seconds while a build is active.

#### Scenario: Story AI is waiting for a provider
- **WHEN** no work item completes for five seconds
- **THEN** a heartbeat reports stage, step, chapter/batch, elapsed time, provider wait and retry state
- **AND** the UI does not appear frozen at a fixed percentage

#### Scenario: A work item fails
- **WHEN** the build reaches a terminal failure
- **THEN** the final event exposes `stage`, `code`, `message`, `retryable` and scoped IDs

### Requirement: V6 Progress Resumes After Disconnect Or Restart
The system SHALL restore progress from the persisted work manifest rather than a frontend-inferred stage table.

#### Scenario: Browser reconnects to an active task
- **WHEN** it reloads task progress
- **THEN** it receives the same item states, high-water percentage and current provider wait context

#### Scenario: Service restarts
- **WHEN** the durable task resumes from stored checkpoints
- **THEN** completed items remain complete and pending items continue
- **AND** progress does not reset to an earlier fixed milestone

#### Scenario: Retryable build failure is resumed
- **WHEN** a V6 build fails with `retryable=true` and its frozen course revision, template digest, mode and theme still match the persisted checkpoint
- **THEN** the same task resumes from the saved work manifest and accepted AI batch outputs
- **AND** only interrupted or failed work items are returned to pending state
- **AND** completed work and the displayed high-water percentage are preserved

#### Scenario: Saved progress is incompatible or incomplete
- **WHEN** a failed task has no persisted V6 checkpoint or progress manifest, or its frozen source/template identity no longer matches
- **THEN** the task is not advertised as resumable
- **AND** a new build is required instead of combining stale progress with changed inputs

#### Scenario: A published deck starts selective visual repair
- **WHEN** the teacher retries degraded V6 pages
- **THEN** the server seeds a new durable work manifest from accepted story and healthy visual checkpoints
- **AND** only target visual batches, materialization, render, quality and atomic publication remain as active work
- **AND** browser refresh restores that repair task by its normal task ID

### Requirement: Frontend Displays Backend Progress Facts
The frontend SHALL render the server-provided V2 work manifest, diagnostics and terminal state and SHALL NOT maintain an independent percentage-by-stage mapping for V6.

#### Scenario: Backend introduces a new work item kind
- **WHEN** the event includes its label, weight and counts
- **THEN** the frontend renders it generically
- **AND** no frontend release is required merely to preserve correct progress arithmetic
