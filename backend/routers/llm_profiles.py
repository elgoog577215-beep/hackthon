"""HTTP API for local LLM provider profiles."""

from fastapi import APIRouter, HTTPException, Request
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from llm_profiles import llm_profile_store


router = APIRouter(prefix="/llm-profiles", tags=["llm_profiles"])
_LOCAL_HOSTS = {"127.0.0.1", "::1", "testclient"}


def _safe_provider_error(exc: Exception, api_key: str) -> str:
    message = " ".join(str(exc or "").split()).strip()
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return (message or type(exc).__name__)[:240]


def _require_local_client(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="模型密钥配置仅允许本机访问")


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    api_base: str = Field(min_length=8, max_length=500)
    api_key: str = Field(min_length=1, max_length=1000)
    smart_model: str = Field(default="", max_length=300)
    fast_model: str = Field(default="", max_length=300)
    activate: bool = True


@router.get("")
def list_profiles(request: Request):
    _require_local_client(request)
    return llm_profile_store.list()


@router.post("", status_code=201)
def create_profile(payload: ProfileRequest, request: Request):
    _require_local_client(request)
    profile = llm_profile_store.create(
        {
            "name": payload.name.strip(),
            "api_base": payload.api_base.strip().rstrip("/"),
            "api_key": payload.api_key.strip(),
            "smart_model": payload.smart_model.strip(),
            "fast_model": payload.fast_model.strip(),
        },
        activate=payload.activate,
    )
    return {"profile": profile}


@router.post("/{profile_id}/activate")
def activate_profile(profile_id: str, request: Request):
    _require_local_client(request)
    try:
        return {"profile": llm_profile_store.activate(profile_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模型配置不存在") from exc


@router.post("/{profile_id}/test")
async def test_profile(profile_id: str, request: Request):
    _require_local_client(request)
    try:
        config = llm_profile_store.config_for(profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模型配置不存在") from exc
    if not config["api_key"]:
        raise HTTPException(status_code=422, detail="该配置没有 API Key")
    smart_model = str(config.get("smart_model") or "").strip()
    fast_model = str(config.get("fast_model") or "").strip() or smart_model
    if not smart_model:
        raise HTTPException(status_code=502, detail="连接可测试，但该配置没有主模型，无法验证真实生成调用")
    try:
        client = AsyncOpenAI(base_url=config["api_base"], api_key=config["api_key"], timeout=15.0, max_retries=0)
        models = await client.models.list()
        validated_model_ids: set[str] = set()
        for label, model_id in (("主模型", smart_model), ("快速模型", fast_model)):
            if model_id in validated_model_ids:
                continue
            try:
                await client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": "仅回复 OK"}],
                    max_tokens=1,
                    stream=False,
                )
            except Exception as exc:
                detail = _safe_provider_error(exc, config["api_key"])
                raise HTTPException(
                    status_code=502,
                    detail=f"{label} {model_id} 生成测试失败：{detail}",
                ) from exc
            validated_model_ids.add(model_id)
        return {
            "ok": True,
            "model_count": len(models.data),
            "validated_models": {"smart": smart_model, "fast": fast_model},
        }
    except HTTPException:
        raise
    except Exception as exc:
        detail = _safe_provider_error(exc, config["api_key"])
        raise HTTPException(status_code=502, detail=f"连接失败：{detail}") from exc
    finally:
        if "client" in locals():
            await client.close()
