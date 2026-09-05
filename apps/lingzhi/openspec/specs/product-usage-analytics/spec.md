# product-usage-analytics Specification

## Purpose
Define a privacy-safe, idempotent usage-event ledger for product analytics that remains independent from learning evidence, task state, and business data.
## Requirements
### Requirement: Product usage signals have an independent event ledger

The system SHALL persist product usage signals as versioned `UsageEvent` records independent
from `LearningEvent`, generation telemetry, task state, and domain objects. Usage events SHALL
NOT change learner state, course state, permissions, billing, or task terminal state.

#### Scenario: A learner opens a course page
- **WHEN** the frontend records the completed route navigation
- **THEN** the system appends one `page_viewed` UsageEvent for that identity and session
- **AND** no LearningEvent or learner projection is created from the page view

### Requirement: Collection uses strict privacy-safe contracts

The system SHALL accept only registered event names, allow-listed scalar properties, stable route
names, sanitized API route templates, bounded IDs, and coarse client context. It SHALL reject
unknown properties and SHALL NOT persist course content, answers, prompts, error messages, stacks,
URL queries, IP addresses, User-Agent strings, cookies, or device fingerprints.

#### Scenario: A client includes free-form content
- **WHEN** an event contains an unregistered property or a nested value
- **THEN** ingestion rejects the event
- **AND** the value is not persisted

### Requirement: Collection is idempotent and cannot block product work

The system SHALL de-duplicate retries by calling identity and `client_event_id`. Frontend collection
SHALL be best-effort, bounded, and isolated from formal HTTP request results.

#### Scenario: The same batch is retried
- **WHEN** a user submits an already accepted `client_event_id`
- **THEN** the original event is returned as a duplicate
- **AND** aggregate counts do not increase

#### Scenario: The analytics endpoint is unavailable
- **WHEN** a formal course or learning request completes while usage collection fails
- **THEN** the formal request retains its original result
- **AND** the bounded usage queue may retry later without showing a product error

### Requirement: Page and mutation coverage is centralized

The frontend SHALL record successful final route navigation and the terminal outcome of Axios
`POST`, `PUT`, `PATCH`, and `DELETE` requests through shared infrastructure. It SHALL NOT record
high-frequency reads, polling, scrolling, pointer movement, or keystrokes.

#### Scenario: A write API fails
- **WHEN** a mutation request returns an HTTP or network failure
- **THEN** the tracker records `api_action_failed` with method, sanitized route template,
  status code when known, and bounded duration
- **AND** it does not record request/response bodies or the error message

### Requirement: Usage records are retained within explicit bounds

The system SHALL enforce a configurable retention period and maximum record count. Aggregations
SHALL use server `received_at` rather than client time.

#### Scenario: New events exceed a retention or capacity bound
- **WHEN** a batch is appended
- **THEN** expired records are removed and only the configured most recent capacity is retained
- **AND** current accepted events remain queryable unless the configured capacity itself is exceeded

### Requirement: Users govern their own raw usage records

A stable request identity under the current `X-User-Id` boundary SHALL be able to summarize,
export, and hard-delete only its own UsageEvents. A caller SHALL NOT be able to select another
identity in the request body or query. This boundary SHALL NOT be described as stronger tenant
authentication until the product has a real account/session authority.

#### Scenario: One user exports usage records
- **WHEN** the user calls the export route
- **THEN** only records owned by the request identity are returned

#### Scenario: One user deletes usage records
- **WHEN** the user confirms deletion
- **THEN** all server-side UsageEvents owned by that identity are hard-deleted
- **AND** another user's records remain unchanged

### Requirement: Cross-user analytics is aggregate-only and protected

The system SHALL expose global usage summary only when a configured analytics admin token matches
the request. The global endpoint SHALL return counts and grouped metrics, not raw cross-user events.

#### Scenario: No analytics admin token is configured
- **WHEN** a caller requests the global summary
- **THEN** the endpoint is unavailable
- **AND** no aggregate or raw event data is returned
