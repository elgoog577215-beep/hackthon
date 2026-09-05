from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from content_blocks import set_node_content_blocks


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "migrate_course_local_knowledge.py"
SPEC = importlib.util.spec_from_file_location("migrate_course_local_knowledge", SCRIPT_PATH)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def _course() -> dict:
    course = {
        "course_id": "course-1",
        "course_name": "动态数组",
        "knowledge_library_binding": {
            "library_id": "legacy-shared-library",
            "revision_id": "legacy-shared-revision",
        },
        "nodes": [{
            "node_id": "section-1",
            "node_level": 2,
            "node_name": "动态数组扩容",
            "learning_objective": "解释扩容触发和摊还成本",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "判断扩容时机并解释扩容成本。",
                "knowledge_points": [{
                    "name": "容量耗尽判定",
                    "statement": "元素数量等于容量时，下一次插入必须先扩容。",
                    "knowledge_type": "rule",
                    "conditions": ["使用连续存储且没有空闲槽位"],
                    "boundaries": ["存在空闲槽位时不触发扩容"],
                    "entry_reason": "这是理解扩容过程的入口。",
                    "capability_points": [{
                        "name": "判断扩容时机",
                        "observable_behavior": "根据长度和容量判断下一次插入是否扩容。",
                    }],
                    "mastery_criteria": [{
                        "name": "扩容判断达标",
                        "observable_performance": "独立判断多个边界案例并说明依据。",
                        "verification_method": "完成三个不同长度与容量组合的检查。",
                    }],
                    "relations": [{
                        "target_name": "倍增扩容的摊还成本",
                        "relation_type": "prerequisite",
                        "reason": "先确定何时扩容，才能分析累计复制成本。",
                    }],
                }, {
                    "name": "倍增扩容的摊还成本",
                    "statement": "几何倍增将少数线性复制成本分摊到一系列插入。",
                    "knowledge_type": "principle",
                    "conditions": ["扩容因子大于一并按几何级数增长"],
                    "boundaries": ["摊还常数成本不代表每次插入最坏为常数"],
                    "entry_reason": "用于解释动态数组平均插入效率。",
                    "capability_points": [{
                        "name": "分析摊还成本",
                        "observable_behavior": "根据扩容序列计算累计复制次数。",
                    }],
                    "mastery_criteria": [{
                        "name": "摊还分析达标",
                        "observable_performance": "独立区分单次最坏成本与摊还成本。",
                        "verification_method": "列出扩容序列并完成累计成本推导。",
                    }],
                }],
            }],
            "grounding_contract": {},
            "generation_status": "completed",
            "node_content": (
                "## 容量耗尽判定\n\n判断下一次插入是否需要扩容。\n\n"
                "## 倍增扩容的摊还成本\n\n分析一系列插入中的累计复制次数。"
            ),
        }],
        "learning_assets": {},
    }
    set_node_content_blocks(course["nodes"][0], course["nodes"][0]["node_content"])
    return course


def test_prepare_course_migration_builds_private_v2_knowledge_base():
    migrated, result = migration.prepare_course_migration(_course())

    assert migrated is not None
    assert result["status"] == "ready"
    assert migrated["course_knowledge_base"]["schema_version"] == "course_knowledge_base_v2"
    assert migrated["course_knowledge_base"]["lifecycle_status"] == "active"
    assert migrated["course_knowledge_map"]["binding_revision_id"] == (
        migrated["course_knowledge_base"]["revision_id"]
    )
    assert "knowledge_library_binding" not in migrated
    assert migrated["course_knowledge_migration"]["knowledge_scope"] == "current_course_only"


def test_run_migration_backs_up_before_writing_and_skips_invalid_files(tmp_path):
    data_dir = tmp_path / "data"
    courses_dir = data_dir / "courses"
    courses_dir.mkdir(parents=True)
    course_path = courses_dir / "course-1.json"
    course_path.write_text(json.dumps(_course(), ensure_ascii=False), encoding="utf-8")
    snapshot_path = courses_dir / "course-1.v1.json"
    snapshot_path.write_text('{"snapshot": true}', encoding="utf-8")
    invalid_path = courses_dir / "broken.json"
    invalid_path.write_text('{"broken": }', encoding="utf-8")

    report = migration.run_migration(
        data_dir=data_dir,
        backup_root=tmp_path / "backups",
        apply=True,
    )

    assert report["status_counts"]["migrated"] == 1
    assert report["status_counts"]["invalid"] == 1
    backup_dir = Path(report["backup_dir"])
    assert (backup_dir / "courses" / "course-1.json").exists()
    assert (backup_dir / "courses" / "broken.json").exists()
    assert json.loads(course_path.read_text(encoding="utf-8"))[
        "course_knowledge_base"
    ]["schema_version"] == "course_knowledge_base_v2"
    assert snapshot_path.read_text(encoding="utf-8") == '{"snapshot": true}'
    assert invalid_path.read_text(encoding="utf-8") == '{"broken": }'
