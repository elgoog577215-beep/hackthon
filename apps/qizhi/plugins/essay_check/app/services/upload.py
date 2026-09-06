import os
import uuid

from app.database import AsyncSessionLocal, get_sync_session
from app.models import Task, TaskPage
from app.services.oss import pdf_to_images, upload_image, get_image_url_or_base64, get_data_dir
from app.services.classifier import classify_page, check_page
from app.config import MAX_PDF_PAGES

from app.logger import get_logger

logger = get_logger(__name__)


async def handle_upload(file_bytes: bytes, filename: str) -> dict:
    """Process uploaded PDF: convert to images, upload to OSS, create DB records."""
    try:
        images = pdf_to_images(file_bytes, max_pages=MAX_PDF_PAGES)
    except ValueError as e:
        raise e
    except Exception as e:
        raise ValueError(f"PDF解析失败: {e}")

    task_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        task = Task(
            id=task_id,
            filename=filename,
            file_size=len(file_bytes),
            total_pages=len(images),
            status="uploaded",
            current_stage="文件已接收，正在转换图片",
        )
        db.add(task)

        for i, img_bytes in enumerate(images):
            key = upload_image(img_bytes, task_id, i + 1)
            page = TaskPage(
                task_id=task_id,
                page_number=i + 1,
                image_url=key,
                status="pending",
            )
            db.add(page)

        await db.commit()

    logger.info(f"Task {task_id} created: {filename}, {len(images)} pages")
    return {"task_id": task_id, "filename": filename, "total_pages": len(images), "status": "uploaded"}


def process_page_stage(page_id: uuid.UUID):
    """Execute page processing pipeline with resume capability.

    State flow:
      pending → classifying → classified → completed
      Any intermediate state + error → pending (retry<3) or failed

    Page stays in classified between classify/check (no explicit 'checking' state).

    Runs in ThreadPoolExecutor — uses sync session.
    """
    db = get_sync_session()
    try:
        page = db.get(TaskPage, page_id)
        if not page or page.status in ("completed", "failed"):
            return

        # ── Stage 1: classify ──
        if page.status in ("pending", "classifying"):
            page.status = "classifying"
            db.commit()

            try:
                signed_url = get_image_url_or_base64(page.image_url)
            except Exception as e:
                logger.warning(f"Failed to get image data for page {page.page_number}: {e}")
                page.error_message = f"图片数据获取失败: {e}"
                _retry_or_fail(page, "图片数据获取失败")
                db.commit()
                return

            page.error_message = None
            db.commit()

            result = classify_page(signed_url)
            if not result:
                logger.warning(f"Page {page.page_number} classify returned None")
                _retry_or_fail(page, "页面分类失败")
                db.commit()
                return

            page.page_type = result.get("page_type", "unknown")
            page.extracted_content = result
            page.status = "classified"
            db.commit()
            logger.info(f"Page {page.page_number} classified as {page.page_type}")

            # 保存数据提取信息到本地 txt 文件
            data_info = result.get("data_info", "")
            if data_info:
                data_dir = get_data_dir(task_id=page.task_id)
                data_dir.mkdir(parents=True, exist_ok=True)
                data_file = data_dir / f"page_{page.page_number:03d}_data.txt"
                data_file.write_text(
                    f"=== 第 {page.page_number} 页（{page.page_type}） ===\n"
                    f"页面描述: {result.get('description', '')}\n\n"
                    f"提取数据:\n{data_info}\n",
                    encoding="utf-8",
                )
                logger.info(f"Saved data info for page {page.page_number}")

        # ── Stage 2: check (resume from classified) ──
        if page.status == "classified":
            if not page.page_type:
                _retry_or_fail(page, "页面未分类")
                db.commit()
                return

            try:
                signed_url = get_image_url_or_base64(page.image_url)
            except Exception as e:
                logger.warning(f"Failed to get image data for page {page.page_number}: {e}")
                _retry_or_fail(page, "图片数据获取失败")
                db.commit()
                return

            result = check_page(
                signed_url,
                page.page_type,
                page.extracted_content.get("description", "") if page.extracted_content else "",
            )
            if result is None:
                logger.warning(f"Page {page.page_number} check returned None")
                _retry_or_fail(page, "页面检查失败")
            else:
                page.check_results = result
                page.status = "completed"

            db.commit()
            logger.info(f"Page {page.page_number} check completed")

    except Exception as e:
        logger.error(f"Page {page_id} processing error: {e}")
        try:
            db2 = get_sync_session()
            p = db2.get(TaskPage, page_id)
            if p and p.status not in ("completed", "failed"):
                p.error_message = str(e)
                _retry_or_fail(p, "处理异常")
                db2.commit()
        except Exception:
            pass
        finally:
            db2.close()
    finally:
        db.close()


def _retry_or_fail(page: TaskPage, error_msg: str):
    """Set page to pending for retry or failed if retries exhausted."""
    page.retry_count += 1
    if page.retry_count >= 3:
        page.status = "failed"
        page.error_message = error_msg
    else:
        page.status = "pending"
        page.error_message = f"{error_msg}，等待重试"
