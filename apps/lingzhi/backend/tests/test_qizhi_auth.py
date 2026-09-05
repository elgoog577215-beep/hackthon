from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from qizhi_auth import (
    AUTH_FORBIDDEN_CODE,
    AUTH_REQUIRED_CODE,
    QizhiAuthError,
    QizhiIdentity,
    QizhiIdentityMiddleware,
    QizhiIdentityVerifier,
    websocket_authorization,
)


class StubVerifier(QizhiIdentityVerifier):
    def __init__(self, *, enabled: bool = True, role: str = "teacher") -> None:
        super().__init__("http://qizhi/user/current" if enabled else "")
        self.role = role

    async def resolve(self, authorization: str | None) -> QizhiIdentity:
        if not authorization:
            raise QizhiAuthError(401, AUTH_REQUIRED_CODE, "请先登录")
        if self.role == "student":
            raise QizhiAuthError(403, AUTH_FORBIDDEN_CODE, "无教师权限")
        return QizhiIdentity(actor_id="qizhi:user-1", role=self.role)


def make_app(verifier: QizhiIdentityVerifier) -> FastAPI:
    app = FastAPI()
    app.add_middleware(QizhiIdentityMiddleware, verifier=verifier)

    @app.get("/api/private")
    async def private(request: Request):
        return {
            "actor": request.headers.get("X-User-Id"),
            "role": request.headers.get("X-Qizhi-Role"),
        }

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


def test_production_bridge_requires_qizhi_session():
    response = TestClient(make_app(StubVerifier())).get("/api/private")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AUTH_REQUIRED_CODE


def test_production_bridge_overwrites_spoofed_actor():
    response = TestClient(make_app(StubVerifier())).get(
        "/api/private",
        headers={"Authorization": "Bearer signed-token", "X-User-Id": "forged-user"},
    )
    assert response.status_code == 200
    assert response.json() == {"actor": "qizhi:user-1", "role": "teacher"}


def test_production_bridge_rejects_non_teacher_role():
    response = TestClient(make_app(StubVerifier(role="student"))).get(
        "/api/private",
        headers={"Authorization": "Bearer student-token"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == AUTH_FORBIDDEN_CODE


def test_health_and_disabled_development_mode_stay_available():
    enabled = TestClient(make_app(StubVerifier()))
    assert enabled.get("/api/health").status_code == 200

    disabled = TestClient(make_app(StubVerifier(enabled=False)))
    response = disabled.get("/api/private", headers={"X-User-Id": "local-teacher"})
    assert response.status_code == 200
    assert response.json()["actor"] == "local-teacher"


def test_websocket_token_is_read_from_subprotocol_without_query_string():
    class Socket:
        headers = {
            "sec-websocket-protocol": "lingzhi-auth-v1, qizhi-bearer.header.payload.signature"
        }

    assert websocket_authorization(Socket()) == "Bearer header.payload.signature"


def test_verifier_maps_qizhi_current_user_response(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "success": True,
                "data": {"id": "formal-user", "role": "admin"},
            }

    monkeypatch.setattr("qizhi_auth.requests.get", lambda *args, **kwargs: Response())
    verifier = QizhiIdentityVerifier("http://qizhi/user/current")
    identity = verifier._verify_upstream("Bearer signed-token")
    assert identity == QizhiIdentity(actor_id="qizhi:formal-user", role="admin")


def test_verifier_rejects_student_from_real_upstream_contract(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "success": True,
                "data": {"id": "student-user", "role": "student"},
            }

    monkeypatch.setattr("qizhi_auth.requests.get", lambda *args, **kwargs: Response())
    verifier = QizhiIdentityVerifier("http://qizhi/user/current")
    try:
        verifier._verify_upstream("Bearer student-token")
    except QizhiAuthError as exc:
        assert exc.status_code == 403
        assert exc.code == AUTH_FORBIDDEN_CODE
    else:
        raise AssertionError("student role must be rejected")
