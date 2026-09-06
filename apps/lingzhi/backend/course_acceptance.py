"""Read-only preflight checks for course-generation learning contracts."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from course_document import COURSE_DOCUMENT_SCHEMA, course_view_from_document
from course_versioning import stable_hash
from learning_progress import project_learning_objective_bindings


REPORT_SCHEMA = "course_acceptance_preflight_v1"
SCAN_SCHEMA = "course_acceptance_scan_v1"
AcceptanceProfile = Literal["standard", "reading_only", "compatibility", "auto"]
ResolvedProfile = Literal["standard", "reading_only", "compatibility"]
_SNAPSHOT_FILE = re.compile(r"\.v\d+\.json$")

_CONTRACT_META = {
    "version": ("版本契约", "GEN"),
    "objective": ("目标契约", "ASSET"),
    "content": ("内容契约", "ASSET"),
    "practice": ("练习契约", "ASSET"),
    "remediation": ("补救契约", "ASSET"),
    "progression": ("推进契约", "ASSET"),
}


class VersionReader(Protocol):
    def current_version_id(self, course_id: str) -> str | None: ...

    def list_versions(self, course_id: str) -> list[dict[str, Any]]: ...


def inspect_course_acceptance(
    course_data: dict[str, Any],
    *,
    requested_profile: AcceptanceProfile = "standard",
    version_context: dict[str, Any] | None = None,
    source_file: str | None = None,
) -> dict[str, Any]:
    """Inspect one course without mutating it or compiling missing assets."""
    raw = deepcopy(course_data)
    if (
        raw.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
        and isinstance(raw.get("course_document"), dict)
    ):
        raw = course_view_from_document(raw, raw["course_document"])
    profile = resolve_acceptance_profile(raw, requested_profile)
    projected = project_learning_objective_bindings(raw)
    course_id = str(raw.get("course_id") or "")
    raw_nodes = list(raw.get("nodes") or [])
    learning_nodes = _learning_nodes(projected)
    raw_learning_nodes = _learning_nodes(raw)
    chapters = [node for node in raw_nodes if int(node.get("node_level") or 1) == 1]
    assets = raw.get("learning_assets") or {}
    plan = raw.get("learning_asset_plan") or {}
    context = dict(version_context or {})

    contracts = [
        _version_contract(raw, profile, context),
        _objective_contract(projected, assets, learning_nodes, profile),
        _content_contract(projected, raw_learning_nodes, learning_nodes),
        _practice_contract(assets, learning_nodes, profile, plan),
        _remediation_contract(assets, learning_nodes, profile),
        _progression_contract(projected, assets, chapters, learning_nodes, profile),
    ]
    blocking_issues = []
    warnings = []
    for contract in contracts:
        for check in contract["checks"]:
            if check["passed"]:
                continue
            issue = {
                "issue_id": stable_hash(
                    {
                        "course_id": course_id,
                        "contract": contract["contract_id"],
                        "check": check["check_id"],
                    },
                    prefix="capi_",
                ),
                "contract_id": contract["contract_id"],
                "check_id": check["check_id"],
                "owner": contract["owner"],
                "severity": "P1" if check["blocking"] else "P2",
                "message": check["message"],
            }
            (blocking_issues if check["blocking"] else warnings).append(issue)

    contract_statuses = [item["status"] for item in contracts]
    if "blocked" in contract_statuses:
        overall_status = "blocked"
    elif "degraded" in contract_statuses:
        overall_status = "degraded"
    else:
        overall_status = "ready"

    return {
        "schema_version": REPORT_SCHEMA,
        "course_id": course_id,
        "course_name": str(raw.get("course_name") or "未命名课程"),
        "source_file": source_file,
        "source_revision_id": stable_hash(raw, prefix="course_source_"),
        "requested_profile": requested_profile,
        "acceptance_profile": profile,
        "status": overall_status,
        "ready_for_full_chain": overall_status == "ready" and profile == "standard",
        "ready_for_declared_scope": not blocking_issues,
        "contracts": contracts,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "statistics": {
            "chapter_count": len(chapters),
            "learning_node_count": len(learning_nodes),
            "persisted_content_block_count": sum(
                len(node.get("content_blocks") or []) for node in raw_learning_nodes
            ),
            "projected_content_block_count": sum(
                len(node.get("content_blocks") or []) for node in learning_nodes
            ),
            "asset_counts": {
                key: len(value)
                for key, value in assets.items()
                if isinstance(value, list)
            },
        },
    }


def scan_course_directory(
    courses_dir: str | Path,
    *,
    requested_profile: AcceptanceProfile = "standard",
    course_id: str | None = None,
    version_reader: VersionReader | None = None,
) -> dict[str, Any]:
    """Parse and inspect main course JSON files without recovery or writes."""
    root = Path(courses_dir)
    reports: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(root.glob("*.json")):
            if _SNAPSHOT_FILE.search(path.name):
                continue
            if course_id and path.stem != course_id:
                continue
            try:
                course = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                reports.append(_invalid_file_report(path, requested_profile, exc))
                continue
            resolved_course_id = str(course.get("course_id") or path.stem)
            if not course.get("course_id"):
                course["course_id"] = resolved_course_id
            reports.append(inspect_course_acceptance(
                course,
                requested_profile=requested_profile,
                version_context=read_version_context(version_reader, resolved_course_id),
                source_file=str(path),
            ))

    counts = {"ready": 0, "degraded": 0, "blocked": 0}
    for report in reports:
        counts[report["status"]] += 1
    return {
        "schema_version": SCAN_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "courses_dir": str(root),
        "requested_profile": requested_profile,
        "course_filter": course_id,
        "summary": {
            "total": len(reports),
            **counts,
            "ready_for_full_chain": sum(bool(item.get("ready_for_full_chain")) for item in reports),
        },
        "reports": reports,
    }


def read_version_context(version_reader: VersionReader | None, course_id: str) -> dict[str, Any]:
    """Read product-version metadata without creating an initial version."""
    if version_reader is None or not course_id:
        return {}
    current = version_reader.current_version_id(course_id)
    versions = version_reader.list_versions(course_id)
    return {
        "repository_current_version_id": current,
        "version_ids": [str(item.get("version_id") or "") for item in versions],
        "version_count": len(versions),
    }


def resolve_acceptance_profile(
    course_data: dict[str, Any],
    requested_profile: AcceptanceProfile,
) -> ResolvedProfile:
    """Resolve auto conservatively; missing assets never imply compatibility."""
    if requested_profile not in {"standard", "reading_only", "compatibility", "auto"}:
        raise ValueError(f"Unsupported acceptance profile: {requested_profile}")
    if requested_profile != "auto":
        return requested_profile
    plan = course_data.get("learning_asset_plan") or {}
    return "reading_only" if plan.get("reading_only_degraded") is True else "standard"


def _version_contract(
    course: dict[str, Any],
    profile: ResolvedProfile,
    context: dict[str, Any],
) -> dict[str, Any]:
    strict = profile != "compatibility"
    course_version = str(course.get("current_course_version_id") or "")
    canonical = course.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
    if canonical:
        document_revision = str(course.get("course_document_revision") or "")
        repository_version = str(context.get("repository_current_version_id") or "")
        effective_version = course_version or repository_version
        version_ids = set(context.get("version_ids") or [])
        document_linked = bool(document_revision) and effective_version == document_revision
        retained_history_linked = bool(effective_version) and effective_version in version_ids
        version_linked = document_linked or retained_history_linked
        version_message = "当前课程必须绑定 CourseDocument 修订或保留的技术历史"
    else:
        repository_version = str(context.get("repository_current_version_id") or "")
        effective_version = course_version or repository_version
        version_ids = set(context.get("version_ids") or [])
        version_linked = bool(effective_version) and bool(context) and effective_version in version_ids
        version_message = "当前版本必须存在于版本仓库"
    quality = course.get("asset_quality_report") or {}
    checks = [
        _check("VER-COURSE-ID", bool(course.get("course_id")), strict, "课程必须有稳定 course_id"),
        _check("VER-CURRENT", bool(effective_version), strict, "课程必须绑定当前产品版本"),
        _check("VER-ENTRY", version_linked, strict, version_message),
        _check(
            "VER-ASSET-BUNDLE",
            bool(course.get("learning_asset_bundle_revision_id")),
            strict,
            "课程必须绑定学习资产包修订",
        ),
        _check(
            "VER-ASSET-QUALITY",
            quality.get("passed") is True,
            strict,
            "学习资产质量报告必须通过",
        ),
        _check(
            "VER-GENERATION-QUALITY",
            course.get("generation_status") == "passed",
            strict,
            "课程生成最终质量状态必须为 passed",
        ),
    ]
    return _contract("version", checks)


def _objective_contract(
    course: dict[str, Any],
    assets: dict[str, Any],
    nodes: list[dict[str, Any]],
    profile: ResolvedProfile,
) -> dict[str, Any]:
    strict_assets = profile != "compatibility"
    objectives = course.get("learning_objectives") or []
    complete_objectives = [
        item for item in objectives
        if item.get("objective_id") and item.get("objective_revision_id") and item.get("statement")
    ]
    criteria = assets.get("mastery_criteria") or []
    covered_nodes = {str(item.get("node_id") or "") for item in criteria if item.get("revision_id")}
    node_ids = {str(node.get("node_id") or "") for node in nodes}
    checks = [
        _check("OBJ-NODES", bool(nodes), True, "课程必须至少有一个可学习目标节点"),
        _check(
            "OBJ-IDENTITY",
            len(complete_objectives) == len(nodes) and bool(nodes),
            True,
            "每个目标节点必须能形成稳定目标 ID、修订和陈述",
        ),
        _check(
            "OBJ-MASTERY-CRITERIA",
            bool(node_ids) and node_ids <= covered_nodes,
            strict_assets,
            "每个目标必须绑定当前掌握标准修订",
        ),
    ]
    return _contract("objective", checks)


def _content_contract(
    course: dict[str, Any],
    raw_nodes: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    projected_blocks = [block for node in nodes for block in node.get("content_blocks") or []]
    persisted_nodes = {str(node.get("node_id") or "") for node in raw_nodes if node.get("content_blocks")}
    node_ids = {str(node.get("node_id") or "") for node in nodes}
    metadata_complete = all(
        block.get("block_id")
        and block.get("content_fingerprint")
        and block.get("block_revision_id")
        for block in projected_blocks
    )
    checks = [
        _check(
            "CONTENT-COVERAGE",
            bool(nodes) and all(node.get("content_blocks") for node in nodes),
            True,
            "每个目标节点必须能形成语义内容块",
        ),
        _check(
            "CONTENT-REVISION",
            bool(projected_blocks) and metadata_complete,
            True,
            "每个内容块必须有稳定 ID、指纹和修订",
        ),
        _check(
            "CONTENT-PERSISTED",
            bool(node_ids) and node_ids <= persisted_nodes,
            False,
            "内容块由读取层兼容投影，生成器尚未持久化全部内容块",
        ),
    ]
    return _contract("content", checks)


def _practice_contract(
    assets: dict[str, Any],
    nodes: list[dict[str, Any]],
    profile: ResolvedProfile,
    plan: dict[str, Any],
) -> dict[str, Any]:
    if profile != "standard":
        explicit = plan.get("reading_only_degraded") is True if profile == "reading_only" else True
        return _contract(
            "practice",
            [_check(
                "PRACTICE-DECLARED-DEGRADE",
                explicit,
                profile == "reading_only",
                "阅读型课程必须在资产计划中显式声明不生成正式题目",
            )],
            force_degraded=True,
        )

    questions = assets.get("questions") or []
    node_ids = {str(node.get("node_id") or "") for node in nodes}
    covered = {str(item.get("node_id") or "") for item in questions}
    required_levels = {"concept_check", "objective_practice", "mastery_check"}
    levels_complete = all(
        required_levels <= {
            str(item.get("practice_level") or "")
            for item in questions
            if str(item.get("node_id") or "") == node_id
        }
        for node_id in node_ids
    )
    contracts_complete = all(
        item.get("revision_id")
        and item.get("practice_contract_revision_id")
        and item.get("input_contract")
        and item.get("hint_contract")
        and (item.get("answer_spec") or {}).get("criteria")
        for item in questions
    )
    checks = [
        _check("PRACTICE-EXISTS", bool(questions), True, "标准课程必须包含正式练习"),
        _check(
            "PRACTICE-COVERAGE",
            bool(node_ids) and node_ids <= covered,
            True,
            "正式练习必须覆盖全部目标节点",
        ),
        _check(
            "PRACTICE-LEVELS",
            bool(node_ids) and levels_complete,
            True,
            "每个目标必须有理解检查、目标练习和掌握检查",
        ),
        _check(
            "PRACTICE-CONTRACTS",
            bool(questions) and contracts_complete,
            True,
            "正式题目必须有任务修订、输入、提示和评分契约",
        ),
    ]
    return _contract("practice", checks)


def _remediation_contract(
    assets: dict[str, Any],
    nodes: list[dict[str, Any]],
    profile: ResolvedProfile,
) -> dict[str, Any]:
    if profile != "standard":
        return _contract("remediation", [], force_degraded=True)

    node_ids = {str(node.get("node_id") or "") for node in nodes}
    diagnostics = assets.get("diagnostic_templates") or []
    units = assets.get("remediation_units") or []
    validations = assets.get("validation_questions") or []
    diagnostic_nodes = {str(item.get("node_id") or "") for item in diagnostics if item.get("revision_id")}
    unit_nodes = {str(item.get("node_id") or "") for item in units if item.get("revision_id") and item.get("guided_task")}
    validation_counts = {
        node_id: sum(
            1
            for item in validations
            if str(item.get("node_id") or "") == node_id
            and item.get("revision_id")
            and item.get("quality_status") == "passed"
        )
        for node_id in node_ids
    }
    checks = [
        _check(
            "REMEDIATION-MISCONCEPTION",
            bool(assets.get("misconceptions")),
            True,
            "标准验收样本必须至少包含一个正式通用误区",
        ),
        _check(
            "REMEDIATION-DIAGNOSTIC",
            bool(node_ids) and node_ids <= diagnostic_nodes,
            True,
            "每个目标必须有稳定辨别任务模板",
        ),
        _check(
            "REMEDIATION-UNIT",
            bool(node_ids) and node_ids <= unit_nodes,
            True,
            "每个目标必须有最小补救单元和引导任务",
        ),
        _check(
            "REMEDIATION-VALIDATION",
            bool(node_ids) and all(validation_counts[node_id] >= 2 for node_id in node_ids),
            True,
            "每个目标必须至少有两道质量通过的独立复验题",
        ),
    ]
    return _contract("remediation", checks)


def _progression_contract(
    course: dict[str, Any],
    assets: dict[str, Any],
    chapters: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    profile: ResolvedProfile,
) -> dict[str, Any]:
    if profile == "compatibility":
        return _contract("progression", [], force_degraded=True)

    all_node_ids = {str(item.get("node_id") or "") for item in course.get("nodes") or []}
    chapter_ids = {str(item.get("node_id") or "") for item in chapters}
    objective_ids = {str(item.get("objective_id") or "") for item in course.get("learning_objectives") or []}
    child_counts = {
        chapter_id: sum(1 for node in nodes if str(node.get("parent_node_id") or "") == chapter_id)
        for chapter_id in chapter_ids
    }
    invalid_parents = [
        str(node.get("node_id") or "")
        for node in nodes
        if str(node.get("parent_node_id") or "") not in chapter_ids
    ]
    prerequisite_refs = [
        str(dependency)
        for node in nodes
        for dependency in node.get("prerequisite_node_ids") or []
    ]
    invalid_prerequisites = [item for item in prerequisite_refs if item not in all_node_ids]
    contracts = assets.get("chapter_progression_contracts") or []
    contract_chapters = {
        str(item.get("chapter_id") or "")
        for item in contracts
        if item.get("prerequisite_policy") and item.get("completion_policy")
    }
    referenced_objectives = {
        str(objective_id)
        for item in contracts
        for objective_id in item.get("required_objective_ids") or []
    }
    required_chapter_count = 2 if profile == "standard" else 1
    required_children = 2 if profile == "standard" else 1
    checks = [
        _check(
            "PROGRESSION-CHAPTERS",
            len(chapters) >= required_chapter_count,
            True,
            f"{profile} 验收至少需要 {required_chapter_count} 个章节",
        ),
        _check(
            "PROGRESSION-OBJECTIVES",
            bool(chapter_ids) and all(child_counts[item] >= required_children for item in chapter_ids),
            True,
            f"每章至少需要 {required_children} 个目标节点",
        ),
        _check(
            "PROGRESSION-PARENTS",
            not invalid_parents and bool(nodes),
            True,
            "目标节点必须归属于有效章节",
        ),
        _check(
            "PROGRESSION-PREREQUISITES",
            not invalid_prerequisites and (bool(prerequisite_refs) if profile == "standard" else True),
            True,
            "标准验收必须有至少一个有效显式前置关系，且不得引用失效节点",
        ),
        _check(
            "PROGRESSION-CONTRACTS",
            bool(chapter_ids) and chapter_ids <= contract_chapters,
            True,
            "每个章节必须有前置策略和完成策略",
        ),
        _check(
            "PROGRESSION-REQUIRED-OBJECTIVES",
            bool(contracts) and referenced_objectives <= objective_ids,
            True,
            "推进契约引用的必需目标必须存在于当前目标修订",
        ),
    ]
    return _contract("progression", checks)


def _learning_nodes(course: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = list(course.get("nodes") or [])
    level_two = [node for node in nodes if int(node.get("node_level") or 1) == 2]
    if level_two:
        return level_two
    return [
        node for node in nodes
        if str(node.get("node_content") or "").strip()
        and str(node.get("node_id") or "") not in {"", "root"}
    ]


def _check(check_id: str, passed: bool, blocking: bool, message: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "blocking": bool(blocking),
        "message": message,
    }


def _contract(
    contract_id: str,
    checks: list[dict[str, Any]],
    *,
    force_degraded: bool = False,
) -> dict[str, Any]:
    label, owner = _CONTRACT_META[contract_id]
    if any(not item["passed"] and item["blocking"] for item in checks):
        status = "blocked"
    elif force_degraded or any(not item["passed"] for item in checks):
        status = "degraded"
    else:
        status = "passed"
    return {
        "contract_id": contract_id,
        "label": label,
        "owner": owner,
        "status": status,
        "checks": checks,
    }


def _invalid_file_report(
    path: Path,
    requested_profile: AcceptanceProfile,
    error: Exception,
) -> dict[str, Any]:
    issue = {
        "issue_id": stable_hash({"file": str(path), "error": type(error).__name__}, prefix="capi_"),
        "contract_id": "storage_integrity",
        "check_id": "STORAGE-JSON",
        "owner": "GEN",
        "severity": "P0",
        "message": f"课程主文件不是有效 JSON：{type(error).__name__}",
    }
    return {
        "schema_version": REPORT_SCHEMA,
        "course_id": path.stem,
        "course_name": "无法读取",
        "source_file": str(path),
        "source_revision_id": None,
        "requested_profile": requested_profile,
        "acceptance_profile": "standard" if requested_profile == "auto" else requested_profile,
        "status": "blocked",
        "ready_for_full_chain": False,
        "ready_for_declared_scope": False,
        "storage_integrity": {
            "passed": False,
            "error_type": type(error).__name__,
        },
        "contracts": [],
        "blocking_issues": [issue],
        "warnings": [],
        "statistics": {},
    }


__all__ = [
    "AcceptanceProfile",
    "REPORT_SCHEMA",
    "SCAN_SCHEMA",
    "inspect_course_acceptance",
    "read_version_context",
    "resolve_acceptance_profile",
    "scan_course_directory",
]
