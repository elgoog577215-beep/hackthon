from __future__ import annotations

from rate_limiter import _match_rate_limit


def test_question_bank_status_polling_has_a_dedicated_read_limit():
    assert _match_rate_limit(
        "/api/courses/course-1/question-bank/rebuilds/job-1",
        method="GET",
    ) == (120, 60)
    assert _match_rate_limit(
        "/api/courses/course-1/question-bank/rebuild",
        method="POST",
    ) == (30, 60)
