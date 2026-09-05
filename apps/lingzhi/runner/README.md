# Formal code runner

This service is the only supported path for grading formal code-submission
questions. The main FastAPI process must never execute hidden tests.

## Runtime contract

- Internal endpoints require `FORMAL_RUNNER_TOKEN`.
- Supported languages are Python and JavaScript.
- Hidden tests are registered before publication; the main application stores
  only `test_bundle_id`, its SHA-256 digest, and the test count.
- Every hidden test starts a new OCI container with networking disabled,
  a read-only root filesystem, non-root UID, all Linux capabilities removed,
  `no-new-privileges`, CPU/memory/process/time limits, and a 32 KB output cap.
- Results expose counts, failure categories, and resource usage only. Hidden
  input, expected output, and raw program output are never returned.

## Deployment

Use `docker-compose.runner.yml` on a Linux host after setting a long random
`FORMAL_RUNNER_TOKEN` and the Docker socket group ID in `DOCKER_GID`.
Pre-pull the configured Python and JavaScript images before serving traffic.
Keep port 8091 on the private service network.

The compose deployment requires a running Linux Docker engine. If the runner
health check is unavailable, implementation questions fail closed and are not
auto-published; output-prediction and state-trace questions remain available.

Mounting the Docker socket gives this small orchestration service control of
the local engine. Deploy it on a dedicated worker host, keep the API private,
and do not colocate unrelated production workloads on that engine.
