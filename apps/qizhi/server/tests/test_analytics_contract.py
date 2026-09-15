import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from common.models.analytics import (
    AnalyticsBatchIn,
    AnalyticsEventIn,
    AnalyticsEventName,
    sanitize_properties,
)
from common.models.operation_log import PENDING_FEATURE_SLOTS
from infra.db.models.user_operation_log import UserOperationLog
from service.analytics.lifecycle import instrument_stream
from service.analytics.metrics import summarize_events
from service.analytics.service import cleanup_expired_events, ingest_events, record_server_event
from service.operation_log.service import log_operation
from api.analytics import _enforce_rate_limit
from fastapi import HTTPException
from service.admin.dashboard_service import AdminDashboardService


def event(name: str, *, session: str = "session-1", page: str = "page-1", **extra):
    item = {
        "event_name": name,
        "session_id": session,
        "page_instance_id": page,
        "visitor_id": extra.pop("visitor_id", "visitor-1"),
        "duration_ms": extra.pop("duration_ms", None),
        "scroll_depth": extra.pop("scroll_depth", None),
    }
    item.update(extra)
    return item


class AnalyticsContractTests(unittest.TestCase):
    def test_event_contract_strips_query_and_rejects_sensitive_properties(self):
        payload = AnalyticsEventIn(
            event_id="evt-1",
            event_name=AnalyticsEventName.PAGE_VIEW,
            anonymous_id="anon-1",
            session_id="session-1",
            page_instance_id="page-1",
            page_path="/document-analysis?recordId=secret#report",
            occurred_at=datetime.now(timezone.utc),
            properties={"feature": "document_analysis", "file_name": "private.docx"},
        )

        self.assertEqual(payload.page_path, "/document-analysis")
        self.assertEqual(payload.properties, {"feature": "document_analysis"})

        parameterized = payload.model_copy(update={"page_path": "/course/123456789012345678"})
        parameterized = AnalyticsEventIn.model_validate(parameterized.model_dump())
        self.assertEqual(parameterized.page_path, "/course/:id")

    def test_batch_and_numeric_bounds_are_enforced(self):
        valid = {
            "event_id": "evt-1",
            "event_name": "scroll_depth_reached",
            "anonymous_id": "anon-1",
            "session_id": "session-1",
            "page_instance_id": "page-1",
            "occurred_at": datetime.now(timezone.utc),
            "scroll_depth": 75,
        }
        self.assertEqual(len(AnalyticsBatchIn(events=[valid]).events), 1)
        with self.assertRaises(ValueError):
            AnalyticsBatchIn(events=[valid] * 51)
        with self.assertRaises(ValueError):
            AnalyticsEventIn(**{**valid, "scroll_depth": 101})
        with self.assertRaises(ValueError):
            AnalyticsEventIn(**{**valid, "user_id": "spoofed-user"})
        with self.assertRaises(ValueError):
            AnalyticsEventIn(**{**valid, "occurred_at": datetime.now(timezone.utc) + timedelta(hours=1)})
        with self.assertRaises(ValueError):
            AnalyticsEventIn(**{**valid, "event_name": "task_succeeded", "workflow_id": "spoofed-task"})

    def test_property_sanitizer_is_allowlist_based_and_size_bounded(self):
        clean = sanitize_properties({
            "feature": "outline",
            "task_type": "resource_generation",
            "email": "person@example.com",
            "content": "private body",
            "unknown": "ignored",
        })
        self.assertEqual(clean, {"feature": "outline", "task_type": "resource_generation"})

    def test_batch_cannot_mix_anonymous_visitors(self):
        base = {
            "event_name": "page_view",
            "session_id": "session-1",
            "page_instance_id": "page-1",
        }
        with self.assertRaises(ValueError):
            AnalyticsBatchIn(events=[
                {**base, "event_id": "evt-1", "anonymous_id": "anon-1"},
                {**base, "event_id": "evt-2", "anonymous_id": "anon-2"},
            ])

    def test_user_operation_fk_allows_account_deletion_and_active_features_are_not_pending(self):
        fk = next(iter(UserOperationLog.__table__.c.user_id.foreign_keys))
        self.assertEqual(fk.ondelete, "SET NULL")
        self.assertNotIn(("text_analysis", None), PENDING_FEATURE_SLOTS)
        self.assertNotIn(("ppt_analysis", None), PENDING_FEATURE_SLOTS)


class AnalyticsMetricTests(unittest.TestCase):
    def test_summary_computes_engagement_bounce_scroll_and_task_outcomes(self):
        rows = [
            event("page_view", visitor_id="visitor-1"),
            event("page_engagement", visitor_id="visitor-1", duration_ms=4_000),
            event("scroll_depth_reached", visitor_id="visitor-1", scroll_depth=25),
            event("task_started", visitor_id="visitor-1", workflow_id="task-1"),
            event("task_failed", visitor_id="visitor-1", workflow_id="task-1"),
            event("page_view", session="session-2", page="page-2", visitor_id="visitor-2"),
            event("page_engagement", session="session-2", page="page-2", visitor_id="visitor-2", duration_ms=12_000),
            event("scroll_depth_reached", session="session-2", page="page-2", visitor_id="visitor-2", scroll_depth=75),
            event("page_view", session="session-2", page="page-3", visitor_id="visitor-2"),
            event("page_engagement", session="session-2", page="page-3", visitor_id="visitor-2", duration_ms=4_000),
            event("task_started", session="session-2", page="page-3", visitor_id="visitor-2", workflow_id="task-2"),
            event("task_succeeded", session="session-2", page="page-3", visitor_id="visitor-2", workflow_id="task-2", duration_ms=3_000),
        ]

        summary = summarize_events(rows)

        self.assertEqual(summary["page_views"], 3)
        self.assertEqual(summary["unique_visitors"], 2)
        self.assertEqual(summary["sessions"], 2)
        self.assertEqual(summary["engaged_duration_ms"], 20_000)
        self.assertEqual(summary["bounce_rate"], 50.0)
        self.assertEqual(summary["task_completion_rate"], 50.0)
        self.assertEqual(summary["task_failure_rate"], 50.0)
        self.assertEqual(summary["unfinished_tasks"], 0)
        self.assertEqual(summary["scroll_reach"]["75"], 1)

    def test_cancelled_tasks_are_reported_separately_from_failures(self):
        rows = [
            event("task_started", workflow_id="task-1"),
            event("task_cancelled", workflow_id="task-1"),
        ]
        summary = summarize_events(rows)
        self.assertEqual(summary["task_cancelled"], 1)
        self.assertEqual(summary["task_cancellation_rate"], 100.0)
        self.assertEqual(summary["task_failure_rate"], 0.0)


class OperationLogIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_operation_log_commit_rolls_back_shared_session(self):
        class BrokenSession:
            rollback_called = False

            def add(self, _value):
                pass

            async def commit(self):
                raise RuntimeError("database unavailable")

            async def rollback(self):
                self.rollback_called = True

        db = BrokenSession()
        await log_operation(db, user_id="user-1", feature_type="chat", action="send")
        self.assertTrue(db.rollback_called)


class AnalyticsPersistenceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def payload() -> AnalyticsEventIn:
        return AnalyticsEventIn(
            event_id="evt-persist-1",
            event_name="page_view",
            anonymous_id="anon-1",
            session_id="session-1",
            page_instance_id="page-1",
            page_path="/",
        )

    async def test_ingest_reports_accepted_and_duplicate_counts(self):
        class Result:
            rowcount = 1

        class Db:
            committed = False

            async def execute(self, _statement):
                return Result()

            async def commit(self):
                self.committed = True

        db = Db()
        accepted, duplicates = await ingest_events(db, [self.payload()], user_id="user-1")
        self.assertEqual((accepted, duplicates), (1, 0))
        self.assertTrue(db.committed)

    async def test_cleanup_uses_configured_retention_and_commits(self):
        class Result:
            rowcount = 3

        class Db:
            committed = False

            async def execute(self, _statement):
                return Result()

            async def commit(self):
                self.committed = True

        db = Db()
        deleted = await cleanup_expired_events(db, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(deleted, 3)
        self.assertTrue(db.committed)

    async def test_server_event_uses_isolated_session_and_rolls_back_on_failure(self):
        class Db:
            rolled_back = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            def add(self, _value):
                pass

            async def commit(self):
                raise RuntimeError("write failed")

            async def rollback(self):
                self.rolled_back = True

        db = Db()
        with patch("infra.db.database.AsyncSessionLocal", return_value=db):
            await record_server_event(
                event_name="task_failed",
                user_id="user-1",
                workflow_id="workflow-1",
                feature="outline",
                properties={"error_code": "RuntimeError"},
            )
        self.assertTrue(db.rolled_back)

    async def test_ingest_rate_limit_rejects_oversized_minute(self):
        with self.assertRaises(HTTPException) as raised:
            await _enforce_rate_limit("rate-limit-test", 241)
        self.assertEqual(raised.exception.status_code, 429)


class DashboardMetricQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_maps_aggregate_queries_to_public_metric_contract(self):
        now = datetime.now(timezone.utc)

        class Result:
            def __init__(self, *, row=None, scalar=None):
                self._row = row
                self._scalar = scalar

            def one(self):
                return self._row

            def scalar(self):
                return self._scalar

        class Db:
            results = [
                Result(row=(10, 4, 5, 50_000, now)),
                Result(scalar=2),
                Result(row=(4, 2, 1, 1)),
                Result(row=(8, 6, 4, 2)),
            ]

            async def execute(self, _statement):
                return self.results.pop(0)

        metrics = await AdminDashboardService(Db()).get_behavior_metrics(
            now - timedelta(days=7), now
        )
        self.assertEqual(metrics.page_views, 10)
        self.assertEqual(metrics.bounce_rate, 40.0)
        self.assertEqual(metrics.task_completion_rate, 50.0)
        self.assertEqual(metrics.task_cancellation_rate, 25.0)
        self.assertEqual(metrics.scroll_reach["75"], 4)
        self.assertEqual(metrics.unfinished_tasks, 0)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_lifecycle_records_success_with_one_workflow_id(self):
        recorded = []

        async def record(**kwargs):
            recorded.append(kwargs)

        async def source():
            yield "first"
            yield "second"

        values = []
        async for value in instrument_stream(
            source(),
            record=record,
            user_id="user-1",
            feature="outline",
            workflow_id="workflow-1",
        ):
            values.append(value)

        self.assertEqual(values, ["first", "second"])
        self.assertEqual([row["event_name"] for row in recorded], ["task_started", "task_succeeded"])
        self.assertEqual({row["workflow_id"] for row in recorded}, {"workflow-1"})

    async def test_stream_lifecycle_records_failure(self):
        recorded = []

        async def record(**kwargs):
            recorded.append(kwargs)

        async def source():
            yield "first"
            raise RuntimeError("generation failed")

        with self.assertRaises(RuntimeError):
            async for _ in instrument_stream(
                source(), record=record, user_id="user-1", feature="ppt", workflow_id="workflow-2"
            ):
                pass

        self.assertEqual([row["event_name"] for row in recorded], ["task_started", "task_failed"])


if __name__ == "__main__":
    unittest.main()
