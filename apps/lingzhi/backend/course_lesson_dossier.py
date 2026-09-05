"""教案呈现对象：把结构化教案编译成固定栏目的课堂交付单。

投影层（`course_teaching_plan_projection`）回答“这一节教什么”，本模块回答
“这一节怎样被印出来交给老师上课”。两者的差别不是措辞，是结构：

- 投影层的字段是**按有无出现**的。某节没有 `homework` 就没有这个键，前端只能
  `v-if` 掉，于是每节长得都不一样——这正是“篇幅和颗粒度波动”的来源。
- 本模块输出的栏目是**恒定的**：`RUBRIC_KEYS` 里的每一栏在每一节都存在，缺内容
  时 `status="empty"`，由前端统一渲染“待补充”。栏目结构因此与内容多少无关。

本模块只做确定性重排与派生，不发明内容：

- 时序（`timeline`）的分钟数来自“已声明的总时长”在环节间的分配，派生出来的条目
  标 `minutes_source="derived"`，教师一眼能看出哪些是模型给的、哪些是摊出来的。
- 对照矩阵（`alignment`）只连接已经存在的知识点、环节、能力、掌握标准与检查，
  连不上就记进 `gaps`，绝不替模型补一条评价标准。

`template` 一栏是给将来“学科模板提升为顶层合同”留的接口：现在它只是把小节已经
挂上的 `lesson_archetype` 与 `module_plan` 摊平成可观测的合同视图，并算出实际环节
与模板环节的出入（`module_conformance`）。顶层合同落地后，只需要给它补上
`template_version` 并把 `contract_state` 升级为强约束，呈现层不必再改。
"""

from __future__ import annotations

from math import ceil, floor
from typing import Any

LESSON_DOSSIER_SCHEMA_VERSION = "course_lesson_dossier_v1"
LESSON_TEMPLATE_CONTRACT_SCHEMA_VERSION = "lesson_template_contract_v1"
LESSON_DOSSIER_CONSISTENCY_SCHEMA_VERSION = "course_lesson_dossier_consistency_v1"

# 固定栏目及其渲染类型。顺序即打印顺序，前端不得重排、不得按内容多少增删。
RUBRIC_SPECS: tuple[tuple[str, str], ...] = (
    ("lesson_identity", "facts"),
    ("objectives", "list"),
    ("focus", "split_list"),
    ("knowledge", "table"),
    ("timeline", "table"),
    ("alignment", "table"),
    ("misconceptions", "table"),
    ("assessment", "list"),
    ("homework", "list"),
    ("resources", "list"),
    ("notes", "list"),
)
RUBRIC_KEYS: tuple[str, ...] = tuple(key for key, _ in RUBRIC_SPECS)

# 环节时长权重。按课程块角色而不是模块 id 取，新增模块无需改这里。
_ROLE_WEIGHTS: dict[str, int] = {
    "objective": 1,
    "orientation": 1,
    "prerequisite": 1,
    "misconception": 1,
    "counterexample": 1,
    "concept": 3,
    "activity": 3,
    "reasoning": 2,
    "example": 2,
    "application": 2,
    "transfer": 2,
    "feedback": 2,
}
_DEFAULT_ROLE_WEIGHT = 2

# 颗粒度对照关注的指标。只放“教师翻页时能直接感受到篇幅差异”的量。
_BANDED_METRICS: tuple[str, ...] = (
    "knowledge_point_count",
    "module_count",
    "planned_minutes",
    "check_count",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _minutes(value: Any, *, upper: int = 600) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= upper else None


def _normalized(value: Any) -> str:
    return "".join(_text(value).lower().split())


def _first_text(record: Any, keys: tuple[str, ...]) -> str:
    """取记录里第一个非空字段。列表按顿号合并，兼容模型偶发的数组化写法。"""
    if isinstance(record, str):
        return _text(record)
    if not isinstance(record, dict):
        return ""
    for key in keys:
        value = record.get(key)
        if isinstance(value, list):
            joined = "；".join(_strings(value))
            if joined:
                return joined
        elif (text := _text(value)):
            return text
    return ""


_CAPABILITY_KEYS = ("observable_behavior", "capability", "behavior", "description")
_PERFORMANCE_KEYS = ("observable_performance", "criterion", "standard", "performance")
_VERIFICATION_KEYS = ("verification_method", "verification", "evidence", "method")
_ERROR_KEYS = ("observable_error_pattern", "error_pattern", "error", "mistake", "symptom")
_DISCRIMINATION_KEYS = ("discrimination", "diagnosis", "root_cause", "why")
_REPAIR_KEYS = ("repair_strategy", "repair", "remediation", "correction", "fix")


def _rubric(key: str, kind: str, *, item_count: int, **payload: Any) -> dict[str, Any]:
    return {
        "key": key,
        "kind": kind,
        "status": "filled" if item_count > 0 else "empty",
        "item_count": item_count,
        **payload,
    }


def _allocate_minutes(weights: list[int], total: int) -> list[int]:
    """把 total 分钟按权重摊到各环节，每个环节至少 1 分钟，合计精确等于 total。

    先给每个环节留 1 分钟，剩下的按最大余数法分配——这样不会出现“0 分钟环节”，
    也不会因为逐个四舍五入而让合计对不上教师填的课时长度。
    """
    count = len(weights)
    if count <= 0 or total < count:
        return []
    pool = total - count
    weight_sum = sum(weights)
    if weight_sum <= 0:
        weights = [1] * count
        weight_sum = count
    raw = [pool * weight / weight_sum for weight in weights]
    allocation = [int(value) for value in raw]
    remainder = pool - sum(allocation)
    order = sorted(
        range(count),
        key=lambda index: (-(raw[index] - allocation[index]), index),
    )
    for index in order[:remainder]:
        allocation[index] += 1
    return [value + 1 for value in allocation]


def _knowledge_matcher(names: list[str]) -> list[tuple[str, str]]:
    """(规范名, 归一化名) 列表，供正文文本里的知识点提及匹配。

    单字名不参与匹配：一个“数”“点”几乎命中所有句子，匹配出来的对应关系是假的。
    """
    matches = []
    for name in names:
        normalized = _normalized(name)
        if len(normalized) >= 2:
            matches.append((name, normalized))
    return matches


def _mentioned_names(text: str, matchers: list[tuple[str, str]]) -> list[str]:
    normalized_text = _normalized(text)
    if not normalized_text:
        return []
    return [name for name, key in matchers if key in normalized_text]


def _template_contract(
    *,
    archetype: dict[str, Any],
    module_plan: list[dict[str, Any]],
    actual_module_ids: list[str],
) -> dict[str, Any]:
    """把小节已挂的课型与环节模板摊成可观测的合同视图。

    现在它不约束任何东西，只报告实际教案与模板的出入。顶层合同落地后由这里补
    `template_version` 并升级 `contract_state`，前端模板不需要跟着改。
    """
    planned_ids = [
        module_id
        for module in module_plan
        if (module_id := _text(module.get("module_id")))
    ]
    required_ids = [
        module_id
        for module in module_plan
        if (module_id := _text(module.get("module_id"))) and module.get("required")
    ]
    actual = set(actual_module_ids)
    archetype_id = _text(archetype.get("archetype_id"))
    return {
        "schema_version": LESSON_TEMPLATE_CONTRACT_SCHEMA_VERSION,
        # 当前只是把事后挂上的课型摊平，还不是生成期的强约束。顶层合同落地后升级。
        "contract_state": "projected_from_archetype" if archetype_id else "unbound",
        "template_id": archetype_id,
        "template_label": _text(archetype.get("label")),
        # 顶层合同落地后由课型注册表版本填充；留空表示“该课程未被版本化模板约束”。
        "template_version": _text(archetype.get("registry_version")),
        "primary_mode": _text(archetype.get("mode")),
        "course_stage": _text(archetype.get("course_stage")),
        "purpose": _text(archetype.get("purpose")),
        "evidence_contract": _text(archetype.get("evidence_contract")),
        "guardrails": _strings(archetype.get("guardrails")),
        "archetype_module_ids": _strings(archetype.get("module_ids")),
        "planned_module_ids": planned_ids,
        "actual_module_ids": list(actual_module_ids),
        "module_conformance": {
            "matched": len([item for item in planned_ids if item in actual]),
            "missing_required": [item for item in required_ids if item not in actual],
            "unplanned": [
                item for item in actual_module_ids if item not in set(planned_ids)
            ],
        },
    }


def _timeline_rubric(
    *,
    modules: list[dict[str, Any]],
    module_plan_by_id: dict[str, dict[str, Any]],
    section_minutes: int | None,
    course_lesson_minutes: int | None,
    course_minutes_basis: str,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for index, module in enumerate(modules):
        module_id = _text(module.get("module_id"))
        planned = module_plan_by_id.get(module_id) or {}
        entries.append({
            "sequence": index + 1,
            "module_id": module_id,
            "label": (
                _text(module.get("label"))
                or _text(planned.get("label"))
                or _text(module.get("teaching_purpose"))
                or module_id
            ),
            "block_role": _text(module.get("block_role")) or _text(planned.get("block_role")),
            "required": bool(planned.get("required")),
            "teaching_purpose": _text(module.get("teaching_purpose")),
            "teaching_guidance": _text(module.get("teaching_guidance")),
            "teacher_activity": _text(module.get("teacher_activity")),
            "student_activity": _text(module.get("student_activity")),
            "knowledge_names": _strings(module.get("knowledge_names")),
            "minutes": _minutes(module.get("planned_minutes")),
            "minutes_source": (
                "planned" if _minutes(module.get("planned_minutes")) else "unset"
            ),
            "start_minute": None,
            "end_minute": None,
        })

    total_minutes = section_minutes or course_lesson_minutes
    minutes_basis = (
        "section_planned" if section_minutes
        else course_minutes_basis if course_lesson_minutes
        else "unset"
    )
    explicit = sum(entry["minutes"] or 0 for entry in entries)
    pending = [entry for entry in entries if entry["minutes"] is None]
    if pending and total_minutes:
        remaining = total_minutes - explicit
        allocation = _allocate_minutes(
            [
                _ROLE_WEIGHTS.get(entry["block_role"], _DEFAULT_ROLE_WEIGHT)
                for entry in pending
            ],
            remaining,
        )
        if allocation:
            for entry, minutes in zip(pending, allocation):
                entry["minutes"] = minutes
                entry["minutes_source"] = "derived"
        else:
            # 剩余时间不够每个环节分 1 分钟：宁可留空，也不写出假的 0 分钟环节。
            minutes_basis = "insufficient"

    cursor = 0
    complete = bool(entries) and all(entry["minutes"] for entry in entries)
    if complete:
        for entry in entries:
            entry["start_minute"] = cursor
            cursor += int(entry["minutes"])
            entry["end_minute"] = cursor

    return _rubric(
        "timeline",
        "table",
        item_count=len(entries),
        entries=entries,
        columns=("stage", "minutes", "teacher", "student", "knowledge"),
        total_minutes=total_minutes,
        allocated_minutes=cursor if complete else explicit,
        minutes_basis=minutes_basis,
        continuous=complete,
        derived_count=len([
            entry for entry in entries if entry["minutes_source"] == "derived"
        ]),
    )


def _knowledge_rows(
    section: dict[str, Any],
    *,
    owned_names: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in _dicts(section.get("knowledge_structure")):
        group_name = _text(group.get("concept_group"))
        for point in _dicts(group.get("knowledge_points")):
            name = _text(point.get("name"))
            if not name:
                continue
            capabilities = [
                text
                for item in (point.get("capability_points") or [])
                if (text := _first_text(item, _CAPABILITY_KEYS))
            ]
            if not capabilities and (fallback := _text(point.get("capability"))):
                capabilities = [fallback]
            mastery = []
            for item in point.get("mastery_criteria") or []:
                performance = _first_text(item, _PERFORMANCE_KEYS)
                verification = _first_text(item, _VERIFICATION_KEYS)
                if performance or verification:
                    mastery.append({
                        "performance": performance,
                        "verification": verification,
                    })
            misconceptions = []
            for item in point.get("misconceptions") or []:
                error = _first_text(item, _ERROR_KEYS)
                if not error:
                    continue
                misconceptions.append({
                    "error_pattern": error,
                    "discrimination": _first_text(item, _DISCRIMINATION_KEYS),
                    "repair_strategy": _first_text(item, _REPAIR_KEYS),
                })
            rows.append({
                "knowledge_id": _text(point.get("knowledge_id")),
                "knowledge_status": _text(point.get("knowledge_status")),
                "name": name,
                "aliases": _strings(point.get("aliases")),
                "concept_group": group_name,
                "knowledge_type": _text(point.get("knowledge_type")),
                "statement": _text(point.get("statement")) or _text(point.get("description")),
                "prerequisite_names": _strings(point.get("prerequisite_names")),
                "boundaries": [
                    *_strings(point.get("conditions")),
                    *_strings(point.get("boundaries")),
                ],
                "counterexamples": _strings(point.get("counterexamples")),
                "ownership": "owned" if _normalized(name) in owned_names else "reused",
                "capabilities": capabilities,
                "mastery": mastery,
                "misconceptions": misconceptions,
            })
    return rows


def build_lesson_dossier(
    section: dict[str, Any],
    *,
    sequence: int,
    node_title: str = "",
    chapter_title: str = "",
    learning_objective: str = "",
    lesson_archetype: dict[str, Any] | None = None,
    module_plan: list[dict[str, Any]] | None = None,
    course_lesson_minutes: int | None = None,
    course_minutes_basis: str = "course_default",
) -> dict[str, Any]:
    """把一节投影编译成固定栏目的课堂交付单。

    `sequence` 从 1 开始，就是教师看到的“第几讲”。所有派生都只依赖参数，不读全局
    状态，方便按小节单独重建与测试。
    """
    archetype = lesson_archetype if isinstance(lesson_archetype, dict) else {}
    plan_modules = _dicts(module_plan)
    module_plan_by_id = {
        module_id: module
        for module in plan_modules
        if (module_id := _text(module.get("module_id")))
    }
    modules = _dicts(section.get("teaching_modules"))
    actual_module_ids = [
        module_id
        for module in modules
        if (module_id := _text(module.get("module_id")))
    ]

    key_points = _strings(section.get("key_points"))
    owned_names = {_normalized(name) for name in key_points}
    rows = _knowledge_rows(section, owned_names=owned_names)
    matchers = _knowledge_matcher([
        name
        for row in rows
        for name in [row["name"], *row["aliases"]]
    ])

    section_minutes = _minutes(section.get("planned_minutes"), upper=240)
    timeline = _timeline_rubric(
        modules=modules,
        module_plan_by_id=module_plan_by_id,
        section_minutes=section_minutes,
        course_lesson_minutes=course_lesson_minutes,
        course_minutes_basis=course_minutes_basis,
    )

    checks = _strings(section.get("in_class_checks"))
    homework = _strings(section.get("homework"))
    check_items = [
        {"text": text, "knowledge_names": _mentioned_names(text, matchers)}
        for text in checks
    ]
    homework_items = [
        {"text": text, "knowledge_names": _mentioned_names(text, matchers)}
        for text in homework
    ]

    # 对照矩阵：一行一个知识点，把它出现在哪个环节、要求什么能力、按什么标准验收、
    # 被哪条课堂检查覆盖并排放。连不上的写进 gaps——这一列才是教师真正要看的。
    modules_by_knowledge: dict[str, list[dict[str, str]]] = {}
    for entry in timeline["entries"]:
        for name in entry["knowledge_names"]:
            modules_by_knowledge.setdefault(_normalized(name), []).append({
                "module_id": entry["module_id"],
                "label": entry["label"],
                "sequence": entry["sequence"],
            })
    alignment_rows = []
    for row in rows:
        normalized_name = _normalized(row["name"])
        row_modules = modules_by_knowledge.get(normalized_name, [])
        row_checks = [
            item["text"] for item in check_items
            if row["name"] in item["knowledge_names"]
            or any(alias in item["knowledge_names"] for alias in row["aliases"])
        ]
        row_homework = [
            item["text"] for item in homework_items
            if row["name"] in item["knowledge_names"]
            or any(alias in item["knowledge_names"] for alias in row["aliases"])
        ]
        gaps = []
        if not row_modules:
            gaps.append("module")
        if not row["capabilities"]:
            gaps.append("capability")
        if not row["mastery"]:
            gaps.append("mastery")
        if not row_checks and not row_homework:
            gaps.append("evidence")
        alignment_rows.append({
            "knowledge_id": row["knowledge_id"],
            "name": row["name"],
            "ownership": row["ownership"],
            "knowledge_type": row["knowledge_type"],
            "modules": row_modules,
            "capabilities": row["capabilities"],
            "mastery": row["mastery"],
            "checks": row_checks,
            "homework": row_homework,
            "gaps": gaps,
        })

    misconception_rows = [
        {
            "knowledge_id": row["knowledge_id"],
            "knowledge_name": row["name"],
            **item,
        }
        for row in rows
        for item in row["misconceptions"]
    ]

    objectives = []
    if learning_objective:
        objectives.append({
            "text": learning_objective,
            "source": "outline",
            "knowledge_name": "",
        })
    for row in rows:
        if row["ownership"] != "owned":
            continue
        for capability in row["capabilities"]:
            objectives.append({
                "text": capability,
                "source": "capability",
                "knowledge_name": row["name"],
            })

    criteria = [
        {
            "knowledge_name": row["name"],
            "performance": item["performance"],
            "verification": item["verification"],
        }
        for row in rows
        for item in row["mastery"]
    ]

    guardrails = _strings(archetype.get("guardrails"))
    notes = _strings(section.get("teaching_notes"))
    resources = _strings(section.get("resource_refs"))
    difficulties = _strings(section.get("key_difficulties"))
    teacher_activities = _strings(section.get("teacher_activities"))
    student_activities = _strings(section.get("student_activities"))

    rubrics = [
        _rubric(
            "lesson_identity",
            "facts",
            item_count=1,
            node_id=_text(section.get("node_id")),
            sequence=sequence,
            title=node_title,
            chapter_title=chapter_title,
            template_label=_text(archetype.get("label")),
            course_stage=_text(archetype.get("course_stage")),
            planned_minutes=timeline["total_minutes"],
            minutes_basis=timeline["minutes_basis"],
            knowledge_point_count=len(rows),
            module_count=len(timeline["entries"]),
        ),
        _rubric("objectives", "list", item_count=len(objectives), items=objectives),
        _rubric(
            "focus",
            "split_list",
            item_count=len(key_points) + len(difficulties),
            key_points=key_points,
            difficulties=difficulties,
        ),
        _rubric(
            "knowledge",
            "table",
            item_count=len(rows),
            columns=("name", "type", "statement", "prerequisite"),
            rows=[
                {
                    "knowledge_id": row["knowledge_id"],
                    "knowledge_status": row["knowledge_status"],
                    "name": row["name"],
                    "concept_group": row["concept_group"],
                    "knowledge_type": row["knowledge_type"],
                    "statement": row["statement"],
                    "prerequisite_names": row["prerequisite_names"],
                    "boundaries": row["boundaries"],
                    "ownership": row["ownership"],
                }
                for row in rows
            ],
            reused_knowledge_names=_strings(section.get("reused_knowledge_names")),
            relations=[
                {
                    "source_name": _text(relation.get("source_name")),
                    "target_name": _text(relation.get("target_name")),
                    "relation_type": _text(relation.get("relation_type")),
                    "reason": _text(relation.get("reason")),
                }
                for relation in _dicts(section.get("knowledge_relations"))
            ],
        ),
        timeline,
        _rubric(
            "alignment",
            "table",
            item_count=len(alignment_rows),
            columns=("knowledge", "module", "capability", "mastery", "evidence"),
            rows=alignment_rows,
            gap_count=len([row for row in alignment_rows if row["gaps"]]),
        ),
        _rubric(
            "misconceptions",
            "table",
            item_count=len(misconception_rows),
            columns=("knowledge", "error_pattern", "discrimination", "repair"),
            rows=misconception_rows,
        ),
        _rubric(
            "assessment",
            "list",
            item_count=len(check_items) + len(criteria),
            checks=check_items,
            criteria=criteria,
        ),
        _rubric("homework", "list", item_count=len(homework_items), items=homework_items),
        _rubric("resources", "list", item_count=len(resources), items=resources),
        _rubric(
            "notes",
            "list",
            item_count=len(notes) + len(guardrails) + len(teacher_activities) + len(student_activities),
            items=notes,
            guardrails=guardrails,
            teacher_activities=teacher_activities,
            student_activities=student_activities,
        ),
    ]

    granularity = {
        "knowledge_point_count": len(rows),
        "module_count": len(timeline["entries"]),
        "planned_minutes": timeline["total_minutes"] or 0,
        "objective_count": len(objectives),
        "capability_count": sum(len(row["capabilities"]) for row in rows),
        "mastery_count": len(criteria),
        "misconception_count": len(misconception_rows),
        "check_count": len(check_items),
        "homework_count": len(homework_items),
        "alignment_gap_count": len([row for row in alignment_rows if row["gaps"]]),
        "filled_rubric_count": len([
            rubric for rubric in rubrics if rubric["status"] == "filled"
        ]),
        "rubric_count": len(rubrics),
    }

    return {
        "schema_version": LESSON_DOSSIER_SCHEMA_VERSION,
        "node_id": _text(section.get("node_id")),
        "sequence": sequence,
        "title": node_title,
        "chapter_title": chapter_title,
        "template": _template_contract(
            archetype=archetype,
            module_plan=plan_modules,
            actual_module_ids=actual_module_ids,
        ),
        "rubric_keys": list(RUBRIC_KEYS),
        "rubrics": rubrics,
        "granularity": granularity,
    }


def _band(values: list[int]) -> dict[str, Any]:
    """按中位数给一个宽松的可比区间。

    用中位数而不是均值：一节把 20 个知识点堆在一起时，均值会被它拉走，于是所有
    正常小节反过来被判成“偏少”，对照就失去意义。

    `filled_sections` 单独报出来，是为了区分两种完全不同的情况：全课都没填这项
    （不是波动，是整体缺失），和只有个别小节填了（这才是教师翻页时看到的波动）。
    """
    ordered = sorted(values)
    count = len(ordered)
    filled = len([value for value in ordered if value > 0])
    if not count:
        return {
            "median": 0, "low": 0, "high": 0, "min": 0, "max": 0,
            "filled_sections": 0, "section_count": 0,
        }
    middle = count // 2
    median = (
        ordered[middle]
        if count % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    span = max(1.0, median * 0.5)
    return {
        "median": round(median, 1),
        "low": max(0, int(floor(median - span))),
        "high": int(ceil(median + span)),
        "min": ordered[0],
        "max": ordered[-1],
        "filled_sections": filled,
        "section_count": count,
    }


def build_lesson_dossier_consistency(
    dossiers: list[dict[str, Any]],
) -> dict[str, Any]:
    """全课颗粒度对照：任取三节能不能看出栏目结构与体量是否一致。

    栏目结构一致是硬事实（`uniform_rubric_structure`）；体量一致是相对判断，用课程
    自己的中位数定区间，超出区间的小节点名列出，教师可以直接翻过去看。
    """
    valid = [item for item in dossiers if isinstance(item, dict) and item.get("rubrics")]
    section_count = len(valid)
    reference = list(RUBRIC_KEYS)
    uniform = all(
        [rubric["key"] for rubric in dossier["rubrics"]] == reference
        for dossier in valid
    )

    coverage = []
    for index, key in enumerate(reference):
        filled = len([
            dossier for dossier in valid
            if index < len(dossier["rubrics"])
            and dossier["rubrics"][index]["key"] == key
            and dossier["rubrics"][index]["status"] == "filled"
        ])
        coverage.append({
            "key": key,
            "filled_sections": filled,
            "section_count": section_count,
        })

    bands = {
        metric: _band([
            int(dossier["granularity"].get(metric) or 0) for dossier in valid
        ])
        for metric in _BANDED_METRICS
    }

    sections = []
    for dossier in valid:
        granularity = dossier["granularity"]
        flags = []
        for metric in _BANDED_METRICS:
            band = bands[metric]
            value = int(granularity.get(metric) or 0)
            # 全课都没填这项时不算波动：那是整体缺失，已经由 band.filled_sections
            # 报出来了；再给每一节挂一个“偏低”只会把真正的异常节淹掉。
            if band["filled_sections"] <= 0:
                continue
            if value < band["low"]:
                flags.append(f"{metric}_below_band")
            elif value > band["high"]:
                flags.append(f"{metric}_above_band")
        if granularity.get("alignment_gap_count"):
            flags.append("alignment_gap")
        sections.append({
            "node_id": dossier["node_id"],
            "sequence": dossier["sequence"],
            "title": dossier["title"],
            "template_id": (dossier.get("template") or {}).get("template_id", ""),
            "granularity": granularity,
            "flags": flags,
        })

    return {
        "schema_version": LESSON_DOSSIER_CONSISTENCY_SCHEMA_VERSION,
        "section_count": section_count,
        "rubric_keys": reference,
        "uniform_rubric_structure": uniform,
        "rubric_coverage": coverage,
        "bands": bands,
        "sections": sections,
        "outlier_node_ids": [
            item["node_id"] for item in sections
            if [flag for flag in item["flags"] if flag != "alignment_gap"]
        ],
    }


__all__ = [
    "LESSON_DOSSIER_SCHEMA_VERSION",
    "LESSON_DOSSIER_CONSISTENCY_SCHEMA_VERSION",
    "LESSON_TEMPLATE_CONTRACT_SCHEMA_VERSION",
    "RUBRIC_KEYS",
    "RUBRIC_SPECS",
    "build_lesson_dossier",
    "build_lesson_dossier_consistency",
]
