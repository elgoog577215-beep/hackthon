from copy import deepcopy

import pytest

from course_knowledge_rebuild import (
    CourseKnowledgeRebuildError,
    CourseKnowledgeRebuildService,
)
from course_repository import CourseDocumentRepository
from learning_assets import compile_learning_assets


class MemoryStorage:
    def __init__(self, course):
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id):
        return deepcopy(self.course)

    async def save_course(self, _course_id, data):
        self.course = deepcopy(data)
        self.save_count += 1


class KnowledgeModel:
    def __init__(self, *, omit_mastery=False):
        self.calls = 0
        self.omit_mastery = omit_mastery

    async def generate_batch(self, *, course_name, sections, existing_knowledge_names):
        del course_name
        self.calls += 1
        generated = []
        for section in sections:
            title = section["title"]
            first_name = f"{title}的成立条件"
            second_name = f"{title}的应用规则"
            block_ids = [item["block_id"] for item in section["blocks"]]
            first_refs = block_ids[:1]
            second_refs = block_ids[1:] or block_ids[:1]
            first_mastery = [] if self.omit_mastery else [{
                "name": f"{title}条件判断达标",
                "observable_performance": f"独立判断新案例是否满足{title}的成立条件",
                "verification_method": "完成正例、反例与边界例分类",
            }]
            generated.append({
                "section_id": section["section_id"],
                "reused_knowledge_names": existing_knowledge_names[:1],
                "knowledge_structure": [{
                    "concept_group": f"{title}的语义结构",
                    "description": f"区分{title}的成立条件与应用规则",
                    "knowledge_points": [{
                        "name": first_name,
                        "statement": f"使用{title}前必须先识别对象并核对全部成立条件。",
                        "knowledge_type": "rule",
                        "conditions": [f"已经明确{title}处理的对象"],
                        "boundaries": [f"任一条件不成立时不能直接使用{title}"],
                        "content_block_refs": first_refs,
                        "capability_points": [{
                            "name": f"核对{title}条件",
                            "observable_behavior": f"给定案例，逐项判断{title}的成立条件",
                        }],
                        "misconceptions": [{
                            "name": f"跳过{title}条件检查",
                            "observable_error_pattern": f"未核对条件就直接套用{title}",
                            "discrimination": f"分别列出{title}的对象、条件与结论",
                            "repair_strategy": f"补做{title}条件清单后重新推理",
                        }],
                        "mastery_criteria": first_mastery,
                        "entry_reason": f"{first_name}是本节的学习入口。",
                        "relations": [{
                            "target_name": second_name,
                            "relation_type": "prerequisite",
                            "reason": f"先核对{title}的成立条件，才能应用规则",
                        }],
                    }, {
                        "name": second_name,
                        "statement": f"条件满足后，应使用{title}规则完成任务并检查结果。",
                        "knowledge_type": "procedure",
                        "conditions": [f"{title}的全部成立条件已经满足"],
                        "boundaries": [f"结果超出{title}适用范围时应更换方法"],
                        "content_block_refs": second_refs,
                        "capability_points": [{
                            "name": f"应用{title}规则",
                            "observable_behavior": f"在新情境中独立应用{title}并检查结果",
                        }],
                        "mastery_criteria": [{
                            "name": f"{title}应用达标",
                            "observable_performance": f"独立完成一个{title}迁移任务并说明检查过程",
                            "verification_method": "提交完整过程并使用边界例复核",
                        }],
                    }],
                }],
            })
        cross_batch_relations = []
        if existing_knowledge_names and generated:
            current_name = generated[0]["knowledge_structure"][0]["knowledge_points"][0]["name"]
            cross_batch_relations.append({
                "source_name": existing_knowledge_names[0],
                "target_name": current_name,
                "relation_type": "prerequisite",
                "reason": "前序小节的条件判断是后续小节独立应用规则的前提",
            })
        return {
            "sections": generated,
            "knowledge_relations": cross_batch_relations,
        }


def _course():
    return {
        "course_id": "legacy-course",
        "course_name": "历史编程课程",
        "course_purpose": "systematic",
        "subject_pedagogy_profile": {
            "primary_mode": "programming_engineering",
            "secondary_mode": None,
            "secondary_intensity": None,
            "confidence": "high",
            "evidence": [],
            "rationale": "test",
            "enabled_module_ids": [],
            "user_locked": True,
        },
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "变量绑定",
            "node_content": (
                "## 赋值语句\n\n赋值语句让变量名指向一个值。\n\n"
                "## 状态追踪\n\n逐步执行赋值语句并记录变量当前值。"
            ),
            "learning_objective": "能够解释并追踪变量绑定",
            "key_points": ["变量"],
            "assessment": ["追踪一组赋值语句并解释结果"],
            "difficulty_contract": {
                "challenge": {"reasoning_depth": 2},
                "support": {"scaffold_intensity": 2},
                "mastery": {"independence": 2},
                "subject_task": "implementation_task",
            },
            "grounding_contract": {},
        }, {
            "node_id": "L2-1-2",
            "node_level": 2,
            "node_name": "函数调用",
            "node_content": (
                "## 参数传入\n\n调用函数时把实参传给形参。\n\n"
                "## 返回结果\n\n函数可以把计算结果返回给调用方。"
            ),
            "learning_objective": "能够解释函数调用的输入与返回",
            "key_points": ["函数"],
            "assessment": ["解释一次函数调用的参数与返回值"],
            "difficulty_contract": {
                "challenge": {"reasoning_depth": 2},
                "support": {"scaffold_intensity": 2},
                "mastery": {"independence": 2},
                "subject_task": "implementation_task",
            },
            "grounding_contract": {},
        }],
    }


@pytest.mark.asyncio
async def test_historical_course_rebuild_persists_only_quality_passed_course_knowledge():
    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    model = KnowledgeModel()
    service = CourseKnowledgeRebuildService(repository, model=model, batch_size=1)

    result = await service.rebuild_course("legacy-course", force=True)

    assert model.calls == 2
    assert result["library"]["lifecycle_status"] == "accepted"
    assert result["course_knowledge_base"]["lifecycle_status"] == "active"
    assert result["quality_report"]["strict_passed"] is True
    assert result["generation_calls"] == 2
    assert storage.save_count == 1
    assert storage.course["course_knowledge_base"]["source_course_fingerprint"].startswith("cksrc_")
    assert storage.course["course_knowledge_rebuild_audit"]["section_count"] == 2
    assert storage.course["learning_assets"]["questions"][0]["course_knowledge_refs"]
    assert storage.course["learning_assets"]["knowledge_library"][0]["nodes"]
    points = {
        item["knowledge_id"]: item
        for item in result["course_knowledge_base"]["knowledge_points"]
    }
    assert any(
        "L2-1-1" in points[item["source_knowledge_id"]]["section_refs"]
        and "L2-1-2" in points[item["target_knowledge_id"]]["section_refs"]
        for item in result["course_knowledge_base"]["relations"]
    )
    assert any(
        set(item["section_refs"]) == {"L2-1-1", "L2-1-2"}
        for item in points.values()
    )


@pytest.mark.asyncio
async def test_persisted_course_knowledge_is_reused_when_course_content_is_unchanged():
    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    model = KnowledgeModel()
    service = CourseKnowledgeRebuildService(repository, model=model)
    await service.rebuild_course("legacy-course", force=True)

    recompiled = compile_learning_assets(repository.load_course_view("legacy-course"))
    reused = await service.rebuild_course("legacy-course", force=False)

    knowledge_base = recompiled["assets"]["course_knowledge_base"][0]
    assert knowledge_base["lifecycle_status"] == "active"
    assert knowledge_base["quality_report"]["strict_passed"] is True
    assert reused["reused"] is True
    assert reused["generation_calls"] == 0
    assert model.calls == 1


@pytest.mark.asyncio
async def test_persisted_course_knowledge_is_not_reused_after_course_content_changes():
    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    service = CourseKnowledgeRebuildService(repository, model=KnowledgeModel())
    await service.rebuild_course("legacy-course", force=True)
    storage.course["nodes"][0]["node_content"] += "\n\n新增了尚未知识化的闭包语义。"
    storage.course["nodes"][0].pop("content_blocks", None)

    recompiled = compile_learning_assets(repository.load_course_view("legacy-course"))

    knowledge_base = recompiled["assets"]["course_knowledge_base"][0]
    assert knowledge_base["lifecycle_status"] == "degraded"
    assert recompiled["assets"]["knowledge_library"][0]["nodes"] == []


@pytest.mark.asyncio
async def test_persisted_course_knowledge_is_not_reused_after_course_path_changes():
    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    service = CourseKnowledgeRebuildService(repository, model=KnowledgeModel())
    await service.rebuild_course("legacy-course", force=True)
    storage.course["nodes"][0]["parent_node_id"] = "L1-moved"

    recompiled = compile_learning_assets(repository.load_course_view("legacy-course"))

    knowledge_base = recompiled["assets"]["course_knowledge_base"][0]
    assert knowledge_base["lifecycle_status"] == "degraded"
    assert recompiled["assets"]["knowledge_library"][0]["nodes"] == []


@pytest.mark.asyncio
async def test_failed_historical_knowledge_candidate_never_mutates_course():
    original = _course()
    storage = MemoryStorage(original)
    repository = CourseDocumentRepository(storage)
    service = CourseKnowledgeRebuildService(
        repository,
        model=KnowledgeModel(omit_mastery=True),
    )

    with pytest.raises(CourseKnowledgeRebuildError) as raised:
        await service.rebuild_course("legacy-course", force=True)

    assert raised.value.code == "knowledge_quality_failed"
    assert raised.value.quality_report["strict_passed"] is False
    assert storage.save_count == 0
    assert storage.course == original


@pytest.mark.asyncio
async def test_historical_rebuild_refuses_to_invent_knowledge_from_empty_section_title():
    course = _course()
    course["nodes"][0]["node_content"] = ""
    storage = MemoryStorage(course)
    model = KnowledgeModel()
    service = CourseKnowledgeRebuildService(
        CourseDocumentRepository(storage),
        model=model,
    )

    with pytest.raises(CourseKnowledgeRebuildError) as raised:
        await service.rebuild_course("legacy-course", force=True)

    assert raised.value.code == "course_section_has_no_source_content"
    assert model.calls == 0
    assert storage.save_count == 0
    assert storage.course == course
