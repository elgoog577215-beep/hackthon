from copy import deepcopy

import pytest

from assessment_blueprint import compile_course_assessment_blueprint, slot_for
from question_knowledge_binding import knowledge_point_coverage
from routers.question_bank import _item_practice_levels_by_node, _question_source_revision


def atomic_course():
    return {
        "course_id": "atomic-course",
        "assessment_variant_count": 1,
        "course_name": "C语言",
        "nodes": [
            {
                "node_id": "types",
                "node_level": 2,
                "node_name": "类型",
                "key_points": ["整数除法", "赋值转换"],
                "node_content": "整数除法先计算整数结果，再把该结果转换为赋值目标类型。" * 8,
            }
        ],
        "course_knowledge_base": {
            "lifecycle_status": "active",
            "revision_id": "baseline-1",
            "knowledge_points": [
                {
                    "knowledge_id": key,
                    "revision_id": key + "-v1",
                    "status": "active",
                    "granularity_status": "atomic",
                    "section_refs": ["types"],
                    "name": name,
                    "statement": statement,
                    "meta_question": question,
                    "conditions": ["C17，操作数为int且除数不为零"],
                    "source_refs": ["source-1"],
                }
                for key, name, statement, question in [
                    ("division", "整数除法", "整数除法截去小数部分", "5/2的结果是什么？"),
                    ("conversion", "赋值转换", "转为double不能恢复已截去的小数", "double x=5/2能恢复小数吗？"),
                ]
            ],
            "sources": [{"source_id": "source-1", "text": "C17课程复核材料"}],
            "relations": [],
        },
    }


def _atomic_model():
    from backend.tests.test_assessment_generation_orchestrator import RepairingModel

    class ReviewedAtomicModel(RepairingModel):
        async def generate_candidate(self, context):
            candidate = await super().generate_candidate(context)
            candidate["question_spec"]["stimulus"]["rendered_text"] = (
                "某封闭系统的一次过程记录为Q=20 kJ、W=8 kJ。判断该过程的能量交换方向。"
            )
            return candidate

        async def evaluate_candidate(self, *args, **kwargs):
            kwargs.pop("call_policy", None)
            report = await super().evaluate_candidate(*args, **kwargs)
            from question_evidence_guard import CHECKS
            report["evidence_checks"] = {key: True for key in CHECKS}
            spec, independent, objective, slot = args
            report["review_witness"] = {
                "option_audit": [{"option_id": o["id"], "meaning": o.get("text") or o.get("label"),
                    "is_correct": o["id"] == independent["answer"],
                    "reason": "Q为正表示吸热，W为正表示对外做功，按题面符号逐项核对。"} for o in spec["options"]],
                "observation_test": {"target_statement": objective["knowledge"][0], "observed_quantity": "能量交换方向",
                    "public_anchor": "Q=20", "incorrect_rule": "把热量与功的正号约定反转",
                    "correct_prediction": "系统吸热且对外做功", "incorrect_prediction": "系统放热且外界对系统做功",
                    "trace": "题面Q和W均为正；正号约定反转时两个方向均反转。"},
                "unsupported_assumptions": [],
            }
            return report

    return ReviewedAtomicModel()


def test_atomic_plan_has_one_exact_target_per_point_instead_of_three_chapter_slots():
    course = atomic_course()
    blueprint = compile_course_assessment_blueprint(course)
    slots = blueprint["nodes"][0]["slots"]
    assert len(slots) == 2
    assert {tuple(s["primary_knowledge_ids"]) for s in slots} == {("division",), ("conversion",)}
    assert len({s["generation_key"] for s in slots}) == 2
    for slot in slots:
        assert slot_for(blueprint, "types", slot["generation_key"]) == slot
        assert slot["knowledge_baseline_revision"] == "baseline-1"
        assert slot["assessment_purpose"] == "atomic_check"


def test_atomic_plan_ignores_candidates_and_does_not_fall_back_to_broad_slots():
    course = atomic_course()
    course["course_knowledge_base"]["knowledge_points"][0]["status"] = "candidate"
    slots = compile_course_assessment_blueprint(course)["nodes"][0]["slots"]
    assert len(slots) == 1
    assert slots[0]["primary_knowledge_ids"] == ["conversion"]


def test_question_source_snapshot_detects_knowledge_revision_change():
    course = atomic_course()
    before = _question_source_revision(course)
    course["course_knowledge_base"]["knowledge_points"][0]["revision_id"] = "division-v2"
    assert _question_source_revision(course) != before


def test_item_rebuild_selects_exact_atomic_slot():
    item = {
        "revision_id": "q1",
        "node_id": "types",
        "practice_levels": ["concept_check"],
        "generation_key": "atomic-division",
    }
    assert _item_practice_levels_by_node({"items": [item]}, revision_ids=["q1"]) == {"types": ["atomic-division"]}


def test_coverage_distinguishes_current_approved_evidence_from_mentions():
    course = atomic_course()
    items = [{"item_id": "q1", "course_knowledge_refs": ["division", "conversion"], "lifecycle_status": "candidate"}]
    report = knowledge_point_coverage(course, items)
    assert report["covered_knowledge_point_count"] == 2
    assert report["assessable_knowledge_point_count"] == 0


def test_old_question_keeps_authored_revision_when_student_starts_after_tree_edit():
    from knowledge_mastery import freeze_knowledge_refs

    course = atomic_course()
    slot = compile_course_assessment_blueprint(course)["nodes"][0]["slots"][0]
    task = {**slot, "concept_ids": slot["primary_knowledge_ids"]}
    course["course_knowledge_base"]["knowledge_points"][0]["revision_id"] = "division-v2"
    assert freeze_knowledge_refs(course["course_knowledge_base"], task) == {"division": "division-v1"}


def test_atomic_bank_does_not_invent_unrequested_template_questions():
    from question_bank import build_question_bank

    course = atomic_course()
    assert build_question_bank(course)["items"] == []


@pytest.mark.asyncio
async def test_orchestrator_uses_each_target_and_resumes_only_requested_slot(monkeypatch):
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from knowledge_assessment import slot_key

    course = atomic_course()
    course["generation_request"] = {"web_question_enrichment": {"mode": "off"}}
    seen = []
    events = []
    runner = AssessmentGenerationOrchestrator(model=object())

    async def generate(**kwargs):
        objective = kwargs["objective"]
        seen.append(objective["knowledge"])
        return (
            "concept_check",
            {"prompt": objective["objective"]},
            {"practice_level": "concept_check", "final_decision": "publish"},
            None,
        )

    monkeypatch.setattr(runner, "_generate_slot_contract", generate)

    async def completed(event):
        events.append(event)

    prepared = await runner.prepare_course(course, on_chapter_complete=completed)
    keys = [slot_key(s) for s in prepared["_course_assessment_blueprint"]["nodes"][0]["slots"]]
    assert seen == [["整数除法截去小数部分"], ["转为double不能恢复已截去的小数"]]
    assert set(prepared["_assessment_generated_contracts"]["types"]) == set(keys)
    assert events[0]["passed"] is True
    assert set(events[0]["settled_practice_levels"]) == set(keys)
    seen.clear()
    retry = await runner.prepare_course(course, practice_levels_by_node={"types": [keys[1]]})
    assert seen == [["转为double不能恢复已截去的小数"]]
    assert retry["_assessment_generation_audit"]["planned_item_count"] == 1


@pytest.mark.asyncio
async def test_model_reviewed_single_point_waits_for_facts_and_adds_no_profile_evidence():
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from backend.tests.test_assessment_generation_orchestrator import _course
    from knowledge_mastery import build_knowledge_profile
    from question_bank import approved_formal_tasks, build_question_bank

    course = _course()
    course["assessment_variant_count"] = 1
    course["course_knowledge_base"] = deepcopy(atomic_course()["course_knowledge_base"])
    point = course["course_knowledge_base"]["knowledge_points"][0]
    point.update(
        section_refs=["thermo-1"],
        statement="系统吸热时Q取正，对外做功时W取正。",
        meta_question="识别吸热与做功的正负号约定",
        name="热量和功的符号",
    )
    course["course_knowledge_base"]["knowledge_points"] = [point]
    prepared = await AssessmentGenerationOrchestrator(model=_atomic_model()).prepare_course(course)
    bank = build_question_bank(prepared)
    assert len(bank["items"]) == 1
    tasks = approved_formal_tasks(bank)
    assert tasks == []
    item = bank['items'][0]
    assert item['lifecycle_status'] == 'needs_review'
    assert 'facts_unverified' in item['risk_flags']
    assert item['primary_knowledge_ids'] == ['division']
    assert item['knowledge_revision_refs'] == {'division': 'division-v1'}
    profile = build_knowledge_profile(
        course["course_knowledge_base"],
        course_id=course["course_id"],
        course_version_id="cv1",
        user_id="u",
        attempts=[],
        events=[],
    )
    assert profile["summary"]["assessed_count"] == 0
    assert profile["nodes"][0]["assessment_count"] == 0
    assert profile["nodes"][0]["independent_count"] == 0


def pilot_course():
    from knowledge_first import compile_tree, material

    package = material()
    assignments = {
        p["key"]: f"{topic}-{i // 6}" for topic, b in package["bundles"].items() for i, p in enumerate(b["points"])
    }
    tree = compile_tree(package, {"assignments": assignments})
    tree["status"] = "accepted"
    return {
        "course_id": "pilot-test",
        "assessment_variant_count": 1,
        "course_name": "C17程序设计",
        "course_knowledge_base": tree,
        "nodes": [
            {
                "node_id": t,
                "node_name": b["title"],
                "node_level": 2,
                "node_content": "本讲以已采用的知识基线和课程来源为依据，检查规则、条件和适用边界。",
            }
            for t, b in package["bundles"].items()
        ],
    }


def test_real_c17_package_plans_all_49_points_and_supports_raw_adopted_profile():
    from knowledge_mastery import build_knowledge_profile

    course = pilot_course()
    blueprint = compile_course_assessment_blueprint(course)
    assert [len(n["slots"]) for n in blueprint["nodes"]] == [16, 12, 21]
    assert blueprint["unplanned_knowledge_ids"] == []
    assert len({s["generation_key"] for n in blueprint["nodes"] for s in n["slots"]}) == 49
    profile = build_knowledge_profile(
        course["course_knowledge_base"],
        course_id="pilot-test",
        course_version_id="v1",
        user_id="u1",
        attempts=[],
        events=[],
    )
    assert profile["summary"]["total_count"] == 49


def test_atomic_student_projection_preserves_multiple_same_level_tasks(monkeypatch):
    import learning_assets
    from routers.question_bank import _merge_approved_question_assets

    course = pilot_course()
    ids = [p["knowledge_id"] for p in course["course_knowledge_base"]["knowledge_points"][:2]]
    tasks = [
        {
            "revision_id": f"qr-{i}",
            "question_id": f"q-{i}",
            "node_id": "types",
            "concept_ids": [kid],
            "course_knowledge_refs": [kid],
            "generation_key": f"slot-{i}",
            "assessment_binding_schema": "atomic_assessment_v1",
            "primary_knowledge_ids": [kid],
            "practice_level": "concept_check",
            "prompt": f"检查{i}",
            "quality_status": "passed",
            "answer_spec": {"type": "exact", "canonical_answer": "A"},
            "input_contract": {"mode": "choice"},
        }
        for i, kid in enumerate(ids)
    ]
    monkeypatch.setattr(learning_assets, "approved_formal_tasks", lambda *a, **kw: deepcopy(tasks))
    assets = learning_assets.compile_learning_assets(
        course, question_bank_bundle={"course_id": "pilot-test", "items": []}
    )
    projected = assets["assets"]["questions"]
    assert len(projected) == 2
    assert [q["concept_ids"] for q in projected] == [[kid] for kid in ids]
    assert [q["revision_id"] for q in projected] == [q["revision_id"] for q in tasks]
    assert assets["assets"]["validation_questions"] == []
    assert assets["assets"]["diagnostic_templates"] == []
    merged = _merge_approved_question_assets(projected, [{**tasks[0], "prompt": "更新第一题"}])
    assert len(merged) == 2
    assert merged[1]["revision_id"] == tasks[1]["revision_id"]


def test_missing_source_is_reported_as_unplanned_instead_of_generating():
    course = atomic_course()
    course["course_knowledge_base"]["knowledge_points"][0]["source_refs"] = ["missing"]
    blueprint = compile_course_assessment_blueprint(course)
    assert blueprint["unplanned_knowledge_ids"] == ["division"]
    assert len(blueprint["nodes"][0]["slots"]) == 1


def test_candidate_pilot_cannot_generate_formal_questions():
    course = pilot_course()
    course["course_knowledge_base"]["status"] = "candidate"
    with pytest.raises(ValueError, match="knowledge_baseline_not_adopted"):
        compile_course_assessment_blueprint(course)


def test_prerequisites_do_not_become_primary_targets_and_unknown_refs_are_ignored():
    course = atomic_course()
    course["course_knowledge_base"]["knowledge_points"][1]["prerequisite_ids"] = ["division", "conversion", "unknown"]
    slot = compile_course_assessment_blueprint(course)["nodes"][0]["slots"][1]
    assert slot["primary_knowledge_ids"] == ["conversion"]
    assert slot["prerequisite_knowledge_ids"] == ["division"]


def test_api_retains_atomic_fact_review_slots_and_checkpoints_exact_ids(monkeypatch, tmp_path):
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from backend.tests.test_assessment_generation_orchestrator import _course
    from backend.tests.test_question_bank_api import _client

    course = _course()
    course["assessment_variant_count"] = 1
    course["course_id"] = "course-api"
    course["course_knowledge_base"] = deepcopy(atomic_course()["course_knowledge_base"])
    point = course["course_knowledge_base"]["knowledge_points"][0]
    point.update(
        section_refs=["thermo-1"],
        statement="系统吸热时Q取正，对外做功时W取正。",
        meta_question="识别吸热与做功的正负号约定",
        name="热量和功的符号",
    )
    course["course_knowledge_base"]["knowledge_points"] = [point]
    course["course_knowledge_base"]["sources"][0]["text"] = point["statement"]
    runner = AssessmentGenerationOrchestrator(model=_atomic_model())
    client, repo = _client(monkeypatch, tmp_path, course=course, orchestrator=runner)
    response = client.post(
        "/api/courses/course-api/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={"request_id": "atomic-api-publication", "mode": "full"},
    )
    assert response.status_code == 202, response.json()
    job = client.get(response.json()["status_url"], headers={"X-User-Id": "teacher-1"}).json()
    assert job["status"] == "waiting_review", job
    bank = repo.load_bundle("course-api")
    assert len(bank['items']) == 1
    assert bank['items'][0]['lifecycle_status'] == 'needs_review'
    assert bank['items'][0]['primary_knowledge_ids'] == ['division']
    assert bank['items'][0]['knowledge_revision_refs'] == {'division': 'division-v1'}
    checkpoint = repo.course_storage.course["question_bank_chapter_rebuild"]
    assert checkpoint["published_practice_levels_by_node"]["thermo-1"] == [bank["items"][0]["generation_key"]]
    assert bank["generation_audit"]["planned_item_count"] == 1
    assert bank["generation_audit"]["published_item_count"] == 0
    assert bank["generation_audit"]["retained_review_item_count"] == 1
    tasks = repo.asset_repository.load_bundle("course-api")["assets"]["questions"]
    assert tasks == []


@pytest.mark.asyncio
async def test_partial_atomic_completion_preserves_successful_sibling(monkeypatch):
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from routers.question_bank import _settled_chapter_contracts

    course = atomic_course()
    runner = AssessmentGenerationOrchestrator(model=object())
    events = []

    async def generate(**kwargs):
        passed = kwargs["objective"]["knowledge"] == ["整数除法截去小数部分"]
        return (
            "concept_check",
            {"generation_status": "ready" if passed else "discarded"},
            {"practice_level": "concept_check", "final_decision": "publish" if passed else "discard"},
            None,
        )

    async def completed(event):
        events.append(event)

    monkeypatch.setattr(runner, "_generate_slot_contract", generate)
    await runner.prepare_course(course, on_chapter_complete=completed)
    contracts, audit = _settled_chapter_contracts(events[0])
    assert events[0]["passed"] is False
    assert len(contracts) == len(audit) == 1
    assert next(iter(contracts.values()))["primary_knowledge_ids"] == ["division"]
    assert events[0]["total_items"] == 2


@pytest.mark.asyncio
async def test_batch_generation_keeps_point_sources_separate(monkeypatch):
    from assessment_orchestrator import AssessmentGenerationOrchestrator

    contexts = []

    class BatchModel:
        async def generate_candidate_batch(self, batch, **kwargs):
            contexts.extend(deepcopy(batch))
            return {}

    runner = AssessmentGenerationOrchestrator(model=BatchModel())

    async def generate(**kwargs):
        return "concept_check", {}, {"practice_level": "concept_check", "final_decision": "publish"}, None

    monkeypatch.setattr(runner, "_generate_slot_contract", generate)
    await runner.prepare_course(atomic_course())
    assert len(contexts) == 2
    assert contexts[0]["objective"]["knowledge"] != contexts[1]["objective"]["knowledge"]
    assert {tuple(c["assessment_slot"]["primary_knowledge_ids"]) for c in contexts} == {("division",), ("conversion",)}
    assert all(c["content_evidence"][0]["reference_id"] == "source-1" for c in contexts)


def test_reconciliation_changes_one_atomic_slot_without_retiring_sibling():
    from backend.tests.test_question_bank_scoped_rebuild import _bundle, _item
    from question_bank import reconcile_scoped_question_bank

    first = {**_item("a", "node-a"), "generation_key": "target-a"}
    sibling = {**_item("b", "node-a"), "generation_key": "target-b"}
    replacement = {**_item("new-a", "node-a"), "generation_key": "target-a"}
    merged = reconcile_scoped_question_bank(
        _bundle([first, sibling]),
        _bundle([replacement]),
        node_ids=["node-a"],
        preserve_reviewed=False,
        practice_levels_by_node={"node-a": ["target-a"]},
    )
    current = {i["item_id"] for i in merged["items"] if i["lifecycle_status"] != "retired"}
    assert current == {"b", "new-a"}


def test_frozen_binding_rejects_mismatched_primary_ids():
    from knowledge_mastery import freeze_knowledge_refs

    slot = compile_course_assessment_blueprint(atomic_course())["nodes"][0]["slots"][0]
    assert freeze_knowledge_refs({}, {**slot, "concept_ids": ["conversion"]}) == {}


def test_publishing_questions_never_replaces_adopted_knowledge_with_asset_projection():
    from routers.question_bank import _course_with_rebuilt_assets

    course = pilot_course()
    projection = deepcopy(course["course_knowledge_base"])
    projection["lifecycle_status"] = "active"
    projection["course_id"] = course["course_id"]
    bank = {"bundle_revision_id": "bank-v1", "coverage": {}, "review_queue": {}, "web_enrichment": {}}
    assets = {
        "bundle_revision_id": "assets-v1",
        "plan": {},
        "quality_report": {},
        "assets": {"course_knowledge_base": [projection]},
    }
    result = _course_with_rebuilt_assets(course, bank, assets)
    assert result["course_knowledge_base"] == course["course_knowledge_base"]
    assert _question_source_revision(result) == _question_source_revision(course)


def test_legacy_derived_knowledge_does_not_conflict_with_its_own_question_publication():
    course = atomic_course()
    course.pop("course_knowledge_base")
    before = _question_source_revision(course)
    course["course_knowledge_base"] = {
        "lifecycle_status": "active",
        "revision_id": "derived-v1",
        "knowledge_points": [{"knowledge_id": "auto-derived-point"}],
    }
    assert _question_source_revision(course) == before


def test_legacy_question_identity_keeps_original_node_key_points():
    from course_versioning import stable_hash
    from question_bank import build_question_bank

    course = atomic_course()
    course.pop("course_knowledge_base")
    expected = stable_hash(
        {
            "course": course["course_id"],
            "node": "types",
            "level": "concept_check",
            "source": None,
            "objective": None,
            "knowledge": ["整数除法", "赋值转换"],
        },
        prefix="qbi_",
    )
    item = next(i for i in build_question_bank(course)["items"] if i.get("practice_levels") == ["concept_check"])
    assert item["item_id"] == expected
