## 1. Freeze the data contract

- [x] 1.1 Separate product usage signals from LearningEvent, task state, and generation telemetry
- [x] 1.2 Define the V1 event/property allow-list and privacy exclusions
- [x] 1.3 Define KPIs, aggregation time, retention, capacity, and governance boundaries

## 2. Implement the backend ledger

- [x] 2.1 Add append-only, idempotent UsageEvent storage with bounded retention
- [x] 2.2 Add strict batch ingestion and per-user summary/export/delete routes
- [x] 2.3 Add token-protected global aggregate summary without raw cross-user export
- [x] 2.4 Register the router and isolate test writes from repository data

## 3. Implement unified frontend collection

- [x] 3.1 Add a bounded retry queue, stable tab session, and identity-aware batch sender
- [x] 3.2 Track successful route navigation without query strings or dynamic route values
- [x] 3.3 Track all Axios mutation outcomes with sanitized API route templates
- [x] 3.4 Track only classified client errors and provide a complete client-side off switch

## 4. Verify and document

- [x] 4.1 Add backend contract, privacy, aggregation, retention, and governance tests
- [x] 4.2 Add frontend tracker and HTTP integration tests
- [x] 4.3 Update architecture and product status with the new data layer and known limits
- [x] 4.4 Run focused backend/frontend tests, build, OpenSpec validation, and diff checks
