import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from study.auth import study_identity
from study.development import development_identity
from study.identity_middleware import LocalStudyIdentityMiddleware


def request(host="127.0.0.1", **headers):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/study/auth/me",
            "scheme": "http",
            "server": ("127.0.0.1", 8001),
            "client": (host, 40000),
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        }
    )


@pytest.fixture
def development(monkeypatch):
    monkeypatch.setenv("LINGZHI_RUNTIME_MODE", "development")
    monkeypatch.setenv("LINGZHI_DEV_SURFACE", "student")
    monkeypatch.delenv("QIZHI_AUTH_VERIFY_URL", raising=False)


def test_development_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LINGZHI_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("LINGZHI_DEV_SURFACE", raising=False)
    assert development_identity(request()) is None


@pytest.mark.parametrize("change", ["remote", "forwarded", "foreign-origin", "production", "qizhi", "teacher"])
def test_development_identity_cannot_be_enabled_for_remote_or_production_requests(development, monkeypatch, change):
    headers = {}
    if change == "forwarded":
        headers["X-Forwarded-For"] = "203.0.113.1"
    if change == "foreign-origin":
        headers["Origin"] = "https://example.org"
    if change == "production":
        monkeypatch.setenv("LINGZHI_RUNTIME_MODE", "production")
    if change == "qizhi":
        monkeypatch.setenv("QIZHI_AUTH_VERIFY_URL", "https://example.org/verify")
    if change == "teacher":
        monkeypatch.setenv("LINGZHI_DEV_SURFACE", "teacher")
    assert development_identity(request("203.0.113.1" if change == "remote" else "127.0.0.1", **headers)) is None


def test_local_development_needs_no_account_and_preserves_student_permissions(development):
    app = FastAPI()
    app.add_middleware(LocalStudyIdentityMiddleware, course_storage=object())

    @app.get("/api/study/auth/me")
    def me(identity=Depends(study_identity)):
        return identity

    @app.post("/api/teacher/courses")
    def teacher_write():
        raise AssertionError("Student development identity must not reach teacher writes")

    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 40000))
    assert client.get("/api/study/auth/me").json() == {
        "id": "local-student:development",
        "username": "开发学习空间",
        "role": "student",
    }
    assert client.post("/api/teacher/courses", headers={"X-User-Id": "forged-teacher"}).status_code == 403
