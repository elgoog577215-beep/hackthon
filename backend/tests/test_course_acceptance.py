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


def _node(node_id, parent_id, name, *, prerequisite_node_ids=None):
    return {
        "node_id": node_id,
        "parent_node_id": parent_id,
        "node_level": 2,
        "node_name": name,
        "node_content": f"## 核心概念\n\n{name} 的定义、条件和应用。",
        "learning_objective": f"能够解释并应用{name}",
        "key_points": [name, f"{name}的条件"],
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
