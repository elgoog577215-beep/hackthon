from teacher_asset_readiness import (
    teacher_lesson_plan_readiness,
    teacher_lesson_ppt_asset_readiness,
    teacher_lesson_script_readiness,
)


def complete_lesson() -> dict:
    return {
        "working_revision_id": "plan-1",
        "source_state": "current",
        "revisions": [{
            "revision_id": "plan-1",
            "generation_source": "model",
            "quality_report": {"passed": True},
            "plan": {
                "schema_version": "course_teaching_plan_v3",
                "sections": [{
                    "node_id": "section-1",
                    "teaching_modules": [{"module_id": "explain"}],
                }],
            },
        }],
        "working_script_revision_id": "script-1",
        "script_revisions": [{
            "revision_id": "script-1",
            "source_lesson_plan_revision_id": "plan-1",
            "publication_eligible": True,
            "sections": [{
                "section_node_id": "section-1",
                "content": "完整讲义",
                "blocks": [{"block_id": "block-1"}],
            }],
        }],
    }


def test_readiness_requires_current_structurally_usable_assets():
    lesson = complete_lesson()
    plan = teacher_lesson_plan_readiness(lesson)
    script = teacher_lesson_script_readiness(lesson, plan_readiness=plan)
    ppt = teacher_lesson_ppt_asset_readiness(
        lesson,
        {
            "working_representation_id": "ppt-1",
            "source_lesson_plan_revision_id": "plan-1",
            "source_script_revision_id": "script-1",
            "source_state": "current",
        },
        plan_readiness=plan,
        script_readiness=script,
    )

    assert plan == {"ready": True, "unavailable_reason": ""}
    assert script == {"ready": True, "unavailable_reason": ""}
    assert ppt == {"ready": True, "unavailable_reason": ""}


def test_identifiers_do_not_make_incomplete_assets_ready():
    lesson = complete_lesson()
    lesson["revisions"][0]["plan"]["sections"] = []
    plan = teacher_lesson_plan_readiness(lesson)
    script = teacher_lesson_script_readiness(lesson, plan_readiness=plan)
    ppt = teacher_lesson_ppt_asset_readiness(
        lesson,
        {
            "working_representation_id": "ppt-1",
            "source_lesson_plan_revision_id": "plan-1",
            "source_script_revision_id": "script-1",
            "source_state": "current",
        },
        plan_readiness=plan,
        script_readiness=script,
    )

    assert plan == {"ready": False, "unavailable_reason": "content_incomplete"}
    assert script == {"ready": False, "unavailable_reason": "upstream_plan_not_ready"}
    assert ppt == {"ready": False, "unavailable_reason": "upstream_plan_not_ready"}
