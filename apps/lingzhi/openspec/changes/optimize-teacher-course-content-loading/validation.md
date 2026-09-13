# Validation

## Initial evidence

- Production version before this change: `f92582f404ccb8dd9d46e7dd00604d129b5a7dc1`.
- Representative course: `afb29754-6842-437b-af1b-5866bfb53b41`.
- Browser evidence: `D:/lingzhi/.codex_tmp/course-open-20260913/course-production-final-cold-browser.json`.
- Workspace shell visible: 5.53 s.
- Blueprint response complete: 12.84 s from navigation.
- Full lesson-authoring response complete: 14.93 s from navigation.
- This evidence is a production read-only sample, not a controlled load test or strict server cold-cache benchmark.

## Required evidence per batch

- Exact commit, CI run, deployed version and rollback target.
- Browser timings for target text readable and editor enabled, with sample count and failures.
- Request list proving unused full-content endpoints are absent from the critical path.
- Authorization, revision conflict, task recovery, stale response and last-good regression results.
- Server timing breakdown and response sizes without content or identity-sensitive logs.
