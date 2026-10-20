"""Reading existing jobs must support normal multi-tab progress observation."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rate_limiter import RateLimitMiddleware, SlidingWindowCounter, _match_rate_limit


@pytest.mark.parametrize('path', ['/api/courses/course-1/knowledge-first/status',
    '/api/courses/course-1/knowledge-first/events/job-1'])
def test_knowledge_observation_has_a_read_budget_separate_from_generation(path):
    assert _match_rate_limit(path, 'GET') == (120, 60)
    assert _match_rate_limit(path, 'POST') == (30, 60)
    assert _match_rate_limit('/api/courses/course-1/knowledge-first/generate/tree', 'POST') == (30, 60)
    assert _match_rate_limit('/api/courses/course-1/knowledge-first', 'GET') == (30, 60)


def test_three_normal_tabs_can_observe_without_increasing_write_budget(monkeypatch):
    import rate_limiter
    monkeypatch.setattr(rate_limiter, '_counter', SlidingWindowCounter())
    app = FastAPI(); app.add_middleware(RateLimitMiddleware)
    @app.get('/api/courses/c/knowledge-first/status')
    def status(): return {'active_jobs': []}
    @app.post('/api/courses/c/knowledge-first/generate/tree')
    def generate(): return {'created': True}
    with TestClient(app) as client:
        for _ in range(3 * 30):
            assert client.get('/api/courses/c/knowledge-first/status').status_code == 200
        for _ in range(30):
            assert client.post('/api/courses/c/knowledge-first/generate/tree').status_code == 200
        assert client.post('/api/courses/c/knowledge-first/generate/tree').status_code == 429
