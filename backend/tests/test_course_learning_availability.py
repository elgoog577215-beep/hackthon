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


def test_practice_reports_active_question_generation_with_progress():
    course = _modern_course(questions=False)

    practice = project_practice_availability(
        course,
        scope="node",
        node_id="n1",
        scoped_question_count=0,
        question_bank_state={
            "job": {
                "job_id": "job-1",
                "status": "running",
                "progress": 55,
                "current_stage": "question_generation",
                "message": "正在生成题目",
            },
        },
    )

    assert practice == {
        "status": "generating",
        "reason_code": "question_generation_in_progress",
        "scope": "node",
        "node_id": "n1",
        "job_id": "job-1",
        "progress": 55,
        "current_stage": "question_generation",
        "message": "正在生成题目",
    }


def test_practice_distinguishes_review_validation_and_source_blocks():
    course = _modern_course(questions=False)
    base_bundle = {
        "items": [],
        "assessment_objectives": [{
            "node_id": "n1",
            "source_sufficiency": "sufficient",
            "generation_status": "ready",
        }],
    }

    review = project_practice_availability(
        course,
        scope="node",
        node_id="n1",
        scoped_question_count=0,
        question_bank_state={
            "bundle": {
                **base_bundle,
                "items": [{
                    "node_id": "n1",
                    "node_ids": ["n1"],
                    "generation_status": "waiting_review",
                }],
            },
        },
    )
    validation = project_practice_availability(
        course,
        scope="node",
        node_id="n1",
        scoped_question_count=0,
        question_bank_state={
            "bundle": {
                **base_bundle,
                "items": [{
                    "node_id": "n1",
                    "node_ids": ["n1"],
                    "generation_status": "validation_failed",
                }],
            },
        },
    )
    source = project_practice_availability(
        course,
        scope="node",
        node_id="n1",
        scoped_question_count=0,
        question_bank_state={
            "bundle": {
                **base_bundle,
                "assessment_objectives": [{
                    "node_id": "n1",
                    "source_sufficiency": "insufficient",
                    "generation_status": "candidate_only",
                }],
            },
        },
    )
    disabled = project_practice_availability(
        course,
        scope="node",
        node_id="n2",
        scoped_question_count=0,
        question_bank_state={"bundle": base_bundle},
    )

    assert review["reason_code"] == "question_review_pending"
    assert validation["reason_code"] == "question_validation_failed"
    assert source["reason_code"] == "question_source_insufficient"
    assert disabled["reason_code"] == "node_assessment_not_enabled"
