"""知识语义字段的编辑边界（tasks 2.4）。

字段白名单沿用 recovered/plan-baseline 的 contracts.md §2.4：开放
statement / capability / conditions / boundaries / counterexamples /
misconceptions / mastery_criteria，一律 requires_impact_review；
稳定知识 ID、来源绑定、编译状态与知识点改名不在其中（§3、§4.3）。

这里守的核心是两条：
1. 教师编辑「易错表现」「掌握标准」时，改的是那一句话本身——配套的
   verification_method / repair_strategy 不该因为改了一句话就被抹掉。
2. 稳定身份永远不可写：knowledge_id、绑定、改名都必须被挡住，否则
   路径与绑定会一起断掉。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_repository import CourseDocumentRepository
from teaching_plan_workbench import (
    TeachingPlanWorkbenchError,
    TeachingPlanWorkbenchService,
    field_permission,
)


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


def _course() -> dict:
    document = refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="一次函数",
        sections=[CourseSection(
            section_id="section-1",
            parent_section_id="chapter-1",
            title="斜率",
            position=0,
            level=2,
            learning_objective="理解斜率的变化意义",
        )],
        blocks=[CourseBlock(
            block_id="block-1",
            section_id="section-1",
            position=0,
            role="concept",
            payload={"markdown": "斜率描述变化率。"},
        )],
    ))
    return {
        "course_id": "course-1",
        "course_name": "一次函数",
        "course_schema_version": "course_document_v1",
        "course_document_authoritative": True,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "course_plan": {
            "course_title": "一次函数",
            "positioning": "从变化率建立函数直觉",
            "learning_objectives": ["理解斜率表示的变化关系"],
            "prerequisites": ["平面直角坐标系"],
            "chapters": [{
                "chapter_number": 1,
                "title": "变化率",
                "sections": [{
                    "node_id": "section-1",
                    "title": "斜率",
                    "learning_objective": "理解斜率的变化意义",
                    "module_plan": [{
                        "module_id": "core",
                        "label": "核心讲解",
                        "required": True,
                        "output_contract": "解释斜率",
                        "prompt_instruction": "从图像和公式说明斜率",
                    }],
                }],
            }],
        },
        "generation_request": {"target_audience": "初中二年级学生"},
        "subject_pedagogy_profile": {"rationale": "先观察图像，再归纳公式。"},
        "course_teaching_plan": {
            "schema_version": "course_teaching_plan_v3",
            "source_outline_revision_id": "outline-1",
            "revision_id": "teaching-initial",
            "sections": [{
                "node_id": "section-1",
                "key_points": ["斜率"],
                "reused_knowledge_names": [],
                "knowledge_relations": [],
                "knowledge_structure": [{
                    "concept_group": "变化率",
                    "knowledge_points": [{
                        "name": "斜率",
                        "knowledge_id": "k-slope",
                        "statement": "斜率描述横坐标每变化一个单位时的纵坐标变化量。",
                        "capability": "能够解释斜率的正负与大小",
                        "conditions": ["在平面直角坐标系中"],
                        "boundaries": [],
                        "counterexamples": [],
                        "mastery_criteria": [{
                            "observable_performance": "能由两点求斜率",
                            "verification_method": "出口题",
                        }],
                        "misconceptions": [{
                            "observable_error_pattern": "把斜率读成纵坐标差",
                            "repair_strategy": "用两点差值重新推导",
                        }],
                    }],
                }],
                "teaching_modules": [{
                    "module_id": "core",
                    "teaching_purpose": "建立变化率直觉",
                    "knowledge_names": ["斜率"],
                    "teaching_guidance": "先比较两段路程，再归纳斜率公式。",
                }],
            }],
        },
        "generation_stage_artifacts": {"course_teaching_plan": {"status": "completed"}},
    }


KNOWLEDGE = "sections/section-1/knowledge/斜率"


def _point(storage: MemoryStorage, *, draft_actor: str | None = None) -> dict:
    if draft_actor:
        source = storage.course["teaching_plan_workbench"]["drafts"][draft_actor]["snapshot"]
    else:
        source = storage.course
    return source["course_teaching_plan"]["sections"][0]["knowledge_structure"][0]["knowledge_points"][0]


async def _open_draft(service: TeachingPlanWorkbenchService, actor: str) -> str:
    view = service.view("course-1", actor=actor)
    created = await service.create_draft(
        "course-1",
        actor=actor,
        idempotency_key=f"create-{actor}",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    return created["draft"]["draft_id"]


def test_all_seven_semantic_fields_are_editable_and_identity_stays_readonly() -> None:
    for suffix in (
        "statement", "capability", "conditions", "boundaries",
        "counterexamples", "misconceptions", "mastery_criteria",
    ):
        permission = field_permission(f"{KNOWLEDGE}/{suffix}")
        assert permission["state"] == "requires_impact_review", suffix

    # 稳定身份、绑定、编译状态与改名：一律不可写（contracts §3、§4.3）。
    for suffix in (
        "knowledge_id", "binding_id", "source_revision",
        "knowledge_status", "name", "aliases", "knowledge_type",
    ):
        assert field_permission(f"{KNOWLEDGE}/{suffix}")["state"] == "readonly", suffix


@pytest.mark.asyncio
async def test_semantic_edits_land_in_the_draft_without_touching_the_official_plan() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")
    before_official = deepcopy(storage.course["course_teaching_plan"])

    edits = {
        "conditions": ["在平面直角坐标系中", "两点横坐标不相等"],
        "boundaries": ["不适用于垂直直线"],
        "counterexamples": ["垂直线没有斜率"],
    }
    for index, (suffix, value) in enumerate(edits.items()):
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path=f"{KNOWLEDGE}/{suffix}",
            value=value,
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key=f"semantic-{index}",
        )

    draft_point = _point(storage, draft_actor="teacher-1")
    for suffix, value in edits.items():
        assert draft_point[suffix] == value

    # 草稿不是第二真源：正式教案在应用前一个字都不能变。
    assert storage.course["course_teaching_plan"] == before_official


@pytest.mark.asyncio
async def test_editing_a_criterion_keeps_its_verification_method() -> None:
    """改「掌握标准」这句话，不该把配套的验证方法一起抹掉。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")

    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path=f"{KNOWLEDGE}/mastery_criteria",
        value=["能由任意两点求斜率并解释正负"],
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="criterion-1",
    )
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path=f"{KNOWLEDGE}/misconceptions",
        value=["把斜率读成纵坐标之差"],
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="misconception-1",
    )

    point = _point(storage, draft_actor="teacher-1")
    assert point["mastery_criteria"] == [{
        "observable_performance": "能由任意两点求斜率并解释正负",
        "verification_method": "出口题",
    }]
    assert point["misconceptions"] == [{
        "observable_error_pattern": "把斜率读成纵坐标之差",
        "repair_strategy": "用两点差值重新推导",
    }]


@pytest.mark.asyncio
async def test_adding_a_criterion_beyond_the_existing_ones_does_not_invent_siblings() -> None:
    """新增的条目只带教师写的主字段，不凭空补验证方法。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")

    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path=f"{KNOWLEDGE}/mastery_criteria",
        value=["能由两点求斜率", "能解释斜率的正负含义"],
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="criterion-add",
    )

    criteria = _point(storage, draft_actor="teacher-1")["mastery_criteria"]
    assert criteria[0] == {
        "observable_performance": "能由两点求斜率",
        "verification_method": "出口题",
    }
    assert criteria[1] == {"observable_performance": "能解释斜率的正负含义"}


@pytest.mark.asyncio
async def test_stable_knowledge_identity_cannot_be_written_through_the_draft() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")
    before_official = deepcopy(storage.course["course_teaching_plan"])

    for index, suffix in enumerate(("knowledge_id", "name", "binding_id")):
        with pytest.raises(TeachingPlanWorkbenchError) as error:
            await service.patch_draft(
                "course-1",
                actor="teacher-1",
                draft_id=draft_id,
                path=f"{KNOWLEDGE}/{suffix}",
                value="不应写入",
                expected_value_hash="",
                base_plan_revision_id="",
                idempotency_key=f"identity-{index}",
            )
        assert error.value.code == "teaching_plan_readonly_field"

    assert storage.course["course_teaching_plan"] == before_official
    assert _point(storage, draft_actor="teacher-1")["knowledge_id"] == "k-slope"


@pytest.mark.asyncio
async def test_semantic_edit_reaches_the_official_plan_only_after_apply() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    draft_id = await _open_draft(service, "teacher-1")

    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path=f"{KNOWLEDGE}/boundaries",
        value=["不适用于垂直直线"],
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="apply-semantic",
    )
    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        idempotency_key="apply-semantic-review",
    )
    change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")

    # 影响分析必须把知识语义变化算进来，不能报「无影响」。
    assert change_set["impact_report"]["needs_regeneration"]

    applied = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set["change_set_id"],
        idempotency_key="apply-semantic-apply",
    )
    assert _point(storage)["boundaries"] == ["不适用于垂直直线"]
    assert applied["workbench"]["current_plan_revision_id"] != view["current_plan_revision_id"]


@pytest.mark.asyncio
async def test_unbound_knowledge_only_allows_descriptive_fields() -> None:
    """7.3：知识点未完成编译时只开放描述性字段。

    能力、掌握标准、易错、边界是知识库编译与下游绑定的输入。在知识点还没
    拿到稳定 knowledge_id 之前改它们，改动无处落脚、编译后会被覆盖——
    看起来保存成功了，其实静默丢失。所以这里明确挡住并说明补全要求。
    """
    course = _course()
    point = course["course_teaching_plan"]["sections"][0]["knowledge_structure"][0]["knowledge_points"][0]
    point.pop("knowledge_id", None)          # 模拟尚未编译

    storage = MemoryStorage(course)
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")

    by_path = {f["path"]: f for f in view["editable_fields"] if "/knowledge/" in f["path"]}
    # 描述性字段仍可编辑
    assert by_path[f"{KNOWLEDGE}/statement"]["state"] != "readonly"
    assert by_path[f"{KNOWLEDGE}/conditions"]["state"] != "readonly"
    # 结构性字段转只读，并给出补全要求
    for suffix in ("capability", "mastery_criteria", "misconceptions", "boundaries"):
        field = by_path[f"{KNOWLEDGE}/{suffix}"]
        assert field["state"] == "readonly", suffix
        assert "编译" in field["reason"]
        assert field.get("requires") == "knowledge_binding"

    draft_id = await _open_draft(service, "teacher-1")
    before = deepcopy(storage.course["course_teaching_plan"])

    # 写入侧同样把关：只在 UI 隐藏不够，API 仍可被直接调用
    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.patch_draft(
            "course-1", actor="teacher-1", draft_id=draft_id,
            path=f"{KNOWLEDGE}/capability", value="绕过 UI 直接写",
            expected_value_hash="", base_plan_revision_id="",
            idempotency_key="unbound-capability",
        )
    assert error.value.code == "teaching_plan_knowledge_binding_required"
    assert storage.course["course_teaching_plan"] == before

    # 描述性字段照常可写
    await service.patch_draft(
        "course-1", actor="teacher-1", draft_id=draft_id,
        path=f"{KNOWLEDGE}/statement", value="未绑定时仍可改陈述",
        expected_value_hash="", base_plan_revision_id="",
        idempotency_key="unbound-statement",
    )
    assert _point(storage, draft_actor="teacher-1")["statement"] == "未绑定时仍可改陈述"


@pytest.mark.asyncio
async def test_bound_knowledge_keeps_every_semantic_field_editable() -> None:
    """已完成编译的知识点不受 7.3 限制，七个字段照常可编辑。"""
    storage = MemoryStorage(_course())      # 夹具带 knowledge_id
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    by_path = {f["path"]: f for f in view["editable_fields"] if "/knowledge/" in f["path"]}
    for suffix in ("statement", "capability", "conditions", "boundaries",
                   "counterexamples", "misconceptions", "mastery_criteria"):
        assert by_path[f"{KNOWLEDGE}/{suffix}"]["state"] == "requires_impact_review", suffix
