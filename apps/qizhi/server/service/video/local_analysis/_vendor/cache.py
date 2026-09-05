"""三层缓存：
1. 上传 sidecar —— 视频只上传一次，跨运行复用（用户的硬性要求）。
2. 上下文缓存 —— 可选，跨多次模型调用复用整段视频 token，失败自动降级。
3. 按维度结果缓存 —— 每个分析步骤的结果落盘，重跑断点续跑、改一处不动其余。
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .util import atomic_write_json, read_json

# google-genai 在使用处导入，避免 import 期副作用
try:  # 仅用于类型/枚举
    from google.genai import types as genai_types
except Exception:  # pragma: no cover
    genai_types = None


# ---------------------------------------------------------------------------
# 视频指纹（避免每次哈希 332MB：首/尾 1MB + 大小）
# ---------------------------------------------------------------------------

def video_fingerprint(path: str) -> str:
    st = os.stat(path)
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    chunk = 1 << 20  # 1MB
    with open(path, "rb") as f:
        head = f.read(chunk)
        h.update(head)
        if st.st_size > chunk:
            f.seek(max(0, st.st_size - chunk))
            h.update(f.read(chunk))
    return h.hexdigest()[:32]


# ---------------------------------------------------------------------------
# 1 + 2：上传 / 上下文缓存 sidecar
# ---------------------------------------------------------------------------

class UploadCache:
    def __init__(self, cache_dir: str, logger):
        self.path = os.path.join(cache_dir, "upload.json")
        self.log = logger
        self._data = read_json(self.path) if os.path.exists(self.path) else {}

    def _save(self):
        atomic_write_json(self.path, self._data)

    # ---- 上传复用 ----
    def ensure_uploaded(self, client, video_path: str, force: bool = False,
                        poll_timeout: float = 600.0):
        """返回一个 File 对象（含 .uri/.name/.mime_type）。命中则复用，否则上传。"""
        fp = video_fingerprint(video_path)
        entry = self._data.get(fp)

        if entry and not force and entry.get("file_name"):
            f = self._try_get_active(client, entry["file_name"], poll_timeout)
            if f is not None:
                self.log.info(f"[upload] 复用已上传文件 {f.name}（缓存命中，未重新上传）")
                return f
            self.log.info("[upload] 已缓存文件失效/过期，重新上传")

        if force:
            self.log.info("[upload] --force-reupload，重新上传")

        f = self._upload(client, video_path, poll_timeout)
        self._data[fp] = {
            "path": os.path.abspath(video_path),
            "size": os.path.getsize(video_path),
            "file_name": f.name,
            "file_uri": f.uri,
            "mime_type": f.mime_type or "video/mp4",
            "uploaded_at": _now_iso(),
            "context_cache": (entry or {}).get("context_cache"),  # 视频变了则保留旧值无意义，但下面 ensure 会校验
        }
        # 视频指纹变化意味着内容不同，上下文缓存作废
        if entry is None or entry.get("file_name") != f.name:
            self._data[fp]["context_cache"] = None
        self._save()
        return f

    def _upload(self, client, video_path: str, poll_timeout: float):
        size_mb = os.path.getsize(video_path) / (1 << 20)
        self.log.info(f"[upload] 上传 {os.path.basename(video_path)} ({size_mb:.0f}MB) ...")
        t0 = time.time()
        f = client.files.upload(file=video_path)
        f = self._poll_active(client, f, poll_timeout)
        self.log.info(f"[upload] 上传完成 {f.name}（{time.time()-t0:.1f}s）")
        return f

    def _try_get_active(self, client, name: str, poll_timeout: float):
        try:
            f = client.files.get(name=name)
        except Exception as e:  # NOT_FOUND / 过期
            self.log.debug(f"[upload] files.get 失败：{e}")
            return None
        try:
            return self._poll_active(client, f, poll_timeout)
        except Exception as e:
            self.log.debug(f"[upload] 轮询失败：{e}")
            return None

    def _poll_active(self, client, f, poll_timeout: float):
        t0 = time.time()
        while _state_name(f) == "PROCESSING":
            if time.time() - t0 > poll_timeout:
                raise TimeoutError("等待文件 ACTIVE 超时")
            time.sleep(3)
            f = client.files.get(name=f.name)
        state = _state_name(f)
        if state == "ACTIVE":
            return f
        raise RuntimeError(f"文件状态异常：{state}")

    # ---- 上下文缓存 ----
    def ensure_context_cache(self, client, model: str, file, system_instruction: str,
                             ttl: str, force: bool = False) -> Optional[str]:
        """返回 cache.name；任何失败都返回 None（降级为每次直传 file part）。"""
        fp = self._find_fp_by_file(file.name)
        entry = self._data.get(fp, {}) if fp else {}
        cc = entry.get("context_cache")
        if cc and not force and cc.get("model") == model and not _expired(cc.get("expire_time")):
            self.log.info(f"[cache] 复用上下文缓存 {cc['name']}")
            return cc["name"]
        try:
            part = genai_types.Part(
                file_data=genai_types.FileData(file_uri=file.uri, mime_type=file.mime_type or "video/mp4")
            )
            cache = client.caches.create(
                model=model,
                config=genai_types.CreateCachedContentConfig(
                    contents=[part],
                    system_instruction=system_instruction,
                    ttl=ttl,
                    display_name="video-analyze",
                ),
            )
            self.log.info(f"[cache] 已创建上下文缓存 {cache.name}")
            if fp:
                self._data[fp]["context_cache"] = {
                    "name": cache.name,
                    "model": model,
                    "expire_time": _dt_iso(getattr(cache, "expire_time", None)),
                }
                self._save()
            return cache.name
        except Exception as e:
            self.log.warning(f"[cache] 创建上下文缓存失败，降级为直传视频：{e}")
            return None

    def _find_fp_by_file(self, file_name: str) -> Optional[str]:
        for fp, entry in self._data.items():
            if entry.get("file_name") == file_name:
                return fp
        return None


# ---------------------------------------------------------------------------
# 3：按维度结果缓存
# ---------------------------------------------------------------------------

class ResultCache:
    def __init__(self, cache_dir: str, logger, force_set: Optional[set] = None):
        self.dir = os.path.join(cache_dir, "results")
        os.makedirs(self.dir, exist_ok=True)
        self.log = logger
        self.force = force_set or set()  # 维度名集合；"*" 表示全部
        self.hits = 0
        self.misses = 0

    def _path(self, dim: str) -> str:
        return os.path.join(self.dir, f"{dim}.json")

    def get(self, dim: str, sig: str) -> Optional[Any]:
        if "*" in self.force or dim in self.force or any(dim.startswith(f) for f in self.force):
            return None
        p = self._path(dim)
        if not os.path.exists(p):
            return None
        try:
            blob = read_json(p)
        except Exception:
            return None
        if blob.get("sig") != sig:
            return None
        self.hits += 1
        self.log.info(f"[{dim}] 结果缓存命中")
        return blob.get("data")

    def put(self, dim: str, sig: str, data: Any) -> None:
        atomic_write_json(self._path(dim), {"sig": sig, "saved_at": _now_iso(), "data": data})

    @staticmethod
    def sig(*parts: Any) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(repr(p).encode("utf-8"))
        return h.hexdigest()[:24]


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _state_name(f) -> str:
    st = getattr(f, "state", None)
    if st is None:
        return "ACTIVE"  # 某些后端不返回 state，视作可用
    return getattr(st, "name", str(st))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt_iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    try:
        return dt.isoformat()
    except Exception:
        return None


def _expired(iso: Optional[str]) -> bool:
    if not iso:
        return True
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= datetime.now(timezone.utc)
    except Exception:
        return True
