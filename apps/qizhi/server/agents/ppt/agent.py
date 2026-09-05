"""PPT 本地生成 Agent：以教案/大纲为依据，用自建 vLLM Qwen 生成幻灯片，
产出可交互 HTML 预览 + 可下载 .pptx，通过 SSE 流式返回进度与最终文件地址。
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from agents.ppt.models import PptGenerateParams
from agents.resource_access import get_owned_resource
from common.config import settings
from common.models import BizException
from common.utils import SseEventEnum, build_sse_response
from common.utils.logger import get_logger
from infra.db import Resource, User, generate_id

logger = get_logger(__name__)


def _clean_course_name(name: str | None) -> str:
    name = (name or "").strip()
    if not name:
        return "课程"
    # 去掉常见后缀「- 教案」「教案」「- 大纲」等，作为封面课程名
    name = re.sub(r"[-—\s]*(教案|教学大纲|大纲|PPT|课件)\s*$", "", name).strip()
    return name or "课程"


async def _load_source(
    db: AsyncSession,
    params: PptGenerateParams,
    actor: User,
) -> tuple[str, str]:
    """返回 (教案/大纲正文, 课程名)。"""
    content = ""
    course = "课程"
    if params.source_resource_id:
        resource = await get_owned_resource(db, params.source_resource_id, actor.id)
        if resource:
            content = resource.content or ""
            course = _clean_course_name(resource.name)
    if not content.strip():
        # 无依据资源时，退回用户提示词作为生成依据
        content = (params.previous_content or params.prompt or "").strip()
    if not content.strip():
        raise BizException("请选择作为依据的教案/大纲，或填写生成要求后再试。")
    return content, course


async def _persist_ppt_artifact(resource_id: str, result: dict,
                                creator_id: str) -> None:
    """把生成的 html/pptx 地址写回 PPT 资源行，保证再次进入仍能预览/下载。

    用独立的新 session（而非流式请求的 db）：PPT 生成耗时较长，流式请求的 session
    在 worker 执行期间长时间空闲，其连接可能已被连接池回收/服务端断开，导致此处写库
    静默失败；新 session 从池里取连接（pool_pre_ping=True）更稳，也与流式响应生命周期解耦。

    带 creator 校验避免越权写；只写产物地址两列，不动 content/name，因此不走
    ResourceService.update_resource（它会拒绝只读资源且只写 content/name）。
    """
    from infra.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = update(Resource).where(
            Resource.id == resource_id,
            Resource.creator_id == creator_id,
        ).values(
            ppt_html_url=result.get("html_url"),
            ppt_pptx_url=result.get("pptx_url"),
        )
        res = await session.execute(stmt)
        await session.commit()
        logger.info(
            "[ppt] 持久化产物地址 resource_id=%s rowcount=%s html=%s",
            resource_id, res.rowcount, result.get("html_url"),
        )


async def stream(
    db: AsyncSession,
    params: PptGenerateParams,
    actor: User,
) -> AsyncIterator[dict]:
    """流式生成 PPT：先回放进度（loading），最终回传 html_url / pptx_url（end）。"""
    content, course = await _load_source(db, params, actor)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(kind: str, payload) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (kind, payload))

    def worker() -> None:
        try:
            # 延迟导入，避免在事件循环线程里加载重依赖
            from agents.ppt.pptx_render import build_pptx
            from agents.ppt.runner import make_default_runner
            from agents.ppt.slides import build_deck_from_text, render_slides_html

            runner = make_default_runner(workers=4)
            deck = build_deck_from_text(
                runner,
                content=content,
                meta={"courseName": course, "subTitle": ""},
                user_prompt=params.prompt or "",
                min_slides=params.min_slides,
                max_slides=params.max_slides,
                log=logger,
                progress=lambda m: emit("loading", m),
            )
            emit("loading", "正在渲染 HTML 与 PPTX…")

            gen_id = generate_id()
            ppt_dir = Path(settings.UPLOAD_DIR) / "ppt"
            ppt_dir.mkdir(parents=True, exist_ok=True)
            html_path = ppt_dir / f"{gen_id}.html"
            pptx_path = ppt_dir / f"{gen_id}.pptx"
            html_path.write_text(render_slides_html(deck), encoding="utf-8")
            build_pptx(deck, str(pptx_path))

            emit("result", {
                "html_url": f"/static/ppt/{gen_id}.html",
                "pptx_url": f"/static/ppt/{gen_id}.pptx",
                "title": deck.get("title") or course,
                "slides": len(deck.get("slides") or []),
            })
        except Exception as e:  # noqa: BLE001
            logger.exception("[ppt] 生成失败")
            emit("error", str(e))
        finally:
            emit("__end__", None)

    fut = loop.run_in_executor(None, worker)
    yield build_sse_response(SseEventEnum.START, {"message": "开始生成 PPT"})

    result = None
    err = None
    while True:
        kind, payload = await queue.get()
        if kind == "loading":
            yield build_sse_response(SseEventEnum.LOADING, {"content": payload})
        elif kind == "result":
            result = payload
        elif kind == "error":
            err = payload
        elif kind == "__end__":
            break

    try:
        await fut
    except Exception:  # noqa: BLE001  worker 内已捕获并 emit error
        pass

    if err:
        raise BizException(f"生成 PPT 失败：{err}")
    if not result:
        raise BizException("生成 PPT 失败：未产出结果")

    # 落库：把产物地址写回当前 PPT 资源行（前端已把 resource_id 传入）。
    # 落库失败不应阻断已生成的结果返回，仅告警。
    if params.resource_id:
        try:
            await _persist_ppt_artifact(
                params.resource_id, result, actor.id
            )
        except Exception:  # noqa: BLE001
            logger.exception("[ppt] 持久化产物地址失败 resource_id=%s", params.resource_id)

    yield build_sse_response(SseEventEnum.END, result)
