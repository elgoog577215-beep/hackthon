"""本地视频分析的预估剩余时间。

只估**本地分析**（task_type=local_video_analysis）；云端(超星)不估。
依据：**视频时长 + ASR 并发 + 本地分析队列里排在前面的视频数量**。

本地分析由单 worker 顺序执行（一次只跑一个），所以某视频的剩余时间 =
  队列中排在它前面的各视频预估耗时之和（含正在跑那个的剩余）+ 它自身预估耗时。

注意：下面几个估时常量是**经验默认值**，可按线上实测校准（看 app 日志里
ASR / LLM 各阶段实际耗时后微调即可）。
"""
import math
import os
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.db.models.task_queue import TaskQueue
from infra.db.models.video import Video

# 本地分析任务类型（与 LocalVideoAnalysisHandler.task_type 一致；写字面量避免循环依赖）
_LOCAL_TASK_TYPE = "local_video_analysis"

# ---- 估时模型常量（可校准）----
_ASR_CHUNK_SEC = 60.0        # 与 run_local_analysis 的 asr_chunk_sec 一致：每块音频时长
_ASR_SEC_PER_CHUNK = 3.0     # 每块（60s）转写耗时（含 ffmpeg + ASR）经验值
_LLM_BASE_SEC = 60.0         # LLM 阶段固定开销（4 维 + 总评；模型服务多为串行处理，故给得保守）
_LLM_SEC_PER_MIN = 5.0       # LLM 随视频时长（字幕越长、每次调用 prompt 越大）增长，取偏长
_OVERHEAD_SEC = 10.0         # 启动/探测/封面/落库等杂项
_DEFAULT_DURATION_SEC = 30 * 60.0  # 时长探测失败时的兜底（按 30 分钟估）
_MIN_REMAINING_SEC = 5       # 正在跑的视频已超估时也至少显示 5s，避免归零跳变


def _workers() -> int:
    """本地分析并发度（透传给 run_local_analysis 的 workers）。延迟导入避免循环依赖。"""
    try:
        from service.video.analysis_task import _LOCAL_ANALYSIS_WORKERS
        return max(1, int(_LOCAL_ANALYSIS_WORKERS))
    except Exception:
        return 8


def estimate_one_seconds(duration_sec: float, workers: int | None = None) -> float:
    """单个视频的本地分析预估总耗时（秒）。"""
    w = workers if workers and workers > 0 else _workers()
    dur = max(0.0, float(duration_sec or 0.0))
    num_chunks = max(1, math.ceil(dur / _ASR_CHUNK_SEC))
    asr = math.ceil(num_chunks / w) * _ASR_SEC_PER_CHUNK
    llm = _LLM_BASE_SEC + _LLM_SEC_PER_MIN * (dur / 60.0)
    return asr + llm + _OVERHEAD_SEC


# 进程内时长缓存：key=(path, mtime)，避免每次列表都 ffprobe 同一文件
_dur_cache: dict[tuple[str, float], float] = {}


def _probe_duration(path: str) -> float | None:
    """ffprobe 探测视频时长（秒）；失败返回 None。带 (path, mtime) 缓存。"""
    if not path:
        return None
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return None
    key = (path, mtime)
    if key in _dur_cache:
        return _dur_cache[key]
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=20,
        )
        dur = float(out.stdout.strip())
    except Exception:
        return None
    if dur > 0:
        _dur_cache[key] = dur
    return dur


async def compute_local_eta_map(db: AsyncSession) -> dict[str, int]:
    """返回 {video_id: 预估剩余秒数}，覆盖本地分析队列里所有 pending/processing 的视频。

    队列按 scheduled_at 排序；正在跑（processing）的那个减去已运行时间。
    """
    rows = (await db.execute(
        select(TaskQueue)
        .where(TaskQueue.task_type == _LOCAL_TASK_TYPE)
        .where(TaskQueue.status.in_(["pending", "processing"]))
        .order_by(TaskQueue.scheduled_at)
    )).scalars().all()
    if not rows:
        return {}

    vid_ids = [t.business_id for t in rows]
    videos = (await db.execute(select(Video).where(Video.id.in_(vid_ids)))).scalars().all()
    vmap = {v.id: v for v in videos}

    workers = _workers()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    eta: dict[str, int] = {}
    cumulative = 0.0  # 排在当前视频之前的累计剩余时间
    for t in rows:
        v = vmap.get(t.business_id)
        if v is None:
            continue  # 视频已删（任务残留）→ 跳过，不占队列时间
        own = estimate_one_seconds(_probe_duration(v.path) or _DEFAULT_DURATION_SEC, workers)
        if t.status == "processing" and v.analysis_start_time is not None:
            elapsed = (now - v.analysis_start_time).total_seconds()
            remaining_own = max(float(_MIN_REMAINING_SEC), own - elapsed)
        else:
            remaining_own = own
        cumulative += remaining_own
        eta[t.business_id] = int(round(cumulative))
    return eta
