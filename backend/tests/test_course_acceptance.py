from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from content_blocks import set_node_content_blocks
from course_acceptance import inspect_course_acceptance, scan_course_directory
from course_document import COURSE_DOCUMENT_SCHEMA, document_from_legacy_course
from learning_assets import compile_learning_assets
from routers import course_acceptance as acceptance_router


def _knowledge_structure(name):
    definition = f"{name}的定义条件"
    boundary = f"{name}的应用边界"
    return [{
        "concept_group": f"{name}的核心结构",
        "description": f"区分{name}的成立条件与应用边界",
        "knowledge_points": [{
            "name": definition,
            "statement": f"{name}只有在明确对象与成立条件后，才能作为后续推理依据。",
            "knowledge_type": "definition",
            "conditions": [f"已经明确{name}所处理的对象"],
            "boundaries": [f"超出{name}定义域时不能直接使用"],
            "capability_points": [{
                "name": f"解释{name}定义",
                "observable_behavior": f"给定一个案例，准确说出{name}的对象与成立条件",
            }],
            "misconceptions": [{
                "name": f"忽略{name}的适用条件",
                "observable_error_pattern": f"未检查条件就直接使用{name}",
                "discrimination": f"逐项核对{name}的对象、条件与结论",
                "repair_strategy": f"先标注{name}的成立条件，再重新完成推理",
            }],
            "mastery_criteria": [{
                "name": f"{name}定义解释达标",
                "observable_performance": f"独立解释{name}的定义、条件与一个反例",
                "verification_method": "使用正例、反例和边界例进行口头或书面验收",
            }],
            "entry_reason": f"{definition}是本节的学习入口。",
            "relations": [{
                "target_name": boundary,
                "relation_type": "prerequisite",
                "reason": f"先明确{name}的定义条件，才能判断其应用边界",
            }],
        }, {
            "name": boundary,
            "statement": f"应用{name}前必须检查成立条件，超出边界时需要更换方法。",
            "knowledge_type": "rule",
            "conditions": [f"案例满足{name}的成立条件"],
            "boundaries": [f"存在违反{name}成立条件的边界例"],
            "capability_points": [{
                "name": f"判断{name}边界",
                "observable_behavior": f"在新情境中判断{name}是否适用并说明依据",
            }],
            "mastery_criteria": [{
                "name": f"{name}边界判断达标",
                "observable_performance": f"独立判断{name}在新情境中的适用性并检查结果",
                "verification_method": "完成一个迁移任务并说明条件检查过程",
            }],
        }],
    }]


def _node(node_id, parent_id, name, *, prerequisite_node_ids=None):
    return {
        "node_id": node_id,
        "parent_node_id": parent_id,
        "node_level": 2,
        "node_name": name,
        "node_content": (
            f"## {name}的定义条件\n\n说明{name}的对象、成立条件与反例。\n\n"
            f"## {name}的应用边界\n\n在新情境中检查{name}是否适用。"
        ),
        "learning_objective": f"能够解释并应用{name}",
        "knowledge_structure": _knowledge_structure(name),
        "key_points": [f"{name}的定义条件", f"{name}的应用边界"],
        "assessment": [f"在新情境中应用{name}并检查结果"],
        "misconceptions": [f"忽略{name}的适用条件"] if node_id == "L2-1-1" else [],
        "prerequisite_node_ids": prerequisite_node_ids or [],
        "difficulty_contract": {
            "challenge": {"reasoning_steps": 2},
            "support": {"scaffold_intensity": 2},
        },
        "grounding_contract": {},
    }


def _ready_course(*, reading_only=False):
    course = {
        "course_id": "course-ready",
        "course_name": "线性代数验收课程",
        "course_purpose": "material_organization" if reading_only else "systematic",
        "generation_request": {
            "asset_preferences": {"questions": False},
        } if reading_only else {},
        "subject_pedagogy_profile": {
            "primary_mode": "math_formal",
            "secondary_mode": None,
            "secondary_intensity": None,
            "confidence": "high",
            "evidence": [],
            "rationale": "acceptance fixture",
            "enabled_module_ids": [],
            "user_locked": True,
        },
        "nodes": [
            {"node_id": "L1-1", "parent_node_id": "root", "node_level": 1, "node_name": "第一章"},
            _node("L2-1-1", "L1-1", "向量"),
            _node("L2-1-2", "L1-1", "矩阵", prerequisite_node_ids=["L2-1-1"]),
            {"node_id": "L1-2", "parent_node_id": "root", "node_level": 1, "node_name": "第二章"},
            _node("L2-2-1", "L1-2", "线性方程组", prerequisite_node_ids=["L2-1-2"]),
            _node("L2-2-2", "L1-2", "线性空间", prerequisite_node_ids=["L2-2-1"]),
        ],
    }
    for node in course["nodes"]:
        if node.get("node_level") == 2:
            set_node_content_blocks(node, node["node_content"])
    bundle = compile_learning_assets(course)
    course.update({
        "learning_asset_plan": bundle["plan"],
        "learning_assets": bundle["assets"],
        "learning_asset_bundle_revision_id": "lab_ready",
        "asset_quality_report": bundle["quality_report"],
        "generation_status": "passed",
        "current_course_version_id": "cv_ready",
    })
    return course


def _version_context():
    return {
        "repository_current_version_id": "cv_ready",
        "version_ids": ["cv_ready"],
        "version_count": 1,
    }


def _contract(report, contract_id):
    return next(item for item in report["contracts"] if item["contract_id"] == contract_id)


def test_standard_course_passes_all_six_contracts():
    report = inspect_course_acceptance(
        _ready_course(),
        requested_profile="standard",
        version_context=_version_context(),
    )

    assert report["status"] == "ready"
    assert report["ready_for_full_chain"] is True
    assert [item["status"] for item in report["contracts"]] == ["passed"] * 6
    assert report["blocking_issues"] == []


def test_migrated_canonical_course_can_retain_technical_version_history():
    course = _ready_course()
    document = document_from_legacy_course(course)
    course.pop("nodes")
    course.update({
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "course_document_authoritative": True,
    })

    report = inspect_course_acceptance(
        course,
        requested_profile="standard",
        version_context=_version_context(),
    )

    assert report["status"] == "ready"
    assert _contract(report, "version")["status"] == "passed"


def test_missing_questions_is_blocked_without_mutating_course():
    course = _ready_course()
    course["learning_assets"]["questions"] = []
    before = deepcopy(course)

    report = inspect_course_acceptance(
        course,
        requested_profile="auto",
        version_context=_version_context(),
    )

    assert report["acceptance_profile"] == "standard"
    assert report["status"] == "blocked"
    assert _contract(report, "practice")["status"] == "blocked"
    assert course == before


def test_explicit_reading_only_course_is_degraded_but_ready_for_scope():
    report = inspect_course_acceptance(
        _ready_course(reading_only=True),
        requested_profile="auto",
        version_context=_version_context(),
    )

    assert report["acceptance_profile"] == "reading_only"
    assert report["status"] == "degraded"
    assert report["ready_for_declared_scope"] is True
    assert _contract(report, "practice")["status"] == "degraded"
    assert _contract(report, "remediation")["status"] == "degraded"


def test_legacy_markdown_course_only_passes_explicit_compatibility_scope():
    course = {
        "course_id": "legacy-course",
        "course_name": "旧课程",
        "nodes": [{
            "node_id": "legacy-node",
            "node_level": 2,
            "node_name": "旧正文",
            "node_content": "## 定义\n\n旧课程仍可阅读。",
        }],
    }

    strict = inspect_course_acceptance(course, requested_profile="auto")
    compatible = inspect_course_acceptance(course, requested_profile="compatibility")

    assert strict["acceptance_profile"] == "standard"
    assert strict["status"] == "blocked"
    assert compatible["status"] == "degraded"
    assert compatible["ready_for_declared_scope"] is True
    assert _contract(compatible, "content")["status"] == "degraded"


def test_directory_scan_reports_invalid_json_without_recovery(tmp_path):
    valid_path = tmp_path / "course-ready.json"
    invalid_path = tmp_path / "course-broken.json"
    snapshot_path = tmp_path / "course-ready.v1.json"
    valid_path.write_text(json.dumps(_ready_course(), ensure_ascii=False), encoding="utf-8")
    invalid_payload = '{"course_id": "course-broken", invalid}'
    invalid_path.write_text(invalid_payload, encoding="utf-8")
    snapshot_path.write_text(json.dumps({"course_id": "snapshot"}), encoding="utf-8")

    report = scan_course_directory(tmp_path, requested_profile="standard")

    assert report["summary"]["total"] == 2
    assert report["summary"]["blocked"] == 2
    broken = next(item for item in report["reports"] if item["course_id"] == "course-broken")
    assert broken["storage_integrity"]["error_type"] == "JSONDecodeError"
    assert broken["blocking_issues"][0]["severity"] == "P0"
    assert invalid_path.read_text(encoding="utf-8") == invalid_payload
    assert snapshot_path.exists()


def test_single_course_api_uses_shared_checker(monkeypatch):
    async def course_or_404(_course_id):
        return _ready_course()

    monkeypatch.setattr(acceptance_router, "get_course_or_404", course_or_404)
    monkeypatch.setattr(
        acceptance_router,
        "read_version_context",
        lambda _reader, _course_id: _version_context(),
    )
    app = FastAPI()
    app.include_router(acceptance_router.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/courses/course-ready/acceptance-preflight")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "course_acceptance_preflight_v1"
    assert response.json()["status"] == "ready"


def test_directory_api_and_cli_share_scan_schema(monkeypatch, tmp_path):
    course_path = tmp_path / "course-ready.json"
    course_path.write_text(json.dumps(_ready_course(), ensure_ascii=False), encoding="utf-8")

    class VersionReader:
        def current_version_id(self, _course_id):
            return "cv_ready"

        def list_versions(self, _course_id):
            return [{"version_id": "cv_ready"}]

    monkeypatch.setattr(acceptance_router, "COURSES_DIR", str(tmp_path))
    monkeypatch.setattr(acceptance_router, "course_version_repository", VersionReader())
    app = FastAPI()
    app.include_router(acceptance_router.router, prefix="/api")
    response = TestClient(app).get("/api/course-acceptance/preflight")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "course_acceptance_scan_v1"
    assert response.json()["summary"]["ready"] == 1

    script = Path(__file__).resolve().parents[2] / "scripts" / "course_acceptance_preflight.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--courses-dir",
            str(tmp_path),
            "--compact",
            "--fail-on-blocked",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    cli_report = json.loads(completed.stdout)
    assert cli_report["schema_version"] == response.json()["schema_version"]
    assert cli_report["summary"]["blocked"] == 1
    assert completed.returncode == 2
