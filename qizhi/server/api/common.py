from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from common.config import settings
from common.models import ApiResponse, BizException
from common.utils.logger import get_logger
from infra.db import User, generate_id
from service.auth import get_current_user

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/attachment/upload",
    summary="上传通用附件",
    response_model=ApiResponse[str],
)
async def attachment_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[str]:
    """上传通用附件。"""
    # 读取内容并校验大小
    content = await file.read()
    if len(content) > settings.UPLOAD_MAX_SIZE:
        logger.warning(f"[common.py] 附件过大: {len(content)} > {settings.UPLOAD_MAX_SIZE}")
        raise BizException(f"文件过大: {len(content)}")

    upload_dir = Path(settings.UPLOAD_DIR) / "attachments"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 重命名并写入文件目录
    new_name = f"{generate_id()}{Path(file.filename).suffix.lower()}"
    save_path = upload_dir / new_name
    save_path.write_bytes(content)

    return ApiResponse.success_response(str(save_path))


@router.get("/health", summary="健康检查", tags=["health"])
async def health_check():
    return {"status": "ok"}


@router.get("/health/net", summary="服务器→GPU 网络计时诊断", tags=["health"])
async def net_diag():
    """从服务器视角测「服务器→GPU」单次 ASR 上传 / 单次 LLM 调用耗时，
    与本地直连对比即可判定瓶颈是否在跨网络。临时诊断端点，确认后删除。"""
    import time, os, subprocess, tempfile, socket

    out = {"text_url": settings.LOCAL_ANALYSIS_TEXT_BASE_URL,
           "asr_url": settings.LOCAL_ANALYSIS_ASR_BASE_URL}

    # 1) TCP 握手时延（纯网络 RTT）
    for label, url in [("text", settings.LOCAL_ANALYSIS_TEXT_BASE_URL),
                       ("asr", settings.LOCAL_ANALYSIS_ASR_BASE_URL)]:
        try:
            host, port = url.replace("http://", "").replace("/v1", "").split(":")
            t = time.time()
            s = socket.create_connection((host, int(port)), timeout=5)
            s.close()
            out[f"tcp_{label}_ms"] = round((time.time() - t) * 1000, 1)
        except Exception as e:
            out[f"tcp_{label}_ms"] = str(e)[:80]

    # 2) 单次 LLM 调用耗时（小输入小输出，主要测网络往返+排队）
    try:
        from openai import OpenAI
        oc = OpenAI(api_key=settings.LOCAL_ANALYSIS_API_KEY, base_url=settings.LOCAL_ANALYSIS_TEXT_BASE_URL, timeout=120)
        t = time.time()
        oc.chat.completions.create(
            model=settings.LOCAL_ANALYSIS_MODEL, max_tokens=8,
            messages=[{"role": "user", "content": "只输出ok"}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        out["llm_call_s"] = round(time.time() - t, 2)
    except Exception as e:
        out["llm_call_s"] = str(e)[:120]

    # 3) 单块 ASR 耗时：找一个已存在的视频，切 60s wav 上传转写
    try:
        from infra.db.database import AsyncSessionLocal
        from infra.db.models.video import Video
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            v = (await db.execute(select(Video).where(Video.status == "success"))).scalars().first()
        if not v or not os.path.exists(v.path):
            out["asr"] = "无可用视频文件"
        else:
            fd, wav = tempfile.mkstemp(suffix=".wav"); os.close(fd)
            t = time.time()
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0", "-i", v.path,
                            "-t", "60", "-ac", "1", "-ar", "16000", wav], check=True)
            out["ffmpeg_extract_s"] = round(time.time() - t, 2)
            wav_size = os.path.getsize(wav)
            out["wav_bytes"] = wav_size
            from openai import OpenAI as OC2
            ac = OC2(api_key=settings.LOCAL_ANALYSIS_API_KEY, base_url=settings.LOCAL_ANALYSIS_ASR_BASE_URL, timeout=120)
            t = time.time()
            with open(wav, "rb") as f:
                ac.audio.transcriptions.create(model=settings.LOCAL_ANALYSIS_ASR_MODEL, file=f, language="zh", response_format="json")
            dt = time.time() - t
            out["asr_call_s"] = round(dt, 2)
            out["asr_upload_mbps"] = round(wav_size / 1024 / 1024 / dt, 2)
            os.remove(wav)
    except Exception as e:
        import traceback
        out["asr"] = str(e)[:120]
        out["asr_tb"] = traceback.format_exc()[-300:]

    return out
