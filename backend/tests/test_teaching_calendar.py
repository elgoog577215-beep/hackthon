import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import teaching_calendar as teaching_calendar_router
from teaching_calendar import TeachingCalendarConflict, TeachingCalendarRepository


class TeachingCalendarRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = TeachingCalendarRepository(Path(tempfile.mkdtemp()))

    def test_persists_sessions_and_isolates_owner(self):
        saved = self.repository.save(
            "teacher-a",
            "course-1",
            {
                "course_title": "设计思维",
                "academic_year": "2025-2026",
                "term": "春夏",
                "sessions": [
                    {
                        "content_summary": "设计思维导论",
                        "date": "2026-03-02",
                        "status": "scheduled",
                    }
                ],
            },
            0,
        )

        self.assertEqual(saved["revision"], 1)
        self.assertTrue(saved["sessions"][0]["session_id"].startswith("tcsess-"))
        self.assertEqual(self.repository.load("teacher-a", "course-1")["sessions"][0]["content_summary"], "设计思维导论")
        self.assertEqual(self.repository.load("teacher-b", "course-1")["sessions"], [])

    def test_rejects_stale_revision(self):
        self.repository.save("teacher-a", "course-1", {"sessions": []}, 0)

        with self.assertRaises(TeachingCalendarConflict) as context:
            self.repository.save("teacher-a", "course-1", {"sessions": []}, 0)

        self.assertEqual(context.exception.current_revision, 1)

    def test_total_calendar_filters_dates_and_cancelled_sessions(self):
        self.repository.save(
            "teacher-a",
            "course-1",
            {
                "course_title": "设计思维",
                "sessions": [
                    {"content_summary": "第一讲", "date": "2026-03-02", "status": "scheduled"},
                    {"content_summary": "第二讲", "date": "2026-03-09", "status": "cancelled"},
                    {"content_summary": "第三讲", "date": "2026-04-06", "status": "scheduled"},
                ],
            },
            0,
        )

        rows = self.repository.list_sessions("teacher-a", date(2026, 3, 1), date(2026, 3, 31))

        self.assertEqual([row["content_summary"] for row in rows], ["第一讲"])


class TeachingCalendarRouteTests(unittest.TestCase):
    def setUp(self):
        self.repository = TeachingCalendarRepository(Path(tempfile.mkdtemp()))
        app = FastAPI()
        app.include_router(teaching_calendar_router.router, prefix="/api")
        self.client = TestClient(app)
        self.course = {
            "course_id": "course-1",
            "course_name": "设计思维",
            "document_revision": "outline-r3",
            "nodes": [
                {"node_id": "chapter-1", "parent_node_id": "", "node_name": "第一章", "node_level": 1},
                {"node_id": "lesson-1", "parent_node_id": "chapter-1", "node_name": "第一讲 导论", "node_level": 2, "learning_objective": "理解设计思维"},
                {"node_id": "lesson-2", "parent_node_id": "chapter-1", "node_name": "第二讲 共情", "node_level": 2},
            ],
        }

    def _patches(self):
        async def fake_get_course(course_id: str):
            if course_id != "course-1":
                raise AssertionError("unexpected course")
            return self.course

        return (
            patch.object(teaching_calendar_router, "teaching_calendar_repository", self.repository),
            patch.object(teaching_calendar_router, "get_course_or_404", fake_get_course),
        )

    def test_save_conflict_and_derive_candidate_without_overwrite(self):
        repository_patch, course_patch = self._patches()
        headers = {"X-User-Id": "teacher-a"}
        with repository_patch, course_patch:
            saved = self.client.put(
                "/api/courses/course-1/teaching-calendar",
                headers=headers,
                json={
                    "base_revision": 0,
                    "course_title": "设计思维",
                    "sessions": [
                        {"lesson_unit_id": "lesson-1", "content_summary": "人工调整后的第一讲", "status": "unscheduled"}
                    ],
                },
            )
            self.assertEqual(saved.status_code, 200)
            conflict = self.client.put(
                "/api/courses/course-1/teaching-calendar",
                headers=headers,
                json={"base_revision": 0, "sessions": []},
            )
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(conflict.json()["detail"]["current_revision"], 1)

            derived = self.client.post(
                "/api/courses/course-1/teaching-calendar/derive-from-outline",
                headers=headers,
            )
            self.assertEqual(derived.status_code, 200)
            result = derived.json()
            self.assertEqual(result["candidate_count"], 2)
            self.assertEqual(result["retained_count"], 1)
            self.assertEqual(result["candidate"]["source_outline_revision"], "outline-r3")
            self.assertEqual(result["candidate"]["sessions"][0]["content_summary"], "人工调整后的第一讲")
            self.assertEqual(self.repository.load("teacher-a", "course-1")["revision"], 1)

    def test_derive_retains_manual_stale_and_repeated_group_sessions(self):
        repository_patch, course_patch = self._patches()
        headers = {"X-User-Id": "teacher-a"}
        with repository_patch, course_patch:
            saved = self.client.put(
                "/api/courses/course-1/teaching-calendar",
                headers=headers,
                json={
                    "base_revision": 0,
                    "course_title": "设计思维",
                    "sessions": [
                        {
                            "session_id": "lesson-1-group-a",
                            "lesson_unit_id": "lesson-1",
                            "content_summary": "第一讲 A 组",
                            "date": "2026-03-02",
                            "start_time": "08:00:00",
                            "end_time": "09:35:00",
                            "location": "紫金港 A101",
                            "group_code": "A",
                            "status": "scheduled",
                            "source": "outline",
                        },
                        {
                            "session_id": "lesson-1-group-b",
                            "lesson_unit_id": "lesson-1",
                            "content_summary": "第一讲 B 组",
                            "date": "2026-03-03",
                            "start_time": "08:00:00",
                            "end_time": "09:35:00",
                            "location": "紫金港 A102",
                            "group_code": "B",
                            "status": "scheduled",
                            "source": "outline",
                        },
                        {
                            "session_id": "manual-office-hour",
                            "content_summary": "期中答疑",
                            "date": "2026-03-04",
                            "start_time": "18:30:00",
                            "end_time": "20:00:00",
                            "status": "scheduled",
                            "source": "manual",
                        },
                        {
                            "session_id": "legacy-lesson",
                            "lesson_unit_id": "lesson-removed",
                            "content_summary": "保留的旧大纲课次",
                            "status": "unscheduled",
                            "source": "outline",
                        },
                    ],
                },
            )
            self.assertEqual(saved.status_code, 200)

            derived = self.client.post(
                "/api/courses/course-1/teaching-calendar/derive-from-outline",
                headers=headers,
            )

            self.assertEqual(derived.status_code, 200)
            result = derived.json()
            sessions = result["candidate"]["sessions"]
            self.assertEqual(result["retained_count"], 4)
            self.assertEqual(result["new_count"], 1)
            self.assertEqual(result["candidate_count"], 5)
            self.assertEqual(
                [item["session_id"] for item in sessions[:4]],
                ["lesson-1-group-a", "lesson-1-group-b", "manual-office-hour", "legacy-lesson"],
            )
            self.assertEqual(sessions[0]["location"], "紫金港 A101")
            self.assertEqual(sessions[1]["group_code"], "B")
            self.assertEqual(sessions[2]["lesson_unit_id"], None)
            self.assertEqual(sessions[4]["lesson_unit_id"], "lesson-2")
            self.assertEqual(self.repository.load("teacher-a", "course-1")["revision"], 1)

    def test_rejects_invalid_time_and_requires_identity(self):
        repository_patch, course_patch = self._patches()
        with repository_patch, course_patch:
            invalid = self.client.put(
                "/api/courses/course-1/teaching-calendar",
                headers={"X-User-Id": "teacher-a"},
                json={
                    "base_revision": 0,
                    "sessions": [
                        {
                            "content_summary": "第一讲",
                            "date": "2026-03-02",
                            "start_time": "10:00:00",
                            "end_time": "09:00:00",
                            "status": "scheduled",
                        }
                    ],
                },
            )
            self.assertEqual(invalid.status_code, 422)
            missing_identity = self.client.get("/api/courses/course-1/teaching-calendar")
            self.assertEqual(missing_identity.status_code, 400)


if __name__ == "__main__":
    unittest.main()
