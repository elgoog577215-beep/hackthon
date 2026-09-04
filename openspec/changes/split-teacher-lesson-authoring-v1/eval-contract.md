# Eval Contract

## Hard Gates

1. A teacher request for N lessons produces exactly N top-level lesson units and never silently changes N.
2. A structurally valid complete outline becomes the current editable revision and starts no lesson-plan, script or release task.
3. Starting lesson 2 creates one teacher lesson-plan task scoped to lesson 2 and all its child sections; sibling lessons remain unchanged.
4. A retryable provider failure affects only the current lesson. Its checkpoint remains recoverable but cannot become the current asset or unlock downstream generation until the result is complete and structurally valid.
5. `lesson` and `section` route state are independent; clicking next changes visible content and survives reload.
6. Manual edit and AI candidate acceptance create teacher lesson-plan revisions without writing student CourseDocument blocks.
7. A usable lesson-plan revision can generate the current script; a usable script can generate the lesson-scoped PPT without student content/publication, and the deck records both exact source revisions.
8. Existing student routes, course generation, content, practice, notes, AI teacher and PPT regression tests remain passing.
9. Frontend build and relevant backend tests pass; real browser console has no new error on verified teacher/student routes.
10. No `.env`, secret, runtime JSON, generated export, lockfile or unrelated dirty file enters the source diff.

## Evidence Mapping

| Gate | Direct evidence |
| --- | --- |
| hard lesson count | request/outline backend test + teacher creation browser flow |
| outline stop | task state/API test; absence of teaching/content tasks |
| lesson task isolation | repository/task tests for lesson 2 and unchanged siblings |
| fallback policy | provider/validation fixture retaining a retryable checkpoint without creating a current asset or downstream-ready source |
| navigation | component/router test + browser 2.1→2.2→2.3 and reload |
| edit/AI | candidate diff/accept/reject API and UI tests |
| lesson PPT | source contract test + browser generation/return path |
| student preservation | existing student route/store/component/backend suites |
| runtime UI | Playwright screenshots/snapshots, console and requests |

## Stop Rule

Any student regression, teacher write into student CourseDocument, cross-lesson retry, unstable lesson/section identity or PPT dependency on student content blocks the change. A partial implementation must be reported as partial and must not be labelled complete.
