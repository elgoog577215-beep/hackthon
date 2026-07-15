from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import llm_profiles


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(llm_profiles.router, prefix="/api")
    return TestClient(app)


def test_connection_check_validates_smart_and_fast_completions(monkeypatch):
    completion_models: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = SimpleNamespace(
                list=self._list_models,
            )
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create_completion),
            )

        async def _list_models(self):
            return SimpleNamespace(data=[
                SimpleNamespace(id="deepseek-v4-pro"),
                SimpleNamespace(id="deepseek-v4-flash"),
            ])

        async def _create_completion(self, **kwargs):
            completion_models.append(kwargs["model"])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])

        async def close(self):
            return None

    monkeypatch.setattr(
        llm_profiles.llm_profile_store,
        "config_for",
        lambda _profile_id: {
            "api_key": "test-key",
            "api_base": "https://api.deepseek.example",
            "smart_model": "deepseek-v4-pro",
            "fast_model": "deepseek-v4-flash",
        },
    )
    monkeypatch.setattr(llm_profiles, "AsyncOpenAI", FakeClient)

    response = _client().post("/api/llm-profiles/profile-1/test")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model_count"] == 2
    assert response.json()["validated_models"] == {
        "smart": "deepseek-v4-pro",
        "fast": "deepseek-v4-flash",
    }
    assert completion_models == ["deepseek-v4-pro", "deepseek-v4-flash"]


def test_connection_check_reports_the_exact_model_that_failed(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = SimpleNamespace(list=self._list_models)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create_completion),
            )

        async def _list_models(self):
            return SimpleNamespace(data=[SimpleNamespace(id="deepseek-v4-pro")])

        async def _create_completion(self, **kwargs):
            if kwargs["model"] == "bad-fast-model":
                raise RuntimeError("400 invalid model bad-fast-model")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])

        async def close(self):
            return None

    monkeypatch.setattr(
        llm_profiles.llm_profile_store,
        "config_for",
        lambda _profile_id: {
            "api_key": "test-key",
            "api_base": "https://api.deepseek.example",
            "smart_model": "deepseek-v4-pro",
            "fast_model": "bad-fast-model",
        },
    )
    monkeypatch.setattr(llm_profiles, "AsyncOpenAI", FakeClient)

    response = _client().post("/api/llm-profiles/profile-1/test")

    assert response.status_code == 502
    assert "快速模型 bad-fast-model" in response.json()["detail"]
    assert "400 invalid model" in response.json()["detail"]


def test_connection_check_inherits_smart_model_when_fast_model_is_blank(monkeypatch):
    completion_models: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = SimpleNamespace(
                list=lambda: self._list_models(),
            )
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create_completion),
            )

        async def _list_models(self):
            return SimpleNamespace(data=[SimpleNamespace(id="deepseek-v4-pro")])

        async def _create_completion(self, **kwargs):
            completion_models.append(kwargs["model"])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])

        async def close(self):
            return None

    monkeypatch.setattr(
        llm_profiles.llm_profile_store,
        "config_for",
        lambda _profile_id: {
            "api_key": "test-key",
            "api_base": "https://api.deepseek.example",
            "smart_model": "deepseek-v4-pro",
            "fast_model": "",
        },
    )
    monkeypatch.setattr(llm_profiles, "AsyncOpenAI", FakeClient)

    response = _client().post("/api/llm-profiles/profile-1/test")

    assert response.status_code == 200
    assert response.json()["validated_models"] == {
        "smart": "deepseek-v4-pro",
        "fast": "deepseek-v4-pro",
    }
    assert completion_models == ["deepseek-v4-pro"]
