"""练习题定向重建：把「受影响的题目」接进共用下游重建执行链。

## 这个模块补的是哪一段

`downstream_rebuild.execute_rebuild` 按 `pipeline_for()` 把下游对象分派给各条
既有管线。表达（PPT/讲义）与正文块都已有 runner，**唯独 `runners["practice"]`
没有人提供**——所以点重建后，练习题只会如实回执「仍待重建」（executor 在缺
runner 时标 `blocked`，不静默跳过）。本模块提供那个缺失的 runner。

## 为什么是「登记作业」而不是「就地出题」

出题是 10 阶段异步作业（`question_bank_jobs.QUESTION_BANK_REBUILD_STAGES`），
自带作业仓库、心跳与断点恢复。在教师的「应用修订」请求里同步跑，教师要等几
分钟，且失败没有恢复位点。所以这里只做三件事：

1. 把下游对象（练习/题目/掌握标准）解析成**题库里真实存在的 `revision_id`**；
2. 通过既有入口登记一个 `scope="items"` 的定向重建作业；
3. 返回 `candidate_ready`，由既有出题管线接手，教师确认后才转正。

对应 executor 的「定向重建候选」语义：成功登记 = 候选就绪，不是重建完成。

## 不建第二真源

- **不自己出题**：不调 AI、不写 bundle。真正的重建仍由题库路由在启动时
  注册的正式 executor 完成；业务层不反向导入路由。
- **不自己定 `revision_id`**：`item_id` / `question_id` 到 `revision_id` 的映射
  只从当前活动 bundle 读，读不到就如实失败，不猜、不造。
- **不绕过质量门与修订机制**：登记的作业走 `reconcile_item_question_bank`，
  该路径保留人工评审痕迹、保留 `lifecycle_status`，并在合并前跑
  `evaluate_question_item_quality`。本模块一个门都不碰。

## 失败时旧题必须继续可读可作答

这是产品级承诺。本模块的失败路径**只返回失败回执，不做任何写入**：

- 解析不到题目 → 返回 `failed`，bundle 一个字节都没动；
- 登记作业抛错 → 返回 `failed`，bundle 一个字节都没动；
- 作业登记成功但后续出题失败 → 由既有作业链处理，
  `_restore_bundle_pointer` 会把活动指针回滚到旧 bundle。

三条路径下 `question_bank_repository` 的 `current.json` 都仍指向旧 bundle，
`approved_formal_tasks` 照常返回旧题，学生照常作答。测试正面锁死这一点。
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from course_versioning import stable_hash

PRACTICE_REBUILD_RECEIPT_SCHEMA = "practice_targeted_rebuild_receipt_v1"

# executor 通过 pipeline_for() 把这三类对象路由到 runners["practice"]。
# 与 downstream_rebuild._PRACTICE_TYPES 保持一致；那里是真源，这里只是文档。
PRACTICE_OBJECT_TYPES = ("practice", "question", "mastery_criterion")


def _text(value: Any) -> str:
    return str(value or "").strip()


def resolve_question_revisions(
    bundle: dict[str, Any] | None,
    *,
    object_id: str,
    section_id: str = "",
) -> list[str]:
    """下游对象 ID -> 题库中真实存在的 `revision_id` 列表。

    影响报告里的练习对象用的是 `learning_assets` 的 `question_id`
    （`stable_hash({course, node, kind}, prefix="q_")`），而定向重建作业要的是
    题库 item 的 `revision_id`。两者不是一个命名空间，必须显式对齐。

    对齐只走 bundle 自己记录的字段，不做任何启发式猜测：

    1. `object_id` 直接就是某个 item 的 `revision_id`（题目对象直接来自题库）；
    2. `object_id` 是某个 item 的 `item_id`；
    3. 都不是，则退回按 `section_id` 取该小节下的题——练习资产是按
       (node_id, practice_level) 聚合的，一个小节对象可能对应多道题。

    找不到就返回空列表，由调用方如实报失败。宁可报「解析不到」，也不能
    随便挑一道题重建——那会重建错题目，且教师无从发现。
    """
    items = [
        item for item in (bundle or {}).get("items") or []
        if isinstance(item, dict)
    ]
    if not items:
        return []

    target = _text(object_id)
    if target:
        by_revision = [
            _text(item.get("revision_id"))
            for item in items
            if _text(item.get("revision_id")) == target
        ]
        if by_revision:
            return _expand_atomic_revisions(bundle, by_revision)

        by_item_id = [
            _text(item.get("revision_id"))
            for item in items
            if _text(item.get("item_id")) == target
            and _text(item.get("revision_id"))
        ]
        if by_item_id:
            return _expand_atomic_revisions(bundle, by_item_id)

    section = _text(section_id)
    if not section:
        return []
    by_section = [
        _text(item.get("revision_id"))
        for item in items
        if _text(item.get("revision_id"))
        and section in _node_ids(item)
        # 已退休的题不再是课程资产，重建它没有意义。
        and _text(item.get("lifecycle_status")) != "retired"
    ]
    return _expand_atomic_revisions(bundle, by_section)


def _expand_atomic_revisions(
    bundle: dict[str, Any] | None,
    revision_ids: list[str],
) -> list[str]:
    from question_bank import expand_question_atomic_revisions

    return expand_question_atomic_revisions(
        bundle,
        revision_ids=revision_ids,
    )


def _node_ids(item: dict[str, Any]) -> set[str]:
    values = item.get("node_ids") or []
    if not isinstance(values, list):
        values = []
    result = {_text(value) for value in values if _text(value)}
    single = _text(item.get("node_id"))
    if single:
        result.add(single)
    return result


def build_practice_rebuild_runner(
    *,
    bundle: dict[str, Any] | None,
    enqueue: Callable[..., dict[str, Any]],
    course_id: str,
    knowledge_revision_id: str = "",
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """构造 `runners["practice"]`，交给 `execute_rebuild` 使用。

    `enqueue` 是既有定向重建作业入口的注入点，签名：
    `enqueue(course_id=..., revision_ids=[...], reason=...) -> job dict`。
    注入而不是直接 import router，是因为 router 持有 FastAPI 依赖、课程文档与
    执行器；runner 不该成为它们的耦合点，也才能在测试里独立验证。

    `knowledge_revision_id` 写进逐题回执，用来回答「这道题依据哪次知识修订
    重建」——任务书要求的可追溯性。
    """
    receipts: list[dict[str, Any]] = []

    def runner(entry: dict[str, Any]) -> dict[str, Any]:
        object_id = _text(entry.get("id"))
        section_id = _text(entry.get("section_id"))
        revision_ids = resolve_question_revisions(
            bundle,
            object_id=object_id,
            section_id=section_id,
        )
        if not revision_ids:
            # 如实失败。executor 会记 failed 并保留 last_available，
            # 旧题继续可读可作答。
            receipts.append(_item_receipt(
                entry,
                status="failed",
                revision_ids=[],
                knowledge_revision_id=knowledge_revision_id,
                error="在当前题库中找不到对应题目，未做任何写入",
            ))
            return {
                "status": "failed",
                "error": (
                    f"练习对象 {object_id or '(空)'} 在当前题库中没有可定向重建的题目"
                ),
            }

        try:
            job = enqueue(
                course_id=course_id,
                revision_ids=revision_ids,
                reason=_text(entry.get("reason")),
            ) or {}
        except Exception as error:  # noqa: BLE001 - 逐题失败不该中断整批
            receipts.append(_item_receipt(
                entry,
                status="failed",
                revision_ids=revision_ids,
                knowledge_revision_id=knowledge_revision_id,
                error=f"登记定向重建作业失败：{error}",
            ))
            return {"status": "failed", "error": str(error)}

        job_id = _text(job.get("job_id"))
        if not job_id:
            receipts.append(_item_receipt(
                entry,
                status="failed",
                revision_ids=revision_ids,
                knowledge_revision_id=knowledge_revision_id,
                error="定向重建作业没有返回 job_id",
            ))
            return {
                "status": "failed",
                "error": "定向重建作业没有返回 job_id，未做任何写入",
            }

        receipts.append(_item_receipt(
            entry,
            status="candidate_ready",
            revision_ids=revision_ids,
            knowledge_revision_id=knowledge_revision_id,
            job_id=job_id,
        ))
        # candidate_ready 而不是 succeeded：作业只是登记成功，题目还没重建完，
        # 更没有经过教师确认。谎报 succeeded 会让下游状态提前转正。
        return {"status": "candidate_ready", "revision": job_id}

    runner.receipts = receipts  # type: ignore[attr-defined]
    return runner


def _item_receipt(
    entry: dict[str, Any],
    *,
    status: str,
    revision_ids: list[str],
    knowledge_revision_id: str,
    job_id: str = "",
    error: str = "",
) -> dict[str, Any]:
    """逐题回执：哪道题、依据哪次知识修订、成功还是失败及原因。"""
    return {
        "schema_version": PRACTICE_REBUILD_RECEIPT_SCHEMA,
        "object_type": _text(entry.get("type")),
        "object_id": _text(entry.get("id")),
        "section_id": _text(entry.get("section_id")),
        "question_revision_ids": list(revision_ids),
        "knowledge_revision_id": _text(knowledge_revision_id),
        "impact_reason": _text(entry.get("reason")),
        "impact_group": _text(entry.get("impact_group")),
        "status": status,
        "job_id": _text(job_id),
        "error": _text(error),
        # 失败时旧题是否仍可读。executor 从下游状态的 last_available 得出。
        "readable_fallback": bool(entry.get("has_readable_fallback")),
    }


def practice_rebuild_receipts(
    runner: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """取出逐题回执，供接线层写进作业结果或返回给前端。"""
    return deepcopy(getattr(runner, "receipts", []))


def question_bank_job_enqueue(
    *,
    job_repository: Any = None,
    actor_id: str = "",
    knowledge_revision_id: str = "",
    job_executor: Any = None,
    payload_factory: Callable[..., Any] | None = None,
    course_data: dict[str, Any] | None = None,
) -> Callable[..., dict[str, Any]]:
    """把既有定向重建作业仓库包成 runner 认识的 `enqueue`。

    走 `scope="items"` 而不是 `scope="nodes"`：任务书要的是「受影响的题目按新
    知识**定向**重建」。按小节重建会把该节没受影响的题目一起重出，既浪费一次
    完整的 10 阶段出题，也会让教师已审阅过的好题平白进入重建流程。

    去重口径由作业仓库自己定（`_same_active_scope`：同 scope + 同题目集合 +
    同 mode/actor 且仍在 queued/running 才算同一个），所以教师连点两次不会叠出
    两条重建；上一轮跑完之后，新一次知识修订能重新登记。`request_id` 只用于
    追溯是哪次知识修订触发的，不承担去重。
    """
    repository = job_repository
    executor = job_executor
    make_payload = payload_factory
    if repository is None:
        from question_bank_jobs import question_bank_rebuild_job_repository
        from question_bank_rebuild_runtime import (
            current_question_bank_rebuild_runtime,
        )

        repository = question_bank_rebuild_job_repository
        if executor is None or make_payload is None:
            configured_executor, configured_payload_factory = (
                current_question_bank_rebuild_runtime()
            )
            executor = executor or configured_executor
            make_payload = make_payload or configured_payload_factory
        if executor is None or make_payload is None:
            raise RuntimeError("题库重建执行器尚未完成启动注册")

    def enqueue(*, course_id: str, revision_ids: list[str], reason: str = "") -> dict[str, Any]:
        scoped = sorted({_text(item) for item in revision_ids if _text(item)})
        request_id = stable_hash(
            {
                "course_id": course_id,
                "knowledge_revision_id": _text(knowledge_revision_id) or "unknown",
                "revision_ids": scoped,
            },
            prefix="knowledge-rebuild_",
        )
        job, created = repository.create_job(
            course_id,
            request_id=request_id,
            scope="items",
            node_ids=[],
            revision_ids=scoped,
            mode="incremental",
            actor_id=actor_id,
        )
        if created and executor is not None and make_payload is not None:
            payload = make_payload(
                request_id=request_id,
                scope="items",
                revision_ids=scoped,
                mode="incremental",
                resume_existing=True,
            )
            executor.submit(
                job_id=str(job["job_id"]),
                course_id=course_id,
                payload=payload,
                course=deepcopy(course_data or {}),
            )
        return job or {}

    return enqueue


def build_rebuild_runners(
    *,
    bundle: dict[str, Any] | None,
    course_id: str,
    knowledge_revision_id: str = "",
    actor_id: str = "",
    job_repository: Any = None,
    enqueue: Callable[..., dict[str, Any]] | None = None,
    job_executor: Any = None,
    payload_factory: Callable[..., Any] | None = None,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    """组装交给 `execute_rebuild` 的 runners 字典。

    只注册 `practice` 这一条——本任务线只负责练习题这一段。表达与正文的
    runner 归各自那条线提供；这里不给它们塞占位实现，否则 executor 会把
    「没人实现」误当成「实现了但失败」。缺 runner 时 executor 自己会标
    `blocked` 并说明原因，那才是诚实的缺口。
    """
    practice_runner = build_practice_rebuild_runner(
        bundle=bundle,
        enqueue=enqueue or question_bank_job_enqueue(
            job_repository=job_repository,
            actor_id=actor_id,
            knowledge_revision_id=knowledge_revision_id,
            job_executor=job_executor,
            payload_factory=payload_factory,
            course_data=course_data,
        ),
        course_id=course_id,
        knowledge_revision_id=knowledge_revision_id,
    )
    return {"practice": practice_runner}


__all__ = [
    "PRACTICE_OBJECT_TYPES",
    "PRACTICE_REBUILD_RECEIPT_SCHEMA",
    "build_practice_rebuild_runner",
    "build_rebuild_runners",
    "practice_rebuild_receipts",
    "question_bank_job_enqueue",
    "resolve_question_revisions",
]
