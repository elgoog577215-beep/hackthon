"""Normalization, validation and deterministic assembly for teaching-plan V3."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_knowledge_base import RELATION_TYPES
from course_versioning import stable_hash


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(
        text for value in values if (text := str(value or "").strip())
    ))


def _optional_int(value: Any, *, lower: int = 1, upper: int = 240) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and lower <= value <= upper:
        return value
    return None


def _section_execution(raw: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "planned_minutes": _optional_int(raw.get("planned_minutes")),
        "key_difficulties": _unique(list(raw.get("key_difficulties") or [])),
        "teacher_activities": _unique(list(raw.get("teacher_activities") or [])),
        "student_activities": _unique(list(raw.get("student_activities") or [])),
        "resource_refs": _unique(list(raw.get("resource_refs") or [])),
        "in_class_checks": _unique(list(raw.get("in_class_checks") or [])),
        "homework": _unique(list(raw.get("homework") or [])),
        "teaching_notes": _unique(list(raw.get("teaching_notes") or [])),
    }
    return {key: value for key, value in fields.items() if value not in (None, [])}


def _module_execution(raw: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "planned_minutes": _optional_int(raw.get("planned_minutes")),
        "teacher_activity": str(raw.get("teacher_activity") or "").strip(),
        "student_activity": str(raw.get("student_activity") or "").strip(),
    }
    return {key: value for key, value in fields.items() if value not in (None, "")}


def _issue(code: str, message: str, *, severity: str = "blocking") -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity}


# 每类关系的必填字段，与 `_compile_relations` 的丢弃规则一一对应。
RELATION_REQUIRED_FIELDS = {
    "derives": ("derivation_steps",),
    "contrasts_with": ("distinction",),
}


def _missing_relation_fields(relation: dict[str, Any], relation_type: str) -> list[str]:
    """列出该类型缺失的必填字段。空数组与空串都算缺失，编译层同样丢弃。"""
    missing = []
    for field in RELATION_REQUIRED_FIELDS.get(relation_type, ()):
        value = relation.get(field)
        if isinstance(value, str):
            if not value.strip():
                missing.append(field)
        elif not value:
            missing.append(field)
    return missing


def promote_course_teaching_plan_v3(
    payload: dict[str, Any],
    *,
    outline_revision_id: str,
) -> dict[str, Any]:
    """Wrap a valid compact/legacy plan in the one official V3 envelope.

    Compact planning already contains the same section knowledge and teaching
    intent as the batched path. The only missing V3 field is a stable revision
    for the embedded whole-course identity decision. Building that revision
    locally keeps small courses at one model call while ensuring every newly
    persisted official plan has the same public schema.
    """
    sections = [
        deepcopy(section)
        for section in payload.get("sections") or []
        if isinstance(section, dict)
    ]
    skeleton_revision_id = str(
        payload.get("skeleton_revision_id") or ""
    ).strip()
    if not skeleton_revision_id:
        identity_contract = {
            "schema_version": "course_teaching_plan_identity_v3",
            "source_outline_revision_id": outline_revision_id,
            "sections": [
                {
                    "node_id": str(section.get("node_id") or ""),
                    "owned_knowledge": [
                        {
                            "name": str(point.get("name") or ""),
                            "statement": str(point.get("statement") or ""),
                            "prerequisite_names": _unique(
                                list(point.get("prerequisite_names") or [])
                            ),
                        }
                        for group in section.get("knowledge_structure") or []
                        if isinstance(group, dict)
                        for point in group.get("knowledge_points") or []
                        if isinstance(point, dict)
                    ],
                    "reused_knowledge_names": _unique(
                        list(section.get("reused_knowledge_names") or [])
                    ),
                    "module_bindings": [
                        {
                            "module_id": str(module.get("module_id") or ""),
                            "knowledge_names": _unique(
                                list(module.get("knowledge_names") or [])
                            ),
                        }
                        for module in section.get("teaching_modules") or []
                        if isinstance(module, dict)
                    ],
                }
                for section in sections
            ],
        }
        skeleton_revision_id = stable_hash(
            identity_contract,
            prefix="teaching_skeleton_",
        )

    upgraded = {
        "schema_version": "course_teaching_plan_v3",
        "source_outline_revision_id": (
            str(payload.get("source_outline_revision_id") or "").strip()
            or outline_revision_id
        ),
        "skeleton_revision_id": skeleton_revision_id,
        "sections": sections,
    }
    upgraded["revision_id"] = stable_hash(upgraded, prefix="teaching_")
    return upgraded


# Deterministic shape repair for knowledge-detail entries.
#
# Models reliably produce the right *content* but drift on the *shape*: a bare
# string where an object is required, or a synonym for the canonical key. Those
# drifts are mechanical, so repairing them here removes a whole class of
# correction round-trips.
#
# This repairs shape only. A field whose content is genuinely absent stays
# absent so the validator still rejects the batch — inventing a mastery
# criterion or a repair strategy would pass the quality gate with content no
# teacher wrote.
_CAPABILITY_ALIASES = {
    "observable_behavior": "observable_behavior",
    "behavior": "observable_behavior",
    "observable": "observable_behavior",
    "capability": "observable_behavior",
    "description": "observable_behavior",
}
_MASTERY_ALIASES = {
    "observable_performance": "observable_performance",
    "performance": "observable_performance",
    "observable": "observable_performance",
    "criterion": "observable_performance",
    "standard": "observable_performance",
    "verification_method": "verification_method",
    "verification": "verification_method",
    "method": "verification_method",
    "evidence": "verification_method",
    "how_to_verify": "verification_method",
}
_MISCONCEPTION_ALIASES = {
    "observable_error_pattern": "observable_error_pattern",
    "error_pattern": "observable_error_pattern",
    "error": "observable_error_pattern",
    "mistake": "observable_error_pattern",
    "symptom": "observable_error_pattern",
    "discrimination": "discrimination",
    "discriminator": "discrimination",
    "diagnosis": "discrimination",
    "why": "discrimination",
    "root_cause": "discrimination",
    "repair_strategy": "repair_strategy",
    "repair": "repair_strategy",
    "remediation": "repair_strategy",
    "fix": "repair_strategy",
    "correction": "repair_strategy",
}


def _repair_detail_entry(
    raw: Any,
    *,
    aliases: dict[str, str],
    primary_field: str,
) -> dict[str, Any]:
    """Coerce one capability/criterion/misconception into its canonical shape."""
    if isinstance(raw, str):
        text = raw.strip()
        return {primary_field: text} if text else {}
    if not isinstance(raw, dict):
        return {}
    repaired: dict[str, Any] = deepcopy(raw)
    for key, value in raw.items():
        canonical = aliases.get(str(key).strip().lower())
        if canonical is None:
            continue
        # Never let an alias clobber a canonical field the model already filled.
        if str(repaired.get(canonical) or "").strip():
            continue
        if isinstance(value, str) and value.strip():
            repaired[canonical] = value.strip()
        elif isinstance(value, list):
            joined = "；".join(
                item.strip() for item in value
                if isinstance(item, str) and item.strip()
            )
            if joined:
                repaired[canonical] = joined
    return repaired


def _repair_detail_list(
    values: Any,
    *,
    aliases: dict[str, str],
    primary_field: str,
) -> list[dict[str, Any]]:
    if isinstance(values, (str, dict)):
        values = [values]
    if not isinstance(values, list):
        return []
    repaired = [
        _repair_detail_entry(item, aliases=aliases, primary_field=primary_field)
        for item in values
    ]
    return [item for item in repaired if item]


def normalize_teaching_plan_skeleton_v3(
    payload: dict[str, Any],
    *,
    outline_revision_id: str,
) -> dict[str, Any]:
    registry: list[dict[str, Any]] = []
    for raw in payload.get("knowledge_registry") or []:
        if not isinstance(raw, dict):
            continue
        registry.append({
            "knowledge_key": str(raw.get("knowledge_key") or "").strip(),
            "name": str(raw.get("name") or "").strip(),
            "statement": str(raw.get("statement") or "").strip(),
            "owner_node_id": str(raw.get("owner_node_id") or "").strip(),
            "reused_in_node_ids": _unique(list(raw.get("reused_in_node_ids") or [])),
            "prerequisite_keys": _unique(list(raw.get("prerequisite_keys") or [])),
            "module_ids": _unique(list(raw.get("module_ids") or [])),
        })
    sections: list[dict[str, Any]] = []
    for raw in payload.get("sections") or []:
        if not isinstance(raw, dict):
            continue
        sections.append({
            "node_id": str(raw.get("node_id") or "").strip(),
            "owned_knowledge_keys": _unique(list(raw.get("owned_knowledge_keys") or [])),
            "reused_knowledge_keys": _unique(list(raw.get("reused_knowledge_keys") or [])),
        })
    normalized = {
        "schema_version": "course_teaching_plan_skeleton_v3",
        "source_outline_revision_id": outline_revision_id,
        "knowledge_registry": registry,
        "sections": sections,
    }
    normalized["revision_id"] = stable_hash(normalized, prefix="teaching_skeleton_")
    return normalized


def validate_teaching_plan_skeleton_v3(
    skeleton: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_ids = [str(item.get("node_id") or "") for item in sections]
    actual_ids = [str(item.get("node_id") or "") for item in skeleton.get("sections") or []]
    allowed_modules = {
        str(section.get("node_id") or ""): {
            str(module.get("module_id") or "")
            for module in section.get("module_plan") or []
            if isinstance(module, dict)
        }
        for section in sections
    }
    issues: list[dict[str, str]] = []
    if actual_ids != expected_ids:
        issues.append(_issue(
            "teaching_skeleton:section_order_mismatch",
            "全课知识职责骨架必须按目录顺序完整覆盖所有小节",
        ))
    registry = [item for item in skeleton.get("knowledge_registry") or [] if isinstance(item, dict)]
    keys = [str(item.get("knowledge_key") or "") for item in registry]
    names = [str(item.get("name") or "") for item in registry]
    key_set = set(keys)
    if not registry or any(not key for key in keys):
        issues.append(_issue("teaching_skeleton:missing_key", "每个知识点必须有稳定 knowledge_key"))
    if len(keys) != len(key_set):
        issues.append(_issue("teaching_skeleton:duplicate_key", "knowledge_key 在全课必须唯一"))
    if any(not name for name in names) or len(names) != len(set(names)):
        issues.append(_issue("teaching_skeleton:invalid_name", "知识规范名称必须非空且全课唯一"))

    section_by_id = {
        str(item.get("node_id") or ""): item
        for item in skeleton.get("sections") or [] if isinstance(item, dict)
    }
    section_order = {node_id: index for index, node_id in enumerate(expected_ids)}
    registry_order = {key: index for index, key in enumerate(keys)}
    ownership: dict[str, str] = {}
    declared_reuse: dict[str, set[str]] = {}
    for node_id in expected_ids:
        identity = section_by_id.get(node_id) or {}
        owned = list(identity.get("owned_knowledge_keys") or [])
        reused = list(identity.get("reused_knowledge_keys") or [])
        if not owned:
            issues.append(_issue(
                "teaching_skeleton:empty_owner",
                f"小节 {node_id} 至少要首次负责一个原子知识点",
            ))
        if len(owned) > 8:
            issues.append(_issue(
                "teaching_skeleton:owner_budget_exceeded",
                f"小节 {node_id} 首次负责的知识点超过 8 个，无法进入有界详细批次",
            ))
        for key in owned:
            if key not in key_set:
                issues.append(_issue("teaching_skeleton:unknown_owned_key", f"小节 {node_id} 引用了未知知识键 {key}"))
            if key in ownership:
                issues.append(_issue("teaching_skeleton:duplicate_owner", f"知识键 {key} 只能由一个小节首次负责"))
            ownership[key] = node_id
        for key in reused:
            if key not in ownership:
                issues.append(_issue("teaching_skeleton:future_reuse", f"小节 {node_id} 只能复用前序小节已负责的知识键 {key}"))
            declared_reuse.setdefault(key, set()).add(node_id)

    registry_by_key = {str(item.get("knowledge_key") or ""): item for item in registry}
    for key, owner in ownership.items():
        item = registry_by_key.get(key) or {}
        if str(item.get("owner_node_id") or "") != owner:
            issues.append(_issue("teaching_skeleton:owner_mismatch", f"知识键 {key} 的 owner_node_id 与小节职责不一致"))
        if not str(item.get("statement") or "").strip():
            issues.append(_issue("teaching_skeleton:missing_statement", f"知识键 {key} 缺少规范陈述"))
        prerequisite_keys = list(item.get("prerequisite_keys") or [])
        if set(prerequisite_keys) - key_set:
            issues.append(_issue("teaching_skeleton:unknown_prerequisite", f"知识键 {key} 引用了未知前置知识"))
        for prerequisite_key in prerequisite_keys:
            prerequisite_owner = ownership.get(prerequisite_key, "")
            if prerequisite_key not in key_set:
                continue
            if (
                section_order.get(prerequisite_owner, len(expected_ids))
                > section_order.get(owner, -1)
                or (
                    prerequisite_owner == owner
                    and registry_order.get(prerequisite_key, len(keys))
                    >= registry_order.get(key, -1)
                )
            ):
                issues.append(_issue(
                    "teaching_skeleton:future_prerequisite",
                    f"知识键 {key} 只能引用本节更早位置或前序小节的前置知识 {prerequisite_key}",
                ))
        if set(item.get("module_ids") or []) - allowed_modules.get(owner, set()):
            issues.append(_issue("teaching_skeleton:unknown_module", f"知识键 {key} 绑定了本节不允许的课程块"))
        if not item.get("module_ids"):
            issues.append(_issue("teaching_skeleton:missing_module", f"知识键 {key} 至少要绑定一个本节允许的课程块"))
        if set(item.get("reused_in_node_ids") or []) != declared_reuse.get(key, set()):
            issues.append(_issue("teaching_skeleton:reuse_mismatch", f"知识键 {key} 的注册表复用位置与小节职责不一致"))
    if set(ownership) != key_set:
        issues.append(_issue("teaching_skeleton:unowned_key", "知识注册表中的每个键都必须有唯一首次负责小节"))
    return {
        "schema_version": "course_teaching_plan_skeleton_validation_v3",
        "passed": not issues,
        "issues": issues,
        "blocking_issues": issues,
        "actual": {"section_count": len(actual_ids), "knowledge_point_count": len(keys)},
    }


def normalize_teaching_plan_batch_v3(
    payload: dict[str, Any],
    *,
    batch_id: str,
    skeleton_revision_id: str,
) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for raw_section in payload.get("sections") or []:
        if not isinstance(raw_section, dict):
            continue
        details = []
        for raw in raw_section.get("knowledge_details") or []:
            if not isinstance(raw, dict):
                continue
            details.append({
                "knowledge_key": str(raw.get("knowledge_key") or "").strip(),
                "concept_group": str(raw.get("concept_group") or "核心机制").strip(),
                "group_description": str(raw.get("group_description") or "").strip(),
                "knowledge_type": str(raw.get("knowledge_type") or "concept").strip(),
                "conditions": _unique(list(raw.get("conditions") or [])),
                "boundaries": _unique(list(raw.get("boundaries") or [])),
                "counterexamples": _unique(list(raw.get("counterexamples") or [])),
                "capability_points": _repair_detail_list(
                    raw.get("capability_points"),
                    aliases=_CAPABILITY_ALIASES,
                    primary_field="observable_behavior",
                ),
                "misconceptions": _repair_detail_list(
                    raw.get("misconceptions"),
                    aliases=_MISCONCEPTION_ALIASES,
                    primary_field="observable_error_pattern",
                ),
                "mastery_criteria": _repair_detail_list(
                    raw.get("mastery_criteria"),
                    aliases=_MASTERY_ALIASES,
                    primary_field="observable_performance",
                ),
                "aliases": _unique(list(raw.get("aliases") or [])),
            })
        relations = []
        for raw in raw_section.get("knowledge_relations") or []:
            if isinstance(raw, dict):
                relations.append({
                    **deepcopy(raw),
                    "source_key": str(raw.get("source_key") or "").strip(),
                    "target_key": str(raw.get("target_key") or "").strip(),
                })
        modules = []
        for raw in raw_section.get("teaching_modules") or []:
            if isinstance(raw, dict):
                modules.append({
                    "module_id": str(raw.get("module_id") or "").strip(),
                    "teaching_purpose": str(raw.get("teaching_purpose") or "").strip(),
                    "knowledge_keys": _unique(list(raw.get("knowledge_keys") or [])),
                    "teaching_guidance": str(raw.get("teaching_guidance") or "").strip(),
                    **_module_execution(raw),
                })
        sections.append({
            "node_id": str(raw_section.get("node_id") or "").strip(),
            "knowledge_details": details,
            "knowledge_relations": relations,
            "teaching_modules": modules,
            **_section_execution(raw_section),
        })
    normalized = {
        "schema_version": "course_teaching_plan_batch_v3",
        "batch_id": batch_id,
        "skeleton_revision_id": skeleton_revision_id,
        "sections": sections,
    }
    normalized["revision_id"] = stable_hash(normalized, prefix="teaching_batch_")
    return normalized


def validate_teaching_plan_batch_v3(
    batch: dict[str, Any],
    *,
    batch_spec: dict[str, Any],
    skeleton: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_ids = list(batch_spec.get("section_ids") or [])
    actual_ids = [str(item.get("node_id") or "") for item in batch.get("sections") or []]
    issues: list[dict[str, str]] = []
    review_issues: list[dict[str, str]] = []
    if actual_ids != expected_ids:
        issues.append(_issue("teaching_batch:section_mismatch", f"批次 {batch.get('batch_id')} 必须精确覆盖指定小节"))
    identity_by_id = {
        str(item.get("node_id") or ""): item
        for item in skeleton.get("sections") or [] if isinstance(item, dict)
    }
    section_by_id = {str(item.get("node_id") or ""): item for item in sections}
    section_order = {
        str(item.get("node_id") or ""): index
        for index, item in enumerate(sections)
    }
    owner_by_key = {
        str(item.get("knowledge_key") or ""): str(item.get("owner_node_id") or "")
        for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    }
    registry_keys = {
        str(item.get("knowledge_key") or "")
        for item in skeleton.get("knowledge_registry") or [] if isinstance(item, dict)
    }
    actual_by_id = {str(item.get("node_id") or ""): item for item in batch.get("sections") or [] if isinstance(item, dict)}
    for node_id in expected_ids:
        identity = identity_by_id.get(node_id) or {}
        expected_keys = list(identity.get("owned_knowledge_keys") or [])
        actual = actual_by_id.get(node_id) or {}
        detail_keys = [str(item.get("knowledge_key") or "") for item in actual.get("knowledge_details") or []]
        if detail_keys != expected_keys:
            issues.append(_issue("teaching_batch:knowledge_key_mismatch", f"小节 {node_id} 必须逐个展开骨架冻结的知识键"))
        allowed_keys = set(expected_keys) | set(identity.get("reused_knowledge_keys") or [])
        available_relation_keys = {
            key
            for key, owner_node_id in owner_by_key.items()
            if section_order.get(owner_node_id, len(sections))
            <= section_order.get(node_id, -1)
        }
        allowed_modules = {
            str(item.get("module_id") or "")
            for item in (section_by_id.get(node_id) or {}).get("module_plan") or []
            if isinstance(item, dict)
        }
        for detail in actual.get("knowledge_details") or []:
            key = str(detail.get("knowledge_key") or "")
            if not detail.get("capability_points") or not detail.get("mastery_criteria"):
                issues.append(_issue("teaching_batch:unobservable_mastery", f"知识键 {key} 必须有可观察能力与掌握标准"))
            if not detail.get("misconceptions"):
                issues.append(_issue("teaching_batch:missing_misconception", f"知识键 {key} 必须包含至少一个可信易错点"))
            for capability in detail.get("capability_points") or []:
                if not isinstance(capability, dict) or not str(
                    capability.get("observable_behavior") or ""
                ).strip():
                    issues.append(_issue("teaching_batch:empty_capability", f"知识键 {key} 的能力必须给出可观察行为"))
            for criterion in detail.get("mastery_criteria") or []:
                if (
                    not isinstance(criterion, dict)
                    or not str(criterion.get("observable_performance") or "").strip()
                    or not str(criterion.get("verification_method") or "").strip()
                ):
                    issues.append(_issue("teaching_batch:empty_mastery", f"知识键 {key} 的掌握标准必须可观察、可验证"))
            for misconception in detail.get("misconceptions") or []:
                if (
                    not isinstance(misconception, dict)
                    or not str(misconception.get("observable_error_pattern") or "").strip()
                    or not str(misconception.get("discrimination") or "").strip()
                    or not str(misconception.get("repair_strategy") or "").strip()
                ):
                    issues.append(_issue("teaching_batch:invalid_misconception", f"知识键 {key} 的易错点必须包含错误表现、判别与修复策略"))
        # 只统计"能活过编译层"的关系类型。非法类型或缺必填字段的关系会被
        # `_compile_relations` 整条丢弃，把它们算进多样性会让软门槛被一条注定
        # 消失的关系骗过去，结果知识网照样退化成线性链。
        surviving_types: list[str] = []
        for relation in actual.get("knowledge_relations") or []:
            relation_type = str(relation.get("relation_type") or "").strip()
            # 类型门与必填字段门镜像 `_compile_relations`（course_knowledge_base.py
            # :1470-1481）的丢弃规则。编译层丢弃发生在校验通过之后，修正轮看不到，
            # 所以这里必须提前报成 blocking，让模型有机会改。
            if relation_type not in RELATION_TYPES:
                issues.append(_issue(
                    "teaching_batch:unknown_relation_type",
                    f"小节 {node_id} 的关系类型 {relation_type or '(空)'} 不在允许的六类内："
                    f"{'、'.join(sorted(RELATION_TYPES))}",
                ))
            else:
                missing = _missing_relation_fields(relation, relation_type)
                if missing:
                    issues.append(_issue(
                        "teaching_batch:relation_missing_required_field",
                        f"小节 {node_id} 的 {relation_type} 关系缺少必填字段 "
                        f"{'、'.join(missing)}，缺字段会导致整条关系被丢弃",
                    ))
                else:
                    surviving_types.append(relation_type)
            if relation.get("source_key") not in registry_keys or relation.get("target_key") not in registry_keys:
                issues.append(_issue("teaching_batch:unknown_relation_endpoint", f"小节 {node_id} 的知识关系引用了未知知识键"))
            elif (
                relation.get("source_key") not in available_relation_keys
                or relation.get("target_key") not in available_relation_keys
            ):
                issues.append(_issue("teaching_batch:future_relation_endpoint", f"小节 {node_id} 的知识关系引用了未来批次保留的知识键"))
            elif not ({relation.get("source_key"), relation.get("target_key")} & set(expected_keys)):
                issues.append(_issue("teaching_batch:unrelated_relation", f"小节 {node_id} 只能返回至少连接一个本节新知识的关系"))
        # 多样性是质量问题而不是结构错误：一节里全是前置关系仍然是可发布的课程，
        # 只是知识网退化成了一条链。所以进复核队列，不进 blocking。
        if not [name for name in surviving_types if name != "prerequisite"]:
            review_issues.append(_issue(
                "teaching_batch:relation_diversity_low",
                f"小节 {node_id} 没有任何非前置关系，知识网退化为线性链，建议复核"
                f"是否存在推导、易混、应用或迁移关系",
                severity="review",
            ))
        for module in actual.get("teaching_modules") or []:
            if module.get("module_id") not in allowed_modules:
                issues.append(_issue("teaching_batch:unknown_module", f"小节 {node_id} 返回了不允许的课程块"))
            if set(module.get("knowledge_keys") or []) - allowed_keys:
                issues.append(_issue("teaching_batch:unknown_module_knowledge", f"小节 {node_id} 的课程块越过了冻结知识边界"))
    return {
        "schema_version": "course_teaching_plan_batch_validation_v3",
        # 软门槛不参与 passed：复核提示不能阻断发布。
        "passed": not issues,
        "issues": issues + review_issues,
        "blocking_issues": issues,
        "review_issues": review_issues,
        "actual": {"section_count": len(actual_ids)},
    }


def _batch_section_has_content(section: dict[str, Any]) -> bool:
    """这一轮返回的小节到底有没有内容。

    三项任一非空就算有：知识点、关系、教学模块。**不能只看知识点**——
    一节完全可以不引入新知识、只把已学知识连起来（纯复用节），
    那种小节的 `knowledge_details` 本来就是空的，误判成失败轮会让它
    永远无法覆盖前一轮。
    """
    return any(
        section.get(field)
        for field in ("knowledge_details", "knowledge_relations", "teaching_modules")
    )


def assemble_course_teaching_plan_v3(
    *,
    skeleton: dict[str, Any],
    batches: list[dict[str, Any]],
    outline_revision_id: str,
) -> dict[str, Any]:
    """Assemble one official plan independent of batch completion order."""
    registry = {
        str(item.get("knowledge_key") or ""): item
        for item in skeleton.get("knowledge_registry") or [] if isinstance(item, dict)
    }
    details_by_id: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for item in batch.get("sections") or []:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "")
            existing = details_by_id.get(node_id)
            # 后写覆盖前写，**除非后写是空的**。同一小节会被写多次：纠正轮与
            # 语义重试都会整批重发。实测（NOTES 3.12）L2-2-3 的模型输出序列是
            # [3, 0, 1]——中间那轮返回 0 条。若最后一轮为 0，前面成功的那批会被
            # 整段抹掉，而且没有报错、没有留痕：教师看到一节凭空少了知识点和
            # 关系，链路却报告成功。这是丢数据，不是丢质量。
            #
            # 只堵"空覆盖非空"这一种无歧义的情况：一轮什么都没返回是失败，
            # 不是删除意图。两轮都有内容时仍然后写生效——纠正轮**故意**删掉
            # 不成立的关系是正常行为，做并集会把校验层刚拒绝的关系从装配层
            # 绕回知识网。
            if existing is not None and not _batch_section_has_content(item):
                continue
            details_by_id[node_id] = item

    planned_sections: list[dict[str, Any]] = []
    for identity in skeleton.get("sections") or []:
        node_id = str(identity.get("node_id") or "")
        expanded = details_by_id.get(node_id) or {}
        groups: list[dict[str, Any]] = []
        group_by_name: dict[str, dict[str, Any]] = {}
        for detail in expanded.get("knowledge_details") or []:
            key = str(detail.get("knowledge_key") or "")
            canonical = registry.get(key) or {}
            group_name = str(detail.get("concept_group") or "核心机制")
            group = group_by_name.get(group_name)
            if group is None:
                group = {
                    "concept_group": group_name,
                    "description": str(detail.get("group_description") or ""),
                    "knowledge_points": [],
                }
                groups.append(group)
                group_by_name[group_name] = group
            group["knowledge_points"].append({
                "name": str(canonical.get("name") or key),
                "statement": str(canonical.get("statement") or ""),
                "knowledge_type": str(detail.get("knowledge_type") or "concept"),
                "conditions": list(detail.get("conditions") or []),
                "boundaries": list(detail.get("boundaries") or []),
                "counterexamples": list(detail.get("counterexamples") or []),
                "entry_reason": (
                    "这是本课程的知识入口。"
                    if not canonical.get("prerequisite_keys") else ""
                ),
                "prerequisite_names": [
                    str((registry.get(item) or {}).get("name") or item)
                    for item in canonical.get("prerequisite_keys") or []
                ],
                "capability_points": deepcopy(detail.get("capability_points") or []),
                "misconceptions": deepcopy(detail.get("misconceptions") or []),
                "mastery_criteria": deepcopy(detail.get("mastery_criteria") or []),
                "aliases": list(detail.get("aliases") or []),
            })
        relations = []
        for relation in expanded.get("knowledge_relations") or []:
            source = registry.get(str(relation.get("source_key") or "")) or {}
            target = registry.get(str(relation.get("target_key") or "")) or {}
            relations.append({
                **deepcopy(relation),
                "source_name": str(source.get("name") or ""),
                "target_name": str(target.get("name") or ""),
            })
            relations[-1].pop("source_key", None)
            relations[-1].pop("target_key", None)
        modules = []
        for module in expanded.get("teaching_modules") or []:
            modules.append({
                "module_id": str(module.get("module_id") or ""),
                "teaching_purpose": str(module.get("teaching_purpose") or ""),
                "knowledge_names": [
                    str((registry.get(item) or {}).get("name") or item)
                    for item in module.get("knowledge_keys") or []
                ],
                "teaching_guidance": str(module.get("teaching_guidance") or ""),
                **_module_execution(module),
            })
        planned_sections.append({
            "node_id": node_id,
            "knowledge_structure": groups,
            "key_points": [
                str((registry.get(key) or {}).get("name") or key)
                for key in identity.get("owned_knowledge_keys") or []
            ],
            "reused_knowledge_names": [
                str((registry.get(key) or {}).get("name") or key)
                for key in identity.get("reused_knowledge_keys") or []
            ],
            "knowledge_relations": relations,
            "teaching_modules": modules,
            **_section_execution(expanded),
        })
    assembled = {
        "schema_version": "course_teaching_plan_v3",
        "source_outline_revision_id": outline_revision_id,
        "skeleton_revision_id": skeleton.get("revision_id"),
        "sections": planned_sections,
    }
    assembled["revision_id"] = stable_hash(
        {
            "schema_version": assembled["schema_version"],
            "source_outline_revision_id": outline_revision_id,
            "skeleton_revision_id": skeleton.get("revision_id"),
            "sections": planned_sections,
        },
        prefix="teaching_",
    )
    return assembled
