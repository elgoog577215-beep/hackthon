import httpx
import json
import time
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func

from common.config import settings
from common.models.exception import BizException, SystemException
from common.utils.http import actor_headers
from common.utils.logger import get_logger
from infra.db import UserEssayTask, User
from infra.db.sequence import generate_id
from service.essay_check.export_service import generate_report_docx, export_to_zip, export_to_zip_from_bytes
from service.essay_check.models import (
    EssayDomainProblemStat,
    EssayOverview,
    EssayOverviewOtherStatus,
    EssayScoreCounts,
    EssayTaskItem,
)

logger = get_logger(__name__)

_SCORE_QUALIFIED = "合格"
_SCORE_NEED_REVISION = "需修改"
_SCORE_UNQUALIFIED = "不合格"
_VALID_SCORES = {_SCORE_QUALIFIED, _SCORE_NEED_REVISION, _SCORE_UNQUALIFIED}
_REF_ISSUE_DOMAIN = "参考文献格式问题"


class EssayCheckService:
    """
    论文审查服务：对接 essay_check 微服务
    """

    def __init__(self, db):
        self.db = db

    async def submit_essay(self, file_bytes: bytes, filename: str, current_user: User) -> str:
        """上传论文到微服务，并创建 user_essay_task 记录，返回本地 task id。"""
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{settings.ESSAY_CHECK_SERVICE_URL}/api/v1/tasks/upload",
                    files={"file": (filename, file_bytes, "application/pdf")},
                    headers=actor_headers(current_user),
                )
            if resp.status_code not in (200, 202):
                logger.error(f"[service.py] 论文微服务上传失败: {resp.status_code} {resp.text}")
                raise SystemException(f"论文微服务上传失败: {resp.status_code} {resp.text}")

            micro_data = resp.json()
            micro_task_id = str(micro_data["task_id"])
            total_pages = micro_data.get("total_pages")
        except httpx.RequestError as e:
            logger.error(f"[service.py] 无法连接论文微服务: {e}")
            raise SystemException(f"无法连接论文微服务: {e}")

        task = UserEssayTask(
            id=generate_id(),
            user_id=current_user.id,
            filename=filename,
            task_id=micro_task_id,
            status="uploaded",
            total_pages=total_pages,
        )
        self.db.add(task)
        await self.db.commit()
        return task.id

    async def list_user_essays(self, current_user: User) -> list[EssayTaskItem]:
        """查询当前用户的论文任务列表，按创建时间倒序。

        对尚未结束（completed / failed）的任务，逐一从微服务拉取最新状态并同步到本地。
        """
        result = await self.db.execute(
            select(UserEssayTask)
            .where(UserEssayTask.user_id == current_user.id)
            .order_by(UserEssayTask.create_time.desc())
        )
        rows = result.scalars().all()

        # 对未结束的任务，去微服务同步状态
        pending_tasks = [t for t in rows if t.status not in ("completed", "failed")]
        for task in pending_tasks:
            try:
                micro_data = await self._fetch_micro_task(task, current_user)
                micro_status = micro_data.get("status", task.status)
                if micro_status != task.status:
                    task.status = micro_status
                if task.total_pages is None and micro_data.get("total_pages"):
                    task.total_pages = micro_data.get("total_pages")
                if micro_status == "completed" and micro_data.get("overall_score") and not task.result:
                    task.result = json.dumps(micro_data, ensure_ascii=False)
            except (BizException, SystemException) as e:
                logger.warning(f"[service.py] 列表同步任务 {task.id} 状态失败: {e}")
        if pending_tasks:
            await self.db.commit()

        return [
            EssayTaskItem(
                id=t.id,
                filename=t.filename,
                task_id=t.task_id,
                status=t.status,
                total_pages=t.total_pages,
                create_time=t.create_time.isoformat() if t.create_time else "",
            )
            for t in rows
        ]

    async def get_overview(self, current_user: User) -> EssayOverview:
        """汇总当前用户全部历史中已完成论文的审查结论与高频问题域。"""
        completed_result = await self.db.execute(
            select(UserEssayTask).where(
                UserEssayTask.user_id == current_user.id,
                UserEssayTask.status == "completed",
            )
        )
        completed_tasks = completed_result.scalars().all()
        total_completed = len(completed_tasks)

        score_counts = {_SCORE_QUALIFIED: 0, _SCORE_NEED_REVISION: 0, _SCORE_UNQUALIFIED: 0}
        domain_paper_counts: dict[str, int] = {}
        score_known = 0

        for task in completed_tasks:
            report = await self._load_report_payload(task, current_user)
            if not report:
                continue

            score = _normalize_overall_score(report.get("overall_score"))
            if score in _VALID_SCORES:
                score_counts[score] += 1
                score_known += 1

            for domain in _failed_domains_in_report(report):
                domain_paper_counts[domain] = domain_paper_counts.get(domain, 0) + 1

        status_rows = await self.db.execute(
            select(UserEssayTask.status, func.count())
            .where(UserEssayTask.user_id == current_user.id)
            .group_by(UserEssayTask.status)
        )
        status_map = {row[0]: row[1] for row in status_rows.all()}
        processing = sum(
            status_map.get(s, 0)
            for s in ("uploaded", "processing", "summarizing")
        )
        failed = status_map.get("failed", 0)

        top_domains: list[EssayDomainProblemStat] = []
        if total_completed > 0:
            sorted_items = sorted(
                domain_paper_counts.items(),
                key=lambda x: (-x[1], x[0]),
            )[:5]
            for domain, count in sorted_items:
                top_domains.append(
                    EssayDomainProblemStat(
                        domain=domain,
                        paper_count=count,
                        percentage=round(count / total_completed * 100, 1),
                    )
                )

        return EssayOverview(
            total_completed=total_completed,
            score_counts=EssayScoreCounts(
                qualified=score_counts[_SCORE_QUALIFIED],
                need_revision=score_counts[_SCORE_NEED_REVISION],
                unqualified=score_counts[_SCORE_UNQUALIFIED],
            ),
            score_known=score_known,
            top_problem_domains=top_domains,
            other_status=EssayOverviewOtherStatus(
                processing=processing,
                failed=failed,
            ),
        )

    async def _load_report_payload(
        self, task: UserEssayTask, current_user: User
    ) -> dict | None:
        """读取已完成任务的报告 JSON（本地缓存优先，缺失时拉微服务）。"""
        if task.result:
            try:
                return json.loads(task.result)
            except json.JSONDecodeError:
                logger.warning(f"[service.py] 任务 {task.id} 本地 result 非合法 JSON")

        try:
            data = await self._fetch_micro_task(task, current_user)
        except (BizException, SystemException) as e:
            logger.warning(f"[service.py] 概览拉取任务 {task.id} 报告失败: {e}")
            return None

        if data.get("status") != "completed":
            return None

        task.result = json.dumps(data, ensure_ascii=False)
        await self.db.commit()
        return data

    async def get_essay_status(self, task_id: str, current_user: User) -> dict:
        """根据本地 task_id 获取任务完整信息（进度+报告）。

        已完成的任务直接从本地缓存读取，未完成的才去查微服务。
        """
        task = await self._get_user_task(task_id, current_user)

        # 已完成且本地有缓存结果，且距上次更新未超过45分钟，直接返回
        CACHE_EXPIRE_MINUTES = 45
        if (
            task.status == "completed"
            and task.result
            and task.update_time
            and datetime.now(timezone.utc).replace(tzinfo=None) - task.update_time.replace(tzinfo=None)
            < timedelta(minutes=CACHE_EXPIRE_MINUTES)
        ):
            data = json.loads(task.result)
            return {
                "task_id": task.id,
                "micro_task_id": task.task_id,
                "filename": task.filename,
                "status": data.get("status"),
                "current_stage": data.get("current_stage"),
                "progress": data.get("progress"),
                "pages": data.get("pages", []),
                "total_pages": task.total_pages or data.get("progress", {}).get("total_pages"),
                "overall_score": data.get("overall_score"),
                "summary": data.get("summary"),
                "check_domains": data.get("check_domains"),
                "reference_issues": data.get("reference_issues"),
                "recommendations": data.get("recommendations"),
            }

        # 未完成，查微服务获取最新状态
        data = await self._fetch_micro_task(task, current_user)

        # 同步更新本地状态
        task.status = data.get("status", task.status)
        if task.total_pages is None:
            task.total_pages = data.get("total_pages")
        if data.get("status") == "completed" and data.get("overall_score"):
            task.result = json.dumps(data, ensure_ascii=False)
        await self.db.commit()

        return {
            "task_id": task.id,
            "micro_task_id": task.task_id,
            "filename": task.filename,
            "status": data.get("status"),
            "current_stage": data.get("current_stage"),
            "progress": data.get("progress"),
            "pages": data.get("pages", []),
            "total_pages": task.total_pages or data.get("progress", {}).get("total_pages"),
            "overall_score": data.get("overall_score"),
            "summary": data.get("summary"),
            "check_domains": data.get("check_domains"),
            "reference_issues": data.get("reference_issues"),
            "recommendations": data.get("recommendations"),
        }

    async def _fetch_micro_task(self, task: UserEssayTask, current_user: User | None = None) -> dict:
        """请求微服务获取任务详情（单接口包含进度+报告）。"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(
                    f"{settings.ESSAY_CHECK_SERVICE_URL}/api/v1/tasks/{task.task_id}",
                    headers=actor_headers(current_user),
                )
        except httpx.RequestError as e:
            logger.error(f"[service.py] 无法连接论文微服务: {e}")
            raise SystemException(f"无法连接论文微服务: {e}")

        if resp.status_code == 404:
            logger.warning(f"[service.py] 微服务中任务不存在")
            raise BizException("微服务中任务不存在")
        if resp.status_code != 200:
            logger.error(f"[service.py] 微服务查询失败: {resp.status_code} {resp.text}")
            raise SystemException(f"微服务查询失败: {resp.status_code} {resp.text}")

        return resp.json()

    async def _get_user_task(self, task_id: str, current_user: User) -> UserEssayTask:
        """获取属于当前用户的 task，否则抛异常。"""
        result = await self.db.execute(
            select(UserEssayTask).where(
                UserEssayTask.id == task_id,
                UserEssayTask.user_id == current_user.id,
            )
        )
        task = result.scalars().first()
        if not task:
            logger.warning(f"[service.py] 任务不存在或无权访问")
            raise BizException("任务不存在或无权访问")
        return task

    async def delete_essay(self, task_id: str, current_user: User) -> None:
        """删除本地论文任务记录。

        先校验任务归属，再物理删除本地记录；同时尝试通知微服务清理对应数据，
        微服务侧失败仅记录日志，不阻塞本地删除。
        """
        task = await self._get_user_task(task_id, current_user)
        await self.db.delete(task)
        await self.db.commit()

    async def export_reports(
        self, task_ids: list[str], current_user: User, export_scope: str = "summary_only"
    ) -> tuple[bytes, str]:
        """导出多个论文任务的审查报告为 zip 文件。

        Args:
            task_ids: 要导出的任务ID列表。
            current_user: 当前用户，用于权限校验。
            export_scope: summary_only | summary_problem_pages | full

        Returns:
            (zip 字节内容, 文件名)。
        """
        if not task_ids:
            raise BizException("请选择要导出的任务")

        task_reports: list[dict] = []
        skipped: list[str] = []

        for tid in task_ids:
            task = await self._get_user_task(tid, current_user)
            if task.status != "completed":
                skipped.append(task.filename)
                continue

            # 获取报告数据
            if task.result:
                data = json.loads(task.result)
            else:
                # 已完成但本地无缓存，从微服务拉取
                data = await self._fetch_micro_task(task, current_user)

            report_data = {
                "filename": task.filename,
                "overall_score": data.get("overall_score", ""),
                "summary": data.get("summary", ""),
                "check_domains": data.get("check_domains", []),
                "reference_issues": data.get("reference_issues"),
                "recommendations": data.get("recommendations"),
                "pages": data.get("pages", []),
            }
            task_reports.append({
                "filename": task.filename,
                "report_data": report_data,
            })

        if not task_reports:
            raise BizException("所选任务均未完成，无法导出")

        if len(task_ids) == 1 and len(task_reports) == 1:
            # 单篇导出：直接返回 docx
            item = task_reports[0]
            safe_name = item["filename"].rsplit(".", 1)[0]
            for ch in r'\/:*?"<>|':
                safe_name = safe_name.replace(ch, "_")
            return generate_report_docx(item["report_data"], export_scope=export_scope), f"{safe_name}.docx"

        # 多篇导出：打包 zip
        zip_bytes = export_to_zip(task_reports, export_scope=export_scope)
        return zip_bytes, "论文分析报告.zip"

    async def stream_export_reports(
        self, task_ids: list[str], current_user: User, export_scope: str = "summary_only"
    ):
        """以 SSE 流方式导出，逐文件报告进度（含生成文件时间），完成后返回 token。

        流程：
        1. 收集报告数据（async，较快）
        2. 逐个生成 docx 文件（CPU 密集），每生成完一个就 yield 进度
        3. 多篇则打包 zip，完成后返回 token

        Yields:
            build_sse_response 构造的 SSE 事件字典。
        """
        from common.utils.sse import build_sse_response, SseEventEnum

        if not task_ids:
            yield build_sse_response(SseEventEnum.ERROR, {"error": "请选择要导出的任务"})
            return

        # ── 阶段一：收集数据 ──
        task_reports: list[dict] = []
        total = len(task_ids)

        yield build_sse_response(SseEventEnum.START, {"total": total, "phase": "collecting"})

        for i, tid in enumerate(task_ids, start=1):
            try:
                task = await self._get_user_task(tid, current_user)
            except BizException:
                yield build_sse_response(SseEventEnum.EXPORT_PROGRESS, {
                    "current": i,
                    "total": total,
                    "filename": "未知",
                    "status": "skipped",
                    "message": "无权访问或不存在",
                })
                continue

            if task.status != "completed":
                yield build_sse_response(SseEventEnum.EXPORT_PROGRESS, {
                    "current": i,
                    "total": total,
                    "filename": task.filename,
                    "status": "skipped",
                    "message": "任务未完成",
                })
                continue

            # 获取报告数据
            if task.result:
                data = json.loads(task.result)
            else:
                try:
                    data = await self._fetch_micro_task(task, current_user)
                except Exception:
                    yield build_sse_response(SseEventEnum.EXPORT_PROGRESS, {
                        "current": i,
                        "total": total,
                        "filename": task.filename,
                        "status": "error",
                        "message": "获取报告失败",
                    })
                    continue

            report_data = {
                "filename": task.filename,
                "overall_score": data.get("overall_score", ""),
                "summary": data.get("summary", ""),
                "check_domains": data.get("check_domains", []),
                "reference_issues": data.get("reference_issues"),
                "recommendations": data.get("recommendations"),
                "pages": data.get("pages", []),
            }
            task_reports.append({
                "filename": task.filename,
                "report_data": report_data,
            })

            yield build_sse_response(SseEventEnum.EXPORT_PROGRESS, {
                "current": i,
                "total": total,
                "filename": task.filename,
                "status": "done",
                "phase": "collecting",
            })

        if not task_reports:
            yield build_sse_response(SseEventEnum.ERROR, {"error": "所选任务均未完成，无法导出"})
            return

        # ── 阶段二：逐个生成 docx 文件 ──
        generated_count = 0
        docx_files: list[tuple[str, bytes]] = []  # (filename, content)

        if len(task_ids) == 1 and len(task_reports) == 1:
            # 单篇：直接生成 docx
            item = task_reports[0]
            safe_name = item["filename"].rsplit(".", 1)[0]
            for ch in r'\/:*?"<>|':
                safe_name = safe_name.replace(ch, "_")
            filename = f"{safe_name}.docx"
            try:
                content = generate_report_docx(item["report_data"], export_scope=export_scope)
            except Exception as e:
                logger.error(f"[service.py] 生成报告失败 {item['filename']}: {e}")
                yield build_sse_response(SseEventEnum.ERROR, {"error": f"报告生成失败: {item['filename']} - {e}"})
                return
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

            token = export_job_manager.store(content, filename, content_type)
            yield build_sse_response(SseEventEnum.EXPORT_COMPLETE, {
                "token": token,
                "filename": filename,
                "content_type": content_type,
                "exported_count": 1,
                "total": total,
            })
        else:
            # 多篇：逐个生成 docx，每生成完一个就 yield 进度
            for idx, item in enumerate(task_reports):
                safe_name = item["filename"].rsplit(".", 1)[0]
                for ch in r'\/:*?"<>|':
                    safe_name = safe_name.replace(ch, "_")
                docx_filename = f"{safe_name}.docx"

                # CPU 密集操作：生成 docx
                try:
                    docx_bytes = generate_report_docx(item["report_data"], export_scope=export_scope)
                    docx_files.append((docx_filename, docx_bytes))
                    generated_count += 1

                    yield build_sse_response(SseEventEnum.EXPORT_PROGRESS, {
                        "current": generated_count,
                        "total": len(task_reports),
                        "filename": item["filename"],
                        "status": "done",
                        "phase": "generating",
                    })
                except Exception as e:
                    logger.error(f"[service.py] 生成报告失败 {item['filename']}: {e}")
                    yield build_sse_response(SseEventEnum.EXPORT_PROGRESS, {
                        "current": generated_count,
                        "total": len(task_reports),
                        "filename": item["filename"],
                        "status": "error",
                        "phase": "generating",
                        "message": str(e),
                    })

            if not docx_files:
                yield build_sse_response(SseEventEnum.ERROR, {"error": "所有报告生成均失败，无法导出"})
                return

            # 全部 docx 生成完毕，打包 zip
            yield build_sse_response(SseEventEnum.EXPORT_GENERATING, {
                "message": "正在打包为 zip 文件...",
            })
            zip_input = []
            for fname, fbytes in docx_files:
                zip_input.append({"filename": fname, "report_data": {}})
            # 直接打包已有的 docx 字节
            zip_bytes = export_to_zip_from_bytes(docx_files)
            filename = "论文分析报告.zip"
            content_type = "application/zip"

            token = export_job_manager.store(zip_bytes, filename, content_type)
            yield build_sse_response(SseEventEnum.EXPORT_COMPLETE, {
                "token": token,
                "filename": filename,
                "content_type": content_type,
                "exported_count": generated_count,
                "total": total,
            })


# ── 导出任务管理器（内存存储 + TTL 清理） ──

class _ExportJob:
    __slots__ = ("token", "content", "filename", "content_type", "created_at")

    def __init__(self, token: str, content: bytes, filename: str, content_type: str):
        self.token = token
        self.content = content
        self.filename = filename
        self.content_type = content_type
        self.created_at = time.time()


class ExportJobManager:
    """内存存储导出文件，TTL 自动过期。"""

    TTL_SECONDS = 300  # 5 分钟

    def __init__(self):
        self._jobs: dict[str, _ExportJob] = {}

    def store(self, content: bytes, filename: str, content_type: str) -> str:
        token = uuid.uuid4().hex[:16]
        self._jobs[token] = _ExportJob(token, content, filename, content_type)
        self._cleanup()
        return token

    def get(self, token: str) -> _ExportJob | None:
        job = self._jobs.get(token)
        if job and (time.time() - job.created_at) < self.TTL_SECONDS:
            return job
        if job:
            del self._jobs[token]
        return None

    def _cleanup(self):
        now = time.time()
        expired = [t for t, j in self._jobs.items() if now - j.created_at >= self.TTL_SECONDS]
        for t in expired:
            del self._jobs[t]


export_job_manager = ExportJobManager()


def _normalize_overall_score(raw) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text in _VALID_SCORES:
        return text
    if "不合格" in text:
        return _SCORE_UNQUALIFIED
    if "需修改" in text or "修改" in text:
        return _SCORE_NEED_REVISION
    if "合格" in text:
        return _SCORE_QUALIFIED
    return None


def _failed_domains_in_report(report: dict) -> set[str]:
    """返回该篇报告中至少有一项不通过的检查域名称集合。"""
    failed: set[str] = set()
    for domain_block in report.get("check_domains") or []:
        if not isinstance(domain_block, dict):
            continue
        name = (domain_block.get("domain") or "").strip() or "未命名检查域"
        points = domain_block.get("check_points") or []
        if any(
            isinstance(cp, dict) and cp.get("passed") is False
            for cp in points
        ):
            failed.add(name)

    ref_issues = report.get("reference_issues")
    if isinstance(ref_issues, list) and len(ref_issues) > 0:
        failed.add(_REF_ISSUE_DOMAIN)

    return failed
