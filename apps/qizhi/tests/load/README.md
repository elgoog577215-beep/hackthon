# MentorAI Load Test (Locust)

Pressure test for 400 concurrent users against the MentorAI backend.

## Quick start

```bash
pip install locust
cd tests/load
locust -f locustfile.py --host=http://127.0.0.1:8000 -u 400 -r 20 --run-time 10m
```

Open the Locust web UI at http://localhost:8089 to monitor in real time.

### Headless mode (no UI)

```bash
locust -f locustfile.py --host=http://127.0.0.1:8000 \
       -u 400 -r 20 --run-time 10m --headless \
       --csv=results/run1
```

Results are written to `results/run1_stats.csv`, `results/run1_failures.csv`, etc.

## User mix

| User class   | Weight | Traffic share | Behavior                                     |
|:-------------|:------:|:-------------:|:---------------------------------------------|
| ChatUser     |   6    |     60%       | SSE streaming chat, outline, teaching plan   |
| AnalysisUser |   2    |     20%       | Trigger video analysis, view reports         |
| BrowsingUser |   2    |     20%       | List courses, resources, videos, sessions    |

## Authentication

The test uses a pre-generated JWT token in `config.py`.  Before running:

1. Obtain a fresh token from the DEV environment:
   ```bash
   curl -X POST "http://127.0.0.1:8000/auth/test-login?name=LoadTest&zju_id=loadtest001"
   ```
2. Copy the token from the `data` field of the response into `config.py` → `TEST_TOKEN`.

All simulated users share the same token (single test account).  This is intentional — the goal is backend capacity testing, not auth-system stress.

## SSE streaming metrics

SSE endpoints (chat, outline, teaching_plan) report two custom metrics:

- **`/ai/chat`** — total stream time (measured by Locust's built-in timer)
- **`/ai/chat [TTFT]`** — time to first token, reported as a separate `SSE` request type

These appear as separate rows in the Locust statistics table.

## Success criteria (SLOs)

| Metric                      | Target          |
|:----------------------------|:----------------|
| P99 latency (non-streaming) | < 3 000 ms      |
| SSE first-token time        | < 2 000 ms      |
| Error rate                  | < 1%            |
| Concurrent users            | 400 sustained   |
| Duration                    | 10 minutes      |

An SLO summary is printed to stdout when the test finishes.

## Configuration

Edit `config.py` to change:

- `TARGET_HOST` — backend address
- `TEST_TOKEN` — JWT auth token
- `CHAT_MESSAGES` — sample chat queries
- `OUTLINE_FORM` / `TEACHING_PLAN_FORM` — form data for generation endpoints
- `SAMPLE_*_IDS` — fallback entity IDs (the test auto-discovers real IDs on start)
- `SLO` — performance targets

## Running specific user types

```bash
# Only chat users
locust -f locustfile.py --host=http://127.0.0.1:8000 -u 100 -r 10 --tags chat

# Only read-heavy browsing
locust -f locustfile.py --host=http://127.0.0.1:8000 -u 200 -r 20 --tags read
```

## Distributed mode (multiple machines)

```bash
# On the master
locust -f locustfile.py --master --host=http://127.0.0.1:8000

# On each worker
locust -f locustfile.py --worker --master-host=<master-ip>
```
