from __future__ import annotations

import inspect

import pytest

import ai_base
from ai_base import AIBase, AIProviderUnavailable
from text_ai_provider_policy import (
    EXPECTED_TEXT_MODEL,
    TextAIProviderPolicyError,
    enforce_text_ai_provider_policy,
    normalize_openai_base_url,
)


PRIVATE_TEST_BASE = "http://qwen.internal.test:30938/v1"


def _locked_environment(monkeypatch):
    monkeypatch.delenv(
        "LINGZHI_TEST_ALLOW_EXTERNAL_TEXT_PROVIDERS",
        raising=False,
    )
    for key in (
        "MODELSCOPE_API_KEY",
        "MODELSCOPE_BASE_URL",
        "MODELSCOPE_MODEL",
        "MODELSCOPE_MODEL_CANDIDATES",
        "MODELSCOPE_MODEL_FAST_CANDIDATES",
        "AI_MODEL_CANDIDATES",
        "AI_MODEL_FAST_CANDIDATES",
        "AI_ASSESSMENT_GENERATOR_MODELS",
        "AI_ASSESSMENT_SOLVER_MODELS",
        "AI_ASSESSMENT_REVIEWER_MODELS",
        "AI_PPT_API_KEY",
        "AI_PPT_API_BASE",
        "AI_PPT_STORY_MODELS",
        "AI_PPT_VISUAL_MODELS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_LOCAL_PROVIDER", "http")
    monkeypatch.setenv("ZJU_QWEN_API_KEY", "EMPTY")
    monkeypatch.setenv("ZJU_QWEN_BASE_URL", PRIVATE_TEST_BASE)
    monkeypatch.setenv("AI_API_KEY", "EMPTY")
    monkeypatch.setenv("AI_API_BASE", PRIVATE_TEST_BASE)
    monkeypatch.setenv("AI_MODEL", EXPECTED_TEXT_MODEL)
    monkeypatch.setenv("AI_MODEL_FAST", EXPECTED_TEXT_MODEL)


def test_policy_accepts_only_normalized_private_endpoint_and_expected_model():
    environment = {
        "ZJU_QWEN_API_KEY": "EMPTY",
        "ZJU_QWEN_BASE_URL": f"{PRIVATE_TEST_BASE}/",
    }

    enforce_text_ai_provider_policy(
        api_base=PRIVATE_TEST_BASE,
        models=[EXPECTED_TEXT_MODEL, EXPECTED_TEXT_MODEL],
        environment=environment,
    )
    assert normalize_openai_base_url(f"{PRIVATE_TEST_BASE}/") == PRIVATE_TEST_BASE


@pytest.mark.parametrize(
    ("api_base", "models", "extra", "reason"),
    [
        (
            "https://api-inference.modelscope.cn/v1",
            [EXPECTED_TEXT_MODEL],
            {},
            "text_provider_base_url_mismatch",
        ),
        (
            PRIVATE_TEST_BASE,
            ["Qwen/Qwen3.5-27B"],
            {},
            "text_provider_model_mismatch",
        ),
        (
            PRIVATE_TEST_BASE,
            [EXPECTED_TEXT_MODEL],
            {"MODELSCOPE_API_KEY": "forbidden"},
            "modelscope_text_fallback_forbidden",
        ),
        (
            PRIVATE_TEST_BASE,
            [EXPECTED_TEXT_MODEL],
            {"AI_LOCAL_PROVIDER": "codex"},
            "external_local_text_provider_forbidden",
        ),
    ],
)
def test_policy_rejects_external_endpoint_model_or_fallback(
    api_base,
    models,
    extra,
    reason,
):
    environment = {
        "ZJU_QWEN_API_KEY": "EMPTY",
        "ZJU_QWEN_BASE_URL": PRIVATE_TEST_BASE,
        **extra,
    }

    with pytest.raises(TextAIProviderPolicyError, match=reason):
        enforce_text_ai_provider_policy(
            api_base=api_base,
            models=models,
            environment=environment,
        )


def test_ai_base_rejects_bad_route_before_creating_network_client(
    monkeypatch,
):
    _locked_environment(monkeypatch)
    monkeypatch.setenv(
        "AI_API_BASE",
        "https://api-inference.modelscope.cn/v1",
    )

    def fail_if_client_created(*_args, **_kwargs):
        raise AssertionError("network client must not be created")

    monkeypatch.setattr(ai_base, "AsyncOpenAI", fail_if_client_created)

    with pytest.raises(
        AIProviderUnavailable,
        match="text_provider_base_url_mismatch",
    ):
        AIBase()


def test_ai_base_routes_general_and_ppt_text_to_same_qwen(monkeypatch):
    _locked_environment(monkeypatch)
    monkeypatch.setenv("AI_PPT_API_KEY", "EMPTY")
    monkeypatch.setenv("AI_PPT_API_BASE", PRIVATE_TEST_BASE)
    monkeypatch.setenv("AI_PPT_STORY_MODELS", EXPECTED_TEXT_MODEL)
    monkeypatch.setenv("AI_PPT_VISUAL_MODELS", EXPECTED_TEXT_MODEL)

    general = AIBase()
    ppt = AIBase(provider_profile="ppt")

    assert general.api_base == PRIVATE_TEST_BASE
    assert ppt.api_base == PRIVATE_TEST_BASE
    assert general.smart_models == [EXPECTED_TEXT_MODEL]
    assert general.fast_models == [EXPECTED_TEXT_MODEL]
    assert ppt._models_for(False, "ppt_story") == [EXPECTED_TEXT_MODEL]
    assert ppt._models_for(True, "ppt_visual") == [EXPECTED_TEXT_MODEL]
    assert "_call_modelscope_fallback" not in inspect.getsource(AIBase._call_llm)
    assert "_stream_modelscope_fallback" not in inspect.getsource(AIBase._stream_llm)


def test_qwen_text_requests_disable_hidden_thinking_by_default(monkeypatch):
    _locked_environment(monkeypatch)

    service = AIBase()

    assert service.thinking_enabled is False
    assert service._thinking_extra_body(False) == {
        "enable_thinking": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
