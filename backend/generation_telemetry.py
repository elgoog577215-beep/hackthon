"""生成链路模型调用埋点（A-1）。

设计约束（任务书 lz-perf A-1）：

* 只在 ``ai_base.py`` 的**请求统一出口**打点，调用点一个都不改。
* 阶段 / 小节标签用 ``contextvar`` 透传，避免给上百个调用点加参数。
* 排队等待时长由 ``ai_capacity.py`` 计量后一并写入。
* 落成 JSONL，一次生成一个文件。

阶段标签有两个来源，互为补充：

1. **显式**：调用方用 :func:`stage` / :func:`section` 包住一段工作。这是
   首选，语义最准。但生成链路的 ``course_*.py`` 归其他 worker 所有，本轮
   不能改，所以不能只靠它。
2. **推断**：记录时向上走栈，取第一个 ``ai_base.py`` 之外的调用帧，把
   ``模块.函数`` 当作阶段。任何调用点都自动带标签，一行业务代码都不用动。

因此"未显式标注的阶段"也不会变成一堆无法归因的记录——账单永远能按
``stage`` 汇总出每个阶段的耗时，这正是 A-1 验收②的要求。

**重复上下文计量**：每条记录带一份 ``context_blocks``——把 prompt 按段落
切块后的 ``(块指纹, 该块 token 数)`` 列表。同一份上下文被反复发送时，同一
指纹会在多条记录里重复出现，离线一聚合就能算出"重复上下文占多少 token"
（验收③），不需要在运行时保留 prompt 原文。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# ============================================================================
# 开关与路径
# ============================================================================

_ENV_ENABLED = "LINGZHI_GENERATION_TELEMETRY"
_ENV_DIR = "LINGZHI_GENERATION_TELEMETRY_DIR"

# 默认落在仓库外的运行目录，避免把账单写进版本库。
_DEFAULT_DIR = Path(
    os.getenv("LINGZHI_DATA_DIR")
    or Path(__file__).resolve().parent / "data"
) / "telemetry"

# prompt 分块的下限：太碎的块（一两句话）既不构成"重复上下文"，又会把
# JSONL 撑大，统计意义也低。
_MIN_BLOCK_CHARS = 80
_MAX_BLOCKS_PER_CALL = 400

_BLOCK_SPLIT = re.compile(r"\n\s*\n+")
# 逐题生成/逐节生成里，块与块之间常只差一个编号或标题序号。做规范化是为了
# 让"同一份上下文"不会因为一个序号差异就被当成两份，从而低估重复量。
_NORMALIZE_WS = re.compile(r"\s+")


def telemetry_enabled() -> bool:
    """埋点默认关闭；只有显式打开时才有运行时开销。"""
    return os.getenv(_ENV_ENABLED, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _telemetry_dir() -> Path:
    configured = os.getenv(_ENV_DIR, "").strip()
    return Path(configured) if configured else _DEFAULT_DIR


# ============================================================================
# 阶段 / 小节标签（contextvar 透传）
# ============================================================================

@dataclass(frozen=True)
class _Label:
    stage: str = ""
    section: str = ""
    purpose: str = ""
    extra: tuple[tuple[str, str], ...] = ()


_LABEL: ContextVar[_Label] = ContextVar("_LABEL", default=_Label())


@contextmanager
def stage(
    name: str,
    *,
    section: str = "",
    purpose: str = "",
    **extra: Any,
) -> Iterator[None]:
    """标注当前阶段。

    ``contextvar`` 语义在 asyncio 下正合适：``asyncio.create_task`` 会复制
    当前上下文，所以并行生成的每个小节各自持有自己的标签，互不串味；而
    ``await`` 链上的深层调用则天然继承外层阶段名。
    """
    current = _LABEL.get()
    merged = _Label(
        stage=name or current.stage,
        section=section or current.section,
        purpose=purpose or current.purpose,
        extra=current.extra + tuple(
            (str(k), str(v)) for k, v in extra.items()
        ),
    )
    token = _LABEL.set(merged)
    try:
        yield
    finally:
        _LABEL.reset(token)


@contextmanager
def section(name: str, *, purpose: str = "", **extra: Any) -> Iterator[None]:
    """在已有阶段内标注章节 / 小节。"""
    with stage("", section=name, purpose=purpose, **extra):
        yield


def current_label() -> dict[str, str]:
    label = _LABEL.get()
    resolved = {
        "stage": label.stage,
        "section": label.section,
        "purpose": label.purpose,
    }
    resolved.update({k: v for k, v in label.extra})
    return resolved


# ============================================================================
# 调用点推断（不改调用点签名的兜底归因）
# ============================================================================

_SELF_FILES = {
    "generation_telemetry.py",
    "ai_base.py",
    "ai_capacity.py",
    "contextlib.py",
}


def _infer_caller() -> tuple[str, str, int]:
    """返回第一个 LLM 调用层之外的调用帧 ``(模块, 函数, 行号)``。

    没有显式标注时，这就是阶段名的来源。用 ``sys._getframe`` 而不是
    ``traceback.extract_stack``：后者会去读源码文件，在每次模型调用上都做
    一遍太贵，而这里只需要帧上已有的元数据。
    """
    try:
        frame = sys._getframe(1)
    except ValueError:  # pragma: no cover - 解释器不支持时直接放弃归因
        return ("", "", 0)
    depth = 0
    while frame is not None and depth < 40:
        filename = frame.f_code.co_filename
        name = os.path.basename(filename)
        if name not in _SELF_FILES and "importlib" not in filename:
            module = name[:-3] if name.endswith(".py") else name
            return (module, frame.f_code.co_name, frame.f_lineno)
        frame = frame.f_back
        depth += 1
    return ("", "", 0)


# ============================================================================
# token 估算与上下文分块
# ============================================================================

def estimate_tokens(text: str) -> int:
    """与 ``AIBase.estimate_request_tokens`` 保持同一套混合语言启发式。

    这里刻意复制而不是 import，是为了不让埋点模块反向依赖 ``ai_base``
    （``ai_base`` 要 import 本模块，反过来会成环）。
    """
    if not text:
        return 0
    ascii_chars = sum(character.isascii() for character in text)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, math.ceil(ascii_chars / 3.2 + non_ascii_chars * 1.2))


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]


def context_blocks(text: str) -> list[list[Any]]:
    """把 prompt 切成 ``[块指纹, token 数]`` 列表，用于离线统计重复上下文。

    只留指纹不留原文：账单会落盘，prompt 里可能含课程内容与学习者数据，
    没有必要把它们抄进一份新文件里。
    """
    if not text:
        return []
    blocks: list[list[Any]] = []
    for raw in _BLOCK_SPLIT.split(text):
        chunk = raw.strip()
        if len(chunk) < _MIN_BLOCK_CHARS:
            continue
        normalized = _NORMALIZE_WS.sub(" ", chunk)
        blocks.append([_digest(normalized), estimate_tokens(chunk)])
        if len(blocks) >= _MAX_BLOCKS_PER_CALL:
            break
    return blocks


# ============================================================================
# 记录器：一次生成一个 JSONL 文件
# ============================================================================

@dataclass
class _Run:
    run_id: str
    path: Path
    started_at: float
    seq: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


_RUN: ContextVar[_Run | None] = ContextVar("_RUN", default=None)
_GLOBAL_RUN: _Run | None = None
_GLOBAL_LOCK = threading.Lock()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-")
    return slug[:60] or "run"


def _new_run(run_id: str) -> _Run:
    directory = _telemetry_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"generation-{stamp}-{_safe_slug(run_id)}.jsonl"
    return _Run(run_id=run_id, path=path, started_at=time.perf_counter())


@contextmanager
def generation_run(run_id: str) -> Iterator[Path]:
    """把一次完整生成的所有模型调用归到一个 JSONL 文件。"""
    run = _new_run(run_id)
    token = _RUN.set(run)
    global _GLOBAL_RUN
    with _GLOBAL_LOCK:
        previous_global = _GLOBAL_RUN
        _GLOBAL_RUN = run
    try:
        yield run.path
    finally:
        _RUN.reset(token)
        with _GLOBAL_LOCK:
            _GLOBAL_RUN = previous_global


def _active_run() -> _Run:
    """取当前 run；没有就按时间戳自动开一个。

    生成入口在 ``course_*.py``，本轮不归我改，所以不能指望它来调
    :func:`generation_run`。自动开 run 保证"直接跑一门课"也能拿到账单。
    """
    run = _RUN.get()
    if run is not None:
        return run
    global _GLOBAL_RUN
    with _GLOBAL_LOCK:
        if _GLOBAL_RUN is None:
            _GLOBAL_RUN = _new_run(os.getenv("LINGZHI_TELEMETRY_RUN_ID", "auto"))
        return _GLOBAL_RUN


def current_run_path() -> Path | None:
    run = _RUN.get() or _GLOBAL_RUN
    return run.path if run is not None else None


def record_call(
    *,
    model_id: str,
    model_role: str = "",
    status: str,
    stream: bool,
    attempt: int = 1,
    queue_wait_ms: float = 0.0,
    duration_ms: float = 0.0,
    ttfb_ms: float | None = None,
    prompt: str = "",
    system_prompt: str = "",
    output_text: str = "",
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    tokens_source: str = "estimate",
    retry_reason: str = "",
    error_code: str = "",
    physical_request_count: int = 1,
    provider_scope: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """写一条调用记录。**任何异常都不得影响业务调用。**"""
    if not telemetry_enabled():
        return
    try:
        run = _active_run()
        label = current_label()
        caller_module, caller_func, caller_line = _infer_caller()
        stage_name = label.get("stage") or caller_module
        with run.lock:
            run.seq += 1
            seq = run.seq
        record = {
            "seq": seq,
            "run_id": run.run_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "elapsed_s": round(time.perf_counter() - run.started_at, 3),
            "stage": stage_name,
            "section": label.get("section", ""),
            "purpose": label.get("purpose", "") or caller_func,
            "caller": f"{caller_module}.{caller_func}:{caller_line}",
            "model_id": model_id,
            "model_role": model_role,
            "provider_scope": provider_scope,
            "stream": stream,
            "status": status,
            "attempt": attempt,
            "is_retry": attempt > 1,
            "retry_reason": retry_reason,
            "error_code": error_code,
            "queue_wait_ms": int(round(queue_wait_ms)),
            "duration_ms": int(round(duration_ms)),
            "ttfb_ms": None if ttfb_ms is None else int(round(ttfb_ms)),
            "physical_request_count": physical_request_count,
            "input_tokens": (
                int(input_tokens)
                if input_tokens is not None
                else estimate_tokens(prompt) + estimate_tokens(system_prompt)
            ),
            "output_tokens": (
                int(output_tokens)
                if output_tokens is not None
                else estimate_tokens(output_text)
            ),
            "tokens_source": tokens_source,
            "prompt_chars": len(prompt) + len(system_prompt),
            "system_sha": _digest(system_prompt) if system_prompt else "",
            "prompt_sha": _digest(prompt) if prompt else "",
            "context_blocks": context_blocks(prompt),
        }
        if extra:
            record.update(extra)
        line = json.dumps(record, ensure_ascii=False)
        with run.lock:
            with run.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:  # pragma: no cover - 埋点永远不能拖垮生成
        pass
