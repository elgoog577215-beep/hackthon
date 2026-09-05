import base64
import hashlib
import hmac
import shutil
import time
import uuid
from pathlib import Path

import fitz  # PyMuPDF
import oss2


from app.config import (
    ENV, IMAGE_BASE_URL, IMAGE_SIGN_SECRET, LOCAL_IMAGE_DIR,
    OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_BUCKET_NAME,
    OSS_ENDPOINT, OSS_URL_PREFIX
)

from app.logger import get_logger

logger = get_logger(__name__)

_LOCAL_URL_EXPIRY = 3600  # 1 hour


def use_local_storage() -> bool:
    return ENV == "prod"


def _get_bucket():
    auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET_NAME)


def _local_image_path(task_id: uuid.UUID, page_number: int) -> Path:
    return Path(LOCAL_IMAGE_DIR) / "essay_images" / str(task_id) / f"page_{page_number:03d}.png"


def get_data_dir(task_id: uuid.UUID) -> Path:
    """返回某篇论文的数据提取目录路径（各页 data_info 的 txt 存储位置）。"""
    return Path(LOCAL_IMAGE_DIR) / "essay_data" / str(task_id)


def _local_key_to_path(object_key: str) -> Path:
    return Path(LOCAL_IMAGE_DIR) / object_key


def _sign(object_key: str, expiry_ts: int) -> str:
    """HMAC-SHA256 signature for a local image URL."""
    msg = f"{object_key}:{expiry_ts}"
    return hmac.new(IMAGE_SIGN_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def verify_local_image_token(expiry_ts: int, signature: str, object_key: str) -> str | None:
    """Verify signed URL token. Returns error message or None if valid."""
    try:
        ts = int(expiry_ts)
    except (ValueError, TypeError):
        return "无效的时间戳"
    if time.time() > ts:
        return "链接已过期"
    expected = _sign(object_key, ts)
    if not hmac.compare_digest(signature, expected):
        return "签名不匹配"
    return None


# ── Core functions ─────────────────────────────────────────────────────────


def store_image(image_bytes: bytes, task_id: uuid.UUID, page_number: int) -> str:
    """Store image bytes, return the object key."""
    if use_local_storage():
        path = _local_image_path(task_id, page_number)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        key = f"essay_images/{task_id}/page_{page_number:03d}.png"
        logger.info(f"[PROD] Stored image locally: {key}")
        return key
    else:
        bucket = _get_bucket()
        object_key = f"essay_images/{task_id}/page_{page_number:03d}.png"
        bucket.put_object(object_key, image_bytes)
        logger.info(f"[DEV] Uploaded image to OSS: {object_key}")
        return object_key


def get_image_url(object_key: str) -> str:
    """Generate an accessible URL for the stored image."""
    if not object_key:
        return ""
    if use_local_storage():
        expiry = int(time.time()) + _LOCAL_URL_EXPIRY
        sig = _sign(object_key, expiry)
        return f"{IMAGE_BASE_URL}/api/v1/images/{object_key}?t={expiry}&s={sig}"
    else:
        bucket = _get_bucket()
        return bucket.sign_url("GET", object_key, 3600)


def get_image_url_or_base64(object_key: str) -> str:
    """返回可传给 LLM 的图片标识。DEV: OSS 签名 URL；PROD: base64 data URI。"""
    if use_local_storage():
        data = get_image_data(object_key)
        if data is None:
            raise ValueError(f"图片不存在: {object_key}")
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"
    else:
        bucket = _get_bucket()
        return bucket.sign_url("GET", object_key, 3600)


def get_image_data(object_key: str) -> bytes | None:
    """Read raw image bytes. In PROD reads from local disk; in DEV fetches from OSS."""
    if use_local_storage():
        path = _local_key_to_path(object_key)
        if not path.exists():
            return None
        return path.read_bytes()
    else:
        bucket = _get_bucket()
        result = bucket.get_object(object_key)
        return result.read()


def delete_task_images(task_id: uuid.UUID):
    """Delete all images for a task, and clean up associated data files."""
    if use_local_storage():
        task_dir = Path(LOCAL_IMAGE_DIR) / "essay_images" / str(task_id)
        if task_dir.exists():
            shutil.rmtree(task_dir)
            logger.info(f"[PROD] Deleted local images: {task_dir}")
        data_dir = get_data_dir(task_id)
        if data_dir.exists():
            shutil.rmtree(data_dir)
            logger.info(f"[PROD] Deleted data files: {data_dir}")
    else:
        bucket = _get_bucket()
        prefix = f"essay_images/{task_id}/"
        for obj in oss2.ObjectIterator(bucket, prefix=prefix):
            bucket.delete_object(obj.key)
        logger.info(f"[DEV] Deleted OSS images: {prefix}")


def image_to_base64(object_key: str) -> str | None:
    """Read image and return base64-encoded string, or None if not found."""
    data = get_image_data(object_key)
    if data is None:
        return None
    return base64.b64encode(data).decode("ascii")


# ── Legacy wrappers (backward compatibility) ──────────────────────────────


def upload_image(image_bytes: bytes, task_id: uuid.UUID, page_number: int) -> str:
    return store_image(image_bytes, task_id, page_number)


def get_signed_url(object_key: str) -> str:
    return get_image_url(object_key)


def pdf_to_images(pdf_bytes: bytes, max_pages: int = 150) -> list[bytes]:
    """Convert PDF to PNG images, one per page. Returns list of PNG bytes."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if len(doc) > max_pages:
        raise ValueError(f"PDF has {len(doc)} pages, maximum allowed is {max_pages}")
    images = []
    for page in doc:
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))
    doc.close()
    return images
