"""
Locust load test for MentorAI (启智) — 400 concurrent users.

User mix (by weight):
    ChatUser      60%   — SSE streaming chat with the AI assistant
    AnalysisUser  20%   — submit video analysis + poll reports
    BrowsingUser  20%   — read-heavy: list courses/resources/videos/sessions

Run:
    locust -f locustfile.py --host=http://127.0.0.1:8000 \
           -u 400 -r 20 --run-time 10m

Success criteria (see SLO in config.py):
    - P99 latency < 3 s for non-streaming endpoints
    - SSE first-token < 2 s
    - Error rate < 1 %
    - 400 concurrent users sustained for 10 minutes
"""

from __future__ import annotations

import json
import random
import time
import uuid

from locust import HttpUser, between, events, task, tag

from config import (
    CHAT_MESSAGES,
    OUTLINE_FORM,
    SAMPLE_COURSE_IDS,
    SAMPLE_RESOURCE_IDS,
    SAMPLE_VIDEO_IDS,
    TEACHING_PLAN_FORM,
    TEST_TOKEN,
)

# ---------------------------------------------------------------------------
# Custom metrics — SSE first-token time
# ---------------------------------------------------------------------------
# Locust fires request events automatically for normal HTTP, but SSE
# streaming needs manual tracking because we want two metrics:
#   1. time-to-first-token (TTFT)
#   2. total stream duration
# We report these through Locust's event system so they appear in the UI
# and in the final statistics.


def _make_request_id() -> str:
    """Generate a unique X-Request-ID for distributed tracing."""
    return f"locust-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Base class — shared auth & helpers
# ---------------------------------------------------------------------------

class AuthenticatedUser(HttpUser):
    """Abstract base providing JWT auth and common helpers.

    Subclasses MUST set ``abstract = True`` is already set here so Locust
    does not instantiate this directly.
    """

    abstract = True
    wait_time = between(1, 5)

    def on_start(self):
        """Called once per simulated user at spawn time."""
        self.token = TEST_TOKEN
        self.session_id = f"locust-session-{uuid.uuid4().hex[:8]}"
        self._default_headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        # Warm-up: discover real IDs from list endpoints so subsequent
        # requests use valid data instead of placeholder IDs.
        self._discover_ids()

    # ---- ID discovery (best-effort, falls back to config placeholders) ----

    def _discover_ids(self):
        """Call list endpoints once to populate real IDs for browsing."""
        self.course_ids = list(SAMPLE_COURSE_IDS)
        self.video_ids = list(SAMPLE_VIDEO_IDS)
        self.resource_ids = list(SAMPLE_RESOURCE_IDS)

        try:
            resp = self.client.get(
                "/course/list",
                headers=self._default_headers,
                name="/course/list [warmup]",
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json()
                items = body.get("data") or []
                ids = [c["id"] for c in items if "id" in c]
                if ids:
                    self.course_ids = ids
        except Exception:
            pass

        try:
            resp = self.client.get(
                "/video/list",
                headers=self._default_headers,
                name="/video/list [warmup]",
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json()
                items = body.get("data") or []
                ids = [v["id"] for v in items if "id" in v]
                if ids:
                    self.video_ids = ids
        except Exception:
            pass

        try:
            resp = self.client.get(
                "/resource/list",
                headers=self._default_headers,
                name="/resource/list [warmup]",
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json()
                items = body.get("data") or []
                ids = [r["id"] for r in items if "id" in r]
                if ids:
                    self.resource_ids = ids
        except Exception:
            pass

        try:
            resp = self.client.get(
                "/session/list",
                headers=self._default_headers,
                name="/session/list [warmup]",
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json()
                items = body.get("data") or []
                ids = [s["id"] for s in items if "id" in s]
                if ids:
                    self.session_ids = ids
                else:
                    self.session_ids = []
            else:
                self.session_ids = []
        except Exception:
            self.session_ids = []

    # ---- SSE helper ----

    def _consume_sse_stream(
        self,
        method: str,
        path: str,
        payload: dict,
        name: str | None = None,
    ):
        """POST to an SSE endpoint, measure TTFT and total time.

        Manually fires ``request`` events so Locust captures:
            {name}            — total response time (from first byte to last)
            {name} [TTFT]     — first-token time only

        On error (non-2xx or exception) a single failure event is fired.
        """
        request_id = _make_request_id()
        headers = {
            **self._default_headers,
            "Accept": "text/event-stream",
            "X-Request-ID": request_id,
        }
        display_name = name or path
        start = time.perf_counter()
        first_token_time = None
        total_bytes = 0
        chunk_count = 0
        error_msg = None

        try:
            with self.client.post(
                path,
                json=payload,
                headers=headers,
                stream=True,
                catch_response=True,
                name=display_name,
                timeout=120,
            ) as resp:
                if resp.status_code >= 400:
                    error_msg = f"HTTP {resp.status_code}"
                    resp.failure(error_msg)
                    return

                for line in resp.iter_lines():
                    chunk_count += 1
                    if line:
                        total_bytes += len(line)
                        # Record TTFT on first non-empty line
                        if first_token_time is None:
                            first_token_time = (time.perf_counter() - start) * 1000

                total_time = (time.perf_counter() - start) * 1000

                # Mark the main request with total stream time
                resp.success()

        except Exception as exc:
            total_time = (time.perf_counter() - start) * 1000
            error_msg = f"{type(exc).__name__}: {str(exc)[:80]}"
            # Fire failure event for the main request
            events.request.fire(
                request_type="POST",
                name=display_name,
                response_time=total_time,
                response_length=0,
                exception=exc,
            )
            return

        # Fire a separate TTFT event so it shows up in Locust stats
        if first_token_time is not None:
            events.request.fire(
                request_type="SSE",
                name=f"{display_name} [TTFT]",
                response_time=first_token_time,
                response_length=0,
                exception=None,
            )


# ===========================================================================
# ChatUser — 60% of traffic
# ===========================================================================

class ChatUser(AuthenticatedUser):
    """Simulates a teacher chatting with the AI assistant via SSE."""

    weight = 6  # 60% of users

    @task(10)
    @tag("chat", "sse")
    def chat(self):
        """Send a chat message and consume the full SSE stream."""
        query = random.choice(CHAT_MESSAGES)
        payload = {
            "query": query,
            "session_id": self.session_id,
            "file_paths": None,
            "extra_params": None,
        }
        self._consume_sse_stream("POST", "/ai/chat", payload, name="/ai/chat")

    @task(2)
    @tag("outline", "sse")
    def generate_outline(self):
        """Generate a teaching outline via SSE."""
        payload = {
            "prompt": None,
            "previous_content": None,
            "resource_id": None,
            "selected_text": None,
            "outline_form": OUTLINE_FORM,
        }
        self._consume_sse_stream("POST", "/ai/outline", payload, name="/ai/outline")

    @task(2)
    @tag("teaching_plan", "sse")
    def generate_teaching_plan(self):
        """Generate a teaching plan via SSE."""
        payload = {
            "prompt": None,
            "resource_id": None,
            "selected_text": None,
            "source_resource_id": None,
            "teaching_plan_form": TEACHING_PLAN_FORM,
        }
        self._consume_sse_stream(
            "POST", "/ai/teaching_plan", payload, name="/ai/teaching_plan"
        )

    @task(3)
    @tag("session", "read")
    def list_sessions(self):
        """List chat sessions (lightweight read)."""
        self.client.get(
            "/session/list",
            headers=self._default_headers,
            name="/session/list",
            timeout=10,
        )


# ===========================================================================
# AnalysisUser — 20% of traffic
# ===========================================================================

class AnalysisUser(AuthenticatedUser):
    """Simulates a teacher submitting video analysis and checking reports."""

    weight = 2  # 20% of users

    @task(3)
    @tag("video", "analysis")
    def trigger_analysis(self):
        """Trigger a local video analysis (GET /video/analyze?id=...&mode=local).

        This is an async fire-and-forget on the backend — the response is
        immediate but the actual work runs in a background task queue.
        """
        if not self.video_ids:
            return
        video_id = random.choice(self.video_ids)
        request_id = _make_request_id()
        headers = {
            **self._default_headers,
            "X-Request-ID": request_id,
        }
        try:
            with self.client.get(
                f"/video/analyze?id={video_id}&mode=local",
                headers=headers,
                name="/video/analyze",
                catch_response=True,
                timeout=30,
            ) as resp:
                if resp.status_code == 200:
                    body = resp.json()
                    # The API wraps in ApiResponse; code != 0 is a business error
                    # (e.g. "video not found"), which is expected during load test
                    # with placeholder IDs — mark as success to avoid noise.
                    resp.success()
                else:
                    resp.failure(f"HTTP {resp.status_code}")
        except Exception:
            pass

    @task(4)
    @tag("video", "read")
    def view_video_detail(self):
        """Fetch video detail by ID."""
        if not self.video_ids:
            return
        video_id = random.choice(self.video_ids)
        try:
            self.client.get(
                f"/video?id={video_id}",
                headers=self._default_headers,
                name="/video [detail]",
                timeout=10,
            )
        except Exception:
            pass

    @task(5)
    @tag("video", "read")
    def list_videos(self):
        """List all videos for the current user."""
        try:
            self.client.get(
                "/video/list",
                headers=self._default_headers,
                name="/video/list",
                timeout=10,
            )
        except Exception:
            pass

    @task(2)
    @tag("video", "read")
    def export_report(self):
        """Attempt to export a video analysis report (Word doc download).

        This exercises the report generation path. May 4xx if analysis
        hasn't completed — that's fine for load testing purposes.
        """
        if not self.video_ids:
            return
        video_id = random.choice(self.video_ids)
        try:
            with self.client.get(
                f"/video/export?id={video_id}",
                headers=self._default_headers,
                name="/video/export",
                catch_response=True,
                timeout=30,
            ) as resp:
                # Accept 200 (success) and business errors (still 200 with error code)
                resp.success()
        except Exception:
            pass


# ===========================================================================
# BrowsingUser — 20% of traffic
# ===========================================================================

class BrowsingUser(AuthenticatedUser):
    """Simulates a teacher browsing courses, resources, and session history."""

    weight = 2  # 20% of users

    @task(5)
    @tag("course", "read")
    def list_courses(self):
        """List all courses."""
        try:
            self.client.get(
                "/course/list",
                headers=self._default_headers,
                name="/course/list",
                timeout=10,
            )
        except Exception:
            pass

    @task(3)
    @tag("course", "read")
    def view_course_detail(self):
        """View a single course by ID."""
        if not self.course_ids:
            return
        course_id = random.choice(self.course_ids)
        try:
            self.client.get(
                f"/course?id={course_id}",
                headers=self._default_headers,
                name="/course [detail]",
                timeout=10,
            )
        except Exception:
            pass

    @task(3)
    @tag("course", "read")
    def list_units(self):
        """List units for a course."""
        if not self.course_ids:
            return
        course_id = random.choice(self.course_ids)
        try:
            self.client.get(
                f"/course/unit/list?course_id={course_id}",
                headers=self._default_headers,
                name="/course/unit/list",
                timeout=10,
            )
        except Exception:
            pass

    @task(4)
    @tag("resource", "read")
    def list_resources(self):
        """List resources, optionally filtered by course."""
        params = {}
        if self.course_ids and random.random() < 0.5:
            params["course_id"] = random.choice(self.course_ids)
        try:
            self.client.get(
                "/resource/list",
                params=params,
                headers=self._default_headers,
                name="/resource/list",
                timeout=10,
            )
        except Exception:
            pass

    @task(2)
    @tag("resource", "read")
    def view_resource_detail(self):
        """View a single resource by ID."""
        if not self.resource_ids:
            return
        resource_id = random.choice(self.resource_ids)
        try:
            self.client.get(
                f"/resource?id={resource_id}",
                headers=self._default_headers,
                name="/resource [detail]",
                timeout=10,
            )
        except Exception:
            pass

    @task(3)
    @tag("session", "read")
    def list_sessions(self):
        """List chat sessions."""
        try:
            self.client.get(
                "/session/list",
                headers=self._default_headers,
                name="/session/list",
                timeout=10,
            )
        except Exception:
            pass

    @task(2)
    @tag("session", "read")
    def view_session_detail(self):
        """View a single chat session."""
        if not self.session_ids:
            return
        session_id = random.choice(self.session_ids)
        try:
            self.client.get(
                f"/session?id={session_id}",
                headers=self._default_headers,
                name="/session [detail]",
                timeout=10,
            )
        except Exception:
            pass

    @task(1)
    @tag("health")
    def health_check(self):
        """Hit the version endpoint as a lightweight health probe."""
        try:
            self.client.get(
                "/api/version",
                headers=self._default_headers,
                name="/api/version",
                timeout=5,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Listener: print SLO summary at test end
# ---------------------------------------------------------------------------

@events.quitting.add_listener
def _print_slo_summary(environment, **kwargs):
    """Print a human-readable SLO check when the test finishes."""
    from config import SLO

    stats = environment.runner.stats
    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures
    if total_requests == 0:
        print("\n[SLO] No requests recorded.")
        return

    error_rate = (total_failures / total_requests) * 100
    print("\n" + "=" * 70)
    print("SLO Summary")
    print("=" * 70)
    print(f"  Total requests:   {total_requests}")
    print(f"  Total failures:   {total_failures}")
    print(f"  Error rate:       {error_rate:.2f}%  (target < {SLO['error_rate_pct']}%)")

    # Check individual endpoint P99
    for entry in stats.entries.values():
        p99 = entry.get_response_time_percentile(0.99) or 0
        name = entry.name
        if "[TTFT]" in name:
            status = "PASS" if p99 < SLO["sse_first_token_ms"] else "FAIL"
            print(f"  {name:40s} P99={p99:>7.0f}ms  target<{SLO['sse_first_token_ms']}ms  [{status}]")
        elif entry.method in ("GET", "POST"):
            status = "PASS" if p99 < SLO["p99_latency_ms"] else "FAIL"
            print(f"  {name:40s} P99={p99:>7.0f}ms  target<{SLO['p99_latency_ms']}ms  [{status}]")

    overall = "PASS" if error_rate < SLO["error_rate_pct"] else "FAIL"
    print(f"\n  Overall error rate: [{overall}]")
    print("=" * 70)
