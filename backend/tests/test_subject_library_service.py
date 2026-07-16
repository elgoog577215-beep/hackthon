from copy import deepcopy

import pytest

from ai_base import AIProviderRequestError
from course_repository import CourseDocumentRepository
from subject_library_repository import SubjectLibraryRepository
from subject_library_service import (
    SubjectLibraryService,
    SubjectLibraryVersionConflict,
    SubjectOntologyGenerationError,
)
from subject_ontology import build_subject_ontology

from test_subject_ontology_pipeline import _cpp_course, _cpp_proposal
from test_subject_library_v3 import _data_structures_course


class _Storage:
    def __init__(self, courses):
        self.courses = {item["course_id"]: deepcopy(item) for item in courses}

    def load_course(self, course_id):
        return deepcopy(self.courses.get(course_id) or {})

    async def save_course(self, course_id, value):
        self.courses[course_id] = deepcopy(value)

    def list_courses(self):
        return [
            {"course_id": course_id, "course_name": value.get("course_name")}
            for course_id, value in self.courses.items()
        ]


@pytest.mark.asyncio
async def test_rebuild_persists_candidate_and_pins_course_binding(tmp_path):
    course = _data_structures_course()
    storage = _Storage([course])
    repository = SubjectLibraryRepository(tmp_path / "libraries")
    service = SubjectLibraryService(
        CourseDocumentRepository(storage),
        repository,
        use_model=False,
    )

    result = await service.rebuild_course(course["course_id"])
    persisted = storage.load_course(course["course_id"])

    assert result["library"]["lifecycle_status"] == "candidate"
    assert result["quality_report"]["passed"] is True
    assert result["course_map"]["schema_version"] == "course_knowledge_map_v2"
    assert persisted["knowledge_library_binding"]["revision_id"] == result["library"]["revision_id"]
    assert persisted["knowledge_library_binding"]["binding_status"] == "pinned"


@pytest.mark.asyncio
async def test_accept_is_idempotent_and_stale_review_conflicts(tmp_path):
    course = _data_structures_course()
    storage = _Storage([course])
    repository = SubjectLibraryRepository(tmp_path / "libraries")
    service = SubjectLibraryService(CourseDocumentRepository(storage), repository, use_model=False)
    built = await service.rebuild_course(course["course_id"])
    revision_id = built["library"]["revision_id"]

    accepted = await service.review_course_library(
        course["course_id"], revision_id=revision_id, decision="accept", note="通过",
    )
    repeated = await service.review_course_library(
        course["course_id"], revision_id=revision_id, decision="accept", note="重复",
    )

    assert accepted["library"]["lifecycle_status"] == "accepted"
    assert repeated["library"]["revision_id"] == revision_id
    with pytest.raises(SubjectLibraryVersionConflict):
        await service.review_course_library(
            course["course_id"], revision_id="sklr_stale", decision="accept",
        )


@pytest.mark.asyncio
async def test_accepted_library_is_reused_by_another_course(tmp_path):
    first = _data_structures_course("course-a")
    second = _data_structures_course("course-b")
    storage = _Storage([first, second])
    repository = SubjectLibraryRepository(tmp_path / "libraries")
    service = SubjectLibraryService(CourseDocumentRepository(storage), repository, use_model=False)
    built = await service.rebuild_course(first["course_id"])
    await service.review_course_library(
        first["course_id"], revision_id=built["library"]["revision_id"], decision="accept",
    )

    reused = await service.rebuild_course(second["course_id"])

    assert reused["reused_accepted"] is True
    assert reused["library"]["revision_id"] == built["library"]["revision_id"]
    assert storage.load_course(second["course_id"])["knowledge_library_binding"]["lifecycle_status"] == "accepted"


@pytest.mark.asyncio
async def test_subject_group_rebuild_generates_one_revision_and_pins_every_source_course(tmp_path):
    first = _data_structures_course("course-a")
    second = _data_structures_course("course-b")
    storage = _Storage([first, second])
    repository = SubjectLibraryRepository(tmp_path / "libraries")
    service = SubjectLibraryService(CourseDocumentRepository(storage), repository, use_model=False)

    results = await service.rebuild_courses(["course-a", "course-b"])

    assert len(results) == 2
    assert {item["library"]["revision_id"] for item in results} == {
        results[0]["library"]["revision_id"],
    }
    assert results[0]["library"]["source_course_ids"] == ["course-a", "course-b"]
    assert storage.load_course("course-a")["knowledge_library_binding"]["revision_id"] == results[0]["library"]["revision_id"]
    assert storage.load_course("course-b")["knowledge_library_binding"]["revision_id"] == results[0]["library"]["revision_id"]


@pytest.mark.asyncio
async def test_migration_can_pin_curated_linear_algebra_even_when_course_wording_does_not_map(tmp_path):
    course = {
        "course_id": "linear-course",
        "course_name": "线性代数：理论与应用",
        "nodes": [{
            "node_id": "section-1",
            "node_level": 2,
            "node_name": "课程自定义表述",
            "key_points": ["完全不匹配预制别名的局部说法"],
            "content_blocks": [],
        }],
    }
    storage = _Storage([course])
    service = SubjectLibraryService(
        CourseDocumentRepository(storage),
        SubjectLibraryRepository(tmp_path / "libraries"),
        use_model=False,
    )

    results = await service.rebuild_courses(["linear-course"], prefer_curated=True)

    assert results[0]["library"]["library_id"] == "math.linear_algebra.v1"
    assert results[0]["library"]["lifecycle_status"] == "accepted"
    assert results[0]["reused_accepted"] is True
    assert storage.load_course("linear-course")["knowledge_library_binding"]["lifecycle_status"] == "accepted"


@pytest.mark.asyncio
async def test_canonical_subject_rebuild_records_old_to_new_knowledge_identity_migrations(tmp_path):
    nodes = [{
        "node_id": "section-1",
        "node_level": 2,
        "node_name": "极限与连续",
        "knowledge_structure": [{
            "topic": "函数极限",
            "knowledge_points": ["极限定义", "连续性"],
        }],
        "content_blocks": [],
    }]
    old_course = {"course_id": "old", "course_name": "未注册数学专题", "nodes": deepcopy(nodes)}
    current_course = {"course_id": "calculus", "course_name": "微积分理论", "nodes": deepcopy(nodes)}
    storage = _Storage([current_course])
    repository = SubjectLibraryRepository(tmp_path / "libraries")
    old_library = repository.save_revision(build_subject_ontology(old_course))
    storage.courses["calculus"]["knowledge_library_binding"] = repository.binding_for(old_library)
    service = SubjectLibraryService(CourseDocumentRepository(storage), repository, use_model=False)

    result = await service.rebuild_course("calculus")

    migrations = result["library"]["identity_migrations"]
    assert migrations
    assert all(item["old_knowledge_id"] != item["new_knowledge_id"] for item in migrations)
    assert {item["from_library_id"] for item in migrations} == {old_library["library_id"]}
    assert {item["to_library_id"] for item in migrations} == {"math.calculus"}


@pytest.mark.asyncio
async def test_failed_quality_uses_degraded_course_index(tmp_path, monkeypatch):
    course = _data_structures_course()
    storage = _Storage([course])
    service = SubjectLibraryService(
        CourseDocumentRepository(storage),
        SubjectLibraryRepository(tmp_path / "libraries"),
        use_model=False,
    )
    monkeypatch.setattr(
        "subject_library_service.evaluate_subject_ontology_quality",
        lambda *_args, **_kwargs: {
            "passed": False,
            "score": 10,
            "metrics": {},
            "issues": [{"code": "course_outline_mirror", "severity": "critical", "message": "mirror"}],
            "blocking_issues": [{"code": "course_outline_mirror", "severity": "critical", "message": "mirror"}],
        },
    )

    result = await service.rebuild_course(course["course_id"])

    assert result["library"]["lifecycle_status"] == "degraded"
    assert result["library"]["origin"] == "course_index"
    assert storage.load_course(course["course_id"])["knowledge_library_binding"]["lifecycle_status"] == "degraded"


class _RepairingOntologyModel:
    def __init__(self):
        self.calls = {"generate": 0, "review": 0, "repair": 0}

    async def generate(self, course):
        self.calls["generate"] += 1
        return _cpp_proposal()

    async def review(self, library):
        self.calls["review"] += 1
        return {"passed": False, "issues": ["领域名称需要更明确"]}

    async def repair(self, course, library, issues):
        self.calls["repair"] += 1
        proposal = _cpp_proposal()
        proposal["domains"][0]["name"] = "C++ 核心语言机制"
        return proposal


@pytest.mark.asyncio
async def test_model_pipeline_generates_reviews_and_structurally_repairs_once(tmp_path):
    course = _cpp_course()
    storage = _Storage([course])
    model = _RepairingOntologyModel()
    service = SubjectLibraryService(
        CourseDocumentRepository(storage),
        SubjectLibraryRepository(tmp_path / "libraries"),
        model=model,
    )

    result = await service.rebuild_course(course["course_id"])

    assert model.calls == {"generate": 1, "review": 1, "repair": 1}
    assert result["library"]["lifecycle_status"] == "candidate"
    assert result["quality_report"]["passed"] is True
    assert "C++ 核心语言机制" in {
        node["name"] for node in result["library"]["nodes"] if node["node_type"] == "domain"
    }
    assert result["library"]["generation_audit"]["semantic_review"]["passed"] is False


class _QuotaFailureOntologyModel:
    async def generate(self, course):
        raise AIProviderRequestError("insufficient_quota")

    async def review(self, library):
        raise AssertionError("review must not run after generation failure")

    async def repair(self, course, library, issues):
        raise AssertionError("repair must not run after generation failure")


@pytest.mark.asyncio
async def test_explicit_rebuild_propagates_provider_failure_without_saving_revision(tmp_path):
    course = _cpp_course()
    storage = _Storage([course])
    repository = SubjectLibraryRepository(tmp_path / "libraries")
    service = SubjectLibraryService(
        CourseDocumentRepository(storage),
        repository,
        model=_QuotaFailureOntologyModel(),
    )

    with pytest.raises(SubjectOntologyGenerationError) as error:
        await service.rebuild_course(course["course_id"])

    assert error.value.code == "insufficient_quota"
    assert repository.list_revisions("computer_science.cpp") == []
    assert not storage.load_course(course["course_id"]).get("knowledge_library_binding")


class _PassingOntologyModel:
    def __init__(self):
        self.generation_calls = 0

    async def generate(self, course):
        self.generation_calls += 1
        return _cpp_proposal()

    async def review(self, library):
        return {"passed": True, "issues": []}

    async def repair(self, course, library, issues):
        raise AssertionError("repair is not needed for a passing proposal")


@pytest.mark.asyncio
async def test_generic_course_candidate_acceptance_is_reused_by_next_course(tmp_path):
    first = _cpp_course("cpp-a")
    second = _cpp_course("cpp-b")
    storage = _Storage([first, second])
    model = _PassingOntologyModel()
    repository = SubjectLibraryRepository(tmp_path / "libraries")
    service = SubjectLibraryService(CourseDocumentRepository(storage), repository, model=model)

    built = await service.rebuild_course("cpp-a")
    assert built["library"]["lifecycle_status"] == "candidate"
    await service.review_course_library(
        "cpp-a", revision_id=built["library"]["revision_id"], decision="accept",
    )
    reused = await service.rebuild_course("cpp-b")

    assert reused["reused_accepted"] is True
    assert reused["library"]["revision_id"] == built["library"]["revision_id"]
    assert model.generation_calls == 1


@pytest.mark.asyncio
async def test_degraded_revision_cannot_be_accepted(tmp_path, monkeypatch):
    course = _data_structures_course()
    storage = _Storage([course])
    service = SubjectLibraryService(
        CourseDocumentRepository(storage),
        SubjectLibraryRepository(tmp_path / "libraries"),
        use_model=False,
    )
    monkeypatch.setattr(
        "subject_library_service.evaluate_subject_ontology_quality",
        lambda *_args, **_kwargs: {
            "passed": False, "score": 0, "metrics": {},
            "issues": [{"code": "broken", "severity": "critical", "message": "broken"}],
            "blocking_issues": [{"code": "broken", "severity": "critical", "message": "broken"}],
        },
    )
    built = await service.rebuild_course(course["course_id"])

    with pytest.raises(SubjectLibraryVersionConflict):
        await service.review_course_library(
            course["course_id"], revision_id=built["library"]["revision_id"], decision="accept",
        )
