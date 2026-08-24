from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.application_errors import REQUEST_ID_HEADER, install_application_error_contract


def build_app() -> FastAPI:
    app = FastAPI()
    install_application_error_contract(app)

    @app.get("/known-error")
    def known_error():
        raise HTTPException(status_code=404, detail="课程不存在")

    @app.get("/unexpected-error")
    def unexpected_error():
        raise RuntimeError("database password must never reach the browser")

    return app


def test_every_http_error_has_request_id_without_changing_known_detail() -> None:
    client = TestClient(build_app())
    response = client.get("/known-error", headers={REQUEST_ID_HEADER: "req_browser_1234"})

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "req_browser_1234"
    assert response.json() == {"detail": "课程不存在"}


def test_unhandled_error_returns_safe_code_and_request_id() -> None:
    client = TestClient(build_app(), raise_server_exceptions=False)
    response = client.get("/unexpected-error")

    assert response.status_code == 500
    payload = response.json()["detail"]
    assert payload["code"] == "internal_server_error"
    assert payload["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert "password" not in response.text
    assert "RuntimeError" not in response.text
