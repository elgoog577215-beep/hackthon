from course_learning_availability import (
    project_course_learning_availability,
    project_practice_availability,
    resolve_learning_mode,
)


def _modern_course(*, questions=True):
    return {
        "course_id": "modern-course",
        "generation_schema_version": "course_generation_v5",
        "learning_asset_plan": {
            "schema_version": "learning_asset_plan_v1",
            "reading_only_degraded": False,
        },
        "learning_assets": {
            "questions": [{
                "revision_id": "qr1",
                "node_id": "n1",
                "practice_level": "mastery_check",
            }] if questions else [],
            "mastery_criteria": [{"revision_id": "mcr1", "node_id": "n1"}],
            "diagnostic_templates": [{"revision_id": "dr1", "node_id": "n1"}],
            "remediation_units": [{"revision_id": "rr1", "node_id": "n1"}],
            "validation_questions": [{"revision_id": "vr1", "node_id": "n1"}],
        },
    }


def test_explicit_reading_only_mode_is_not_inferred_from_question_count():
    course = _modern_course(questions=False)
    course["learning_asset_plan"]["reading_only_degraded"] = True

    availability = project_course_learning_availability(course)

    assert availability["mode"] == "reading_only"
    assert availability["capabilities"]["practice"] == {
        "status": "unavailable",
        "reason_code": "declared_reading_only",
    }


def test_modern_course_missing_questions_remains_standard_and_blocked():
    course = _modern_course(questions=False)

    availability = project_course_learning_availability(course)
    practice = project_practice_availability(
        course,
        scope="node",
        node_id="n1",
        scoped_question_count=0,
    )

    assert resolve_learning_mode(course) == "standard"
    assert availability["capabilities"]["practice"]["status"] == "blocked"
    assert practice["reason_code"] == "required_practice_missing"


def test_legacy_course_is_compatible_by_generation_structure_not_empty_assets():
    course = {
        "course_id": "legacy-course",
        "nodes": [{"node_id": "n1", "node_level": 2, "node_content": "旧正文"}],
    }

    availability = project_course_learning_availability(course)
    practice = project_practice_availability(
        course,
        scope="node",
        node_id="n1",
        scoped_question_count=0,
    )

    assert availability["mode"] == "compatibility"
    assert practice == {
        "status": "degraded",
        "reason_code": "legacy_reading_compatible",
        "scope": "node",
        "node_id": "n1",
    }


def test_standard_course_can_report_an_empty_local_scope_without_asset_failure():
    course = _modern_course()

    practice = project_practice_availability(
        course,
        scope="node",
        node_id="n2",
        scoped_question_count=0,
    )

    assert practice["status"] == "empty"
    assert practice["reason_code"] == "no_questions_in_scope"
