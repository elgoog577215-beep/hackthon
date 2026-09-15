import asyncio
import unittest
from datetime import datetime, timezone

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
from service.operation_log.service import log_operation


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

    def test_property_sanitizer_is_allowlist_based_and_size_bounded(self):
        clean = sanitize_properties({
            "feature": "outline",
            "task_type": "resource_generation",
            "email": "person@example.com",
            "content": "private body",
            "unknown": "ignored",
        })
        self.assertEqual(clean, {"feature": "outline", "task_type": "resource_generation"})

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
        self.assertEqual(summary["scroll_reach"]["75"], 1)


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
