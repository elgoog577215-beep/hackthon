"""K2: 多轮苏格拉底式引导。

三级提示是编译期冻结的静态内容，无法按学生实时回答动态追问。本节在既有
`/attempts/{id}/ai-support` 上挂载多轮引导（端点、证据折算、权限都已就绪）。

本文件锁住两件**可以自动化验证**的事：

1. **不泄题**——引导是运行时生成的，拿不到编译期那道门，所以每一轮都必须过
   泄漏筛查；被拦下时给安全兜底问题，不能重试到"说得含糊一点"就放行。
2. **轮次计入既有证据强度**（K3）——复用 `ai_support_level` 一套计量，
   不建第二套；问得越多证据越弱，引导不能成为刷掌握的后门。

**追问质量本身不在本文件的验证范围内。** "这个问题问得好不好"是教研判断，
不能由实现方自评。见 NOTES_TO_OWNER.md。
"""

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import learning_events
from practice_attempts import PracticeAttemptRepository, evidence_strength
from routers import practice as practice_router
from socratic_guidance import (
    MAX_ROUNDS,
    SocraticGuide,
    screen_guidance_turn,
    support_level_for_round,
)


class MemoryStorage:
    def __init__(self):
        self.data = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


def _course():
    return {
        "course_id": "c1",
        "course_name": "线性代数",
        "current_course_version_id": "cv1",
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "二次函数",
            "learning_objective": "能够求二次函数的最小值",
            "node_content": "二次函数可以通过配方求极值。",
        }],
        "learning_assets": {
            "questions": [{
                "asset_id": "q1",
                "revision_id": "qr1",
                "node_id": "n1",
                "objective_id": "lo_placeholder",
                "objective_revision_id": "lor_placeholder",
                "question_type": "short_answer",
                "prompt": "求函数 f(x)=x^2-4x+3 的最小值，并写出推导过程。",
                "answer_spec": {
                    "type": "rubric",
                    "correct_answer": "最小值为 -1",
                    "criteria": ["完成配方", "读出顶点", "得出最小值"],
                    "pass_score": 70,
                },
            }],
            "mastery_criteria": [],
            "checklist": [],
            "misconceptions": [],
            "final_assessment": [],
        },
    }


def _question():
    return {
        "prompt": "求函数 f(x)=x^2-4x+3 的最小值，并写出推导过程。",
        "question_type": "short_answer",
        "answer_spec": {
            "type": "rubric",
            "correct_answer": "最小值为 -1",
            "criteria": ["完成配方", "读出顶点", "得出最小值"],
            "solution_spec": {
                "final_answer": "最小值为 -1",
                "steps": [
                    {"step_id": "s1", "action": "把 f(x)=x^2-4x+3 配方为 (x-2)^2-1"},
                    {"step_id": "s2", "action": "读出顶点坐标 (2,-1)"},
                    {"step_id": "s3", "action": "由开口向上得最小值为 -1"},
                ],
            },
        },
    }


# --- 泄漏筛查 ----------------------------------------------------------------


def test_a_genuine_probing_question_passes_screening():
    """正常的苏格拉底式追问必须放行，否则功能等于没有。"""
    screening = screen_guidance_turn(
        {
            "question": "你刚才说“配方”，那配方之后常数项去哪了？",
            "focus": "检查学习者是否理解配方的恒等变形",
            "closing": "",
        },
        _question(),
    )

    assert screening["safe"] is True


def test_a_turn_that_gives_the_answer_is_rejected():
    screening = screen_guidance_turn(
        {"question": "别绕了，最小值为 -1，你直接写上就行。", "focus": "", "closing": ""},
        _question(),
    )

    assert screening["safe"] is False
    assert screening["reason"] == "reveals_final_answer"


def test_a_turn_that_restates_a_reference_step_is_rejected():
    """复述参考解答的某一步＝替学生做了那一步，必须拦下。"""
    screening = screen_guidance_turn(
        {
            "question": "你把 f(x)=x^2-4x+3 配方为 (x-2)^2-1 了吗？",
            "focus": "",
            "closing": "",
        },
        _question(),
    )

    assert screening["safe"] is False
    assert screening["reason"] == "restates_reference_step"


def test_an_empty_turn_is_rejected():
    assert screen_guidance_turn(
        {"question": "", "focus": "", "closing": ""}, _question()
    )["safe"] is False


class _FakeGuide(SocraticGuide):
    def __init__(self, response):
        super().__init__()
        self.client = object()
        self._response = response

    async def _call_llm(self, prompt, **kwargs):
        self._last_prompt = prompt
        self._last_system_prompt = kwargs.get("system_prompt") or ""
        return self._response


@pytest.mark.asyncio
async def test_leaky_generation_is_replaced_by_a_safe_fallback_question():
    """模型想泄题时，学生看到的必须是安全兜底问题，且如实标为 screened。"""
    guide = _FakeGuide(
        '{"question":"最小值为 -1，抄下来吧。","focus":"","student_signal":"",'
        '"is_stuck":false,"closing":""}'
    )
    turn = await guide.next_turn(_question(), {}, [], "我卡住了")

    assert turn["status"] == "screened"
    assert turn["reason"] == "reveals_final_answer"
    assert "-1" not in turn["question"]
    # 兜底内容仍然是一个问题，而不是答案。
    assert turn["question"].endswith("？") or "请把" in turn["question"]
    assert turn["generated"] is False


@pytest.mark.asyncio
async def test_safe_generation_is_returned_as_is():
    guide = _FakeGuide(
        '{"question":"你这一步用了什么条件？","focus":"检查条件",'
        '"student_signal":"我先配方","is_stuck":false,"closing":""}'
    )
    turn = await guide.next_turn(_question(), {}, [], "我先配方")

    assert turn["status"] == "ok"
    assert turn["question"] == "你这一步用了什么条件？"
    assert turn["generated"] is True


@pytest.mark.asyncio
async def test_unusable_model_output_degrades_instead_of_inventing_guidance():
    guide = _FakeGuide("这不是 JSON")
    turn = await guide.next_turn(_question(), {}, [], "我卡住了")

    assert turn["status"] == "degraded"
    assert turn["generated"] is False


@pytest.mark.asyncio
async def test_guidance_without_a_model_is_reported_unavailable():
    guide = SocraticGuide()
    guide.client = None
    turn = await guide.next_turn(_question(), {}, [], "我卡住了")

    assert turn["status"] == "unavailable"
    assert turn["generated"] is False


@pytest.mark.asyncio
async def test_system_prompt_forbids_answering_and_restating():
    guide = _FakeGuide(
        '{"question":"你这一步用了什么条件？","focus":"","student_signal":"",'
        '"is_stuck":false,"closing":""}'
    )
    await guide.next_turn(_question(), {}, [], "我卡住了")

    assert "绝不替他完成推理" in guide._last_system_prompt
    assert "复述参考解答的推导步骤" in guide._last_system_prompt
    assert "补写学生没有表达的推理" in guide._last_system_prompt


# --- 证据强度：复用 K3 口径，不建第二套 --------------------------------------


def test_rounds_escalate_support_level_gently_but_monotonically():
    """问得越多证据越弱；但一两次追问不该与"直接看脚手架"等价。"""
    levels = [support_level_for_round(n) for n in range(1, 7)]

    assert levels == [1, 1, 2, 2, 3, 3]
    assert levels == sorted(levels)


def test_guidance_weakens_evidence_through_the_existing_metric():
    """引导轮次通过既有 ai_support_level 影响证据强度，没有第二套计量。"""
    assert evidence_strength({"ai_support_level": 0}) == "independent"
    assert evidence_strength({"ai_support_level": 1}) == "lightly_supported"
    assert evidence_strength({"ai_support_level": 2}) == "supported"
    # 引导用满之后，证据不再足以支撑"独立掌握"。
    assert evidence_strength({"ai_support_level": 3}) == "scaffolded"


# --- 端点集成 ----------------------------------------------------------------


def _setup(monkeypatch, tmp_path, guide_response):
    repository = PracticeAttemptRepository(tmp_path)
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", MemoryStorage())

    course = _course()
    question = course["learning_assets"]["questions"][0]
    question["answer_spec"] = deepcopy(_question()["answer_spec"])

    async def fake_course(_course_id):
        return deepcopy(course)

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    monkeypatch.setattr(
        practice_router, "socratic_guide", _FakeGuide(guide_response)
    )

    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})
    created = client.post(
        "/api/courses/c1/practice/attempts", json={"question_revision_id": "qr1"}
    )
    return repository, client, created.json()["attempt"]


def test_ai_support_without_a_message_keeps_its_original_behaviour(
    monkeypatch, tmp_path
):
    """既有调用方不受影响：不带 message 就只记录"用过 AI 求助"。"""
    _, client, attempt = _setup(monkeypatch, tmp_path, "{}")

    response = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/ai-support",
        json={"expected_revision": 1, "level": 1, "summary": "打开 AI 老师"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "recorded"
    assert "guidance" not in body
    assert body["attempt"]["ai_support_level"] == 1


def test_a_guidance_round_returns_a_question_and_records_the_transcript(
    monkeypatch, tmp_path
):
    repository, client, attempt = _setup(
        monkeypatch,
        tmp_path,
        '{"question":"你这一步用了什么条件？","focus":"检查条件",'
        '"student_signal":"我先配方","is_stuck":false,"closing":""}',
    )

    response = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/ai-support",
        json={"expected_revision": 1, "level": 1, "message": "我先配方，然后就卡住了"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["guidance"]["question"] == "你这一步用了什么条件？"
    assert body["guidance"]["status"] == "ok"

    stored = repository.get("u1", "c1", attempt["attempt_id"])
    roles = [item["role"] for item in stored["guidance_turns"]]
    assert roles == ["student", "assistant"]
    # 学生原话与引导内容都留痕，便于教研人工评估追问质量。
    assert stored["guidance_turns"][0]["text"] == "我先配方，然后就卡住了"


def test_endpoint_never_returns_a_leaked_answer_to_the_student(
    monkeypatch, tmp_path
):
    """端到端：模型试图泄题，学生端拿到的必须是安全兜底。"""
    _, client, attempt = _setup(
        monkeypatch,
        tmp_path,
        '{"question":"最小值为 -1，直接写上。","focus":"","student_signal":"",'
        '"is_stuck":false,"closing":""}',
    )

    response = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/ai-support",
        json={"expected_revision": 1, "level": 1, "message": "答案是多少"},
    )

    body = response.json()
    assert body["guidance"]["status"] == "screened"
    assert "-1" not in body["guidance"]["question"]


def test_more_guidance_rounds_push_the_support_level_up(monkeypatch, tmp_path):
    """连续追问必须抬高 support level——引导不能变成刷掌握的后门。"""
    repository, client, attempt = _setup(
        monkeypatch,
        tmp_path,
        '{"question":"你怎么检查这一步？","focus":"","student_signal":"",'
        '"is_stuck":false,"closing":""}',
    )
    attempt_id = attempt["attempt_id"]

    levels = []
    for round_number in range(1, 6):
        current = repository.get("u1", "c1", attempt_id)
        client.post(
            f"/api/courses/c1/practice/attempts/{attempt_id}/ai-support",
            json={
                "expected_revision": current["revision"],
                "level": 1,
                "message": f"第 {round_number} 轮回答",
            },
        )
        levels.append(repository.get("u1", "c1", attempt_id)["ai_support_level"])

    assert levels[0] == 1
    assert levels[-1] == 3
    assert levels == sorted(levels)
    # 用满引导之后，这次作答不再算独立证据。
    assert evidence_strength(repository.get("u1", "c1", attempt_id)) == "scaffolded"


def test_guidance_rounds_are_capped(monkeypatch, tmp_path):
    repository, client, attempt = _setup(
        monkeypatch,
        tmp_path,
        '{"question":"你怎么检查这一步？","focus":"","student_signal":"",'
        '"is_stuck":false,"closing":""}',
    )
    attempt_id = attempt["attempt_id"]

    for round_number in range(MAX_ROUNDS):
        current = repository.get("u1", "c1", attempt_id)
        assert client.post(
            f"/api/courses/c1/practice/attempts/{attempt_id}/ai-support",
            json={
                "expected_revision": current["revision"],
                "level": 1,
                "message": f"第 {round_number} 轮",
            },
        ).status_code == 200

    current = repository.get("u1", "c1", attempt_id)
    response = client.post(
        f"/api/courses/c1/practice/attempts/{attempt_id}/ai-support",
        json={"expected_revision": current["revision"], "level": 1, "message": "再来一轮"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "guidance_round_limit_reached"


# --- K3：只有真正送达的引导才折算证据 ----------------------------------------


def test_undelivered_guidance_does_not_charge_support(monkeypatch, tmp_path):
    """模型不可用时学生拿到的是兜底套话，不能因此被判为"用过引导"。

    三种失败态（unavailable / degraded / screened）返回的是**同一句**兜底
    文本。若照样折算支持等级，就等于记录了一次从未发生的帮助——违反"不伪造
    证据"，还会让一次 provider 故障把诚实作答的学生推到 scaffolded。
    """
    repository, client, attempt = _setup(monkeypatch, tmp_path, "这不是 JSON")

    response = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/ai-support",
        json={"expected_revision": 1, "level": 1, "message": "我卡住了"},
    )

    assert response.status_code == 200
    assert response.json()["guidance"]["status"] == "degraded"
    stored = repository.get("u1", "c1", attempt["attempt_id"])
    # 仍然停留在调用方声明的等级，没有被引导轮次抬高。
    assert stored["ai_support_level"] == 1
    assert stored["guidance_turns"][1]["counted_as_support"] is False


def test_screened_guidance_does_not_charge_support(monkeypatch, tmp_path):
    """被泄漏筛查拦下也是我们的失败，不该由学生付代价。"""
    repository, client, attempt = _setup(
        monkeypatch,
        tmp_path,
        '{"question":"最小值为 -1，直接写上。","focus":"","student_signal":"",'
        '"is_stuck":false,"closing":""}',
    )

    client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/ai-support",
        json={"expected_revision": 1, "level": 1, "message": "答案是多少"},
    )

    stored = repository.get("u1", "c1", attempt["attempt_id"])
    assert stored["ai_support_level"] == 1
    assert stored["guidance_turns"][1]["counted_as_support"] is False


def test_undelivered_rounds_do_not_consume_the_round_budget(monkeypatch, tmp_path):
    """provider 故障不能把学生的提问额度耗光并锁死。"""
    repository, client, attempt = _setup(monkeypatch, tmp_path, "这不是 JSON")
    attempt_id = attempt["attempt_id"]

    for _ in range(MAX_ROUNDS + 2):
        current = repository.get("u1", "c1", attempt_id)
        response = client.post(
            f"/api/courses/c1/practice/attempts/{attempt_id}/ai-support",
            json={
                "expected_revision": current["revision"],
                "level": 1,
                "message": "我卡住了",
            },
        )
        # 从不因为失败轮次而被 409 锁死。
        assert response.status_code == 200

    assert repository.get("u1", "c1", attempt_id)["ai_support_level"] == 1


def test_delivered_guidance_still_charges_support(monkeypatch, tmp_path):
    """反向确认：真正送达的引导仍然照常折算，修复没有把 K3 关掉。"""
    repository, client, attempt = _setup(
        monkeypatch,
        tmp_path,
        '{"question":"你这一步用了什么条件？","focus":"","student_signal":"",'
        '"is_stuck":false,"closing":""}',
    )
    attempt_id = attempt["attempt_id"]

    for round_number in range(3):
        current = repository.get("u1", "c1", attempt_id)
        client.post(
            f"/api/courses/c1/practice/attempts/{attempt_id}/ai-support",
            json={
                "expected_revision": current["revision"],
                "level": 1,
                "message": f"第 {round_number} 轮",
            },
        )

    stored = repository.get("u1", "c1", attempt_id)
    assert stored["ai_support_level"] == 2
    assert stored["guidance_turns"][1]["counted_as_support"] is True


# --- 裸答案值泄漏（真机抽查发现的真实缺陷） ----------------------------------


def _bare_answer_question():
    """存的答案是「最小值为 -4」这个短语，但模型很可能只说出裸数字 -4。"""
    return {
        "prompt": "求函数 f(x)=x^2-6x+5 的最小值，并写出推导过程。",
        "question_type": "worked_solution",
        "answer_spec": {
            "type": "rubric",
            "correct_answer": "最小值为 -4",
            "solution_spec": {
                "final_answer": "最小值为 -4",
                "steps": [
                    {"step_id": "s1", "action": "把 f(x)=x^2-6x+5 配方为 (x-3)^2-4"},
                    {"step_id": "s2", "action": "读出顶点坐标 (3,-4)"},
                ],
            },
        },
    }


def test_bare_numeric_answer_is_caught_even_when_phrase_is_not():
    """真机对抗抽查复现出来的泄漏：学生硬要答案时模型说出了裸数字 -4。

    短语「最小值为 -4」在引导文本里找不到，而 hint_leakage 会跳过短于一个
    shingle 的答案（编译期这样取舍是对的，裸 "3"/"B" 与普通行文碰撞太容易）。
    运行时引导是另一回事：一两句针对特定学生现生成的话里出现 "-4"，压倒性
    地就是答案本身。
    """
    screening = screen_guidance_turn(
        {
            "question": "你现在最想直接知道的是那个数字（-4），但题目要求写出推导过程。",
            "focus": "",
            "closing": "",
        },
        _bare_answer_question(),
    )

    assert screening["safe"] is False
    assert screening["reason"] == "reveals_final_answer"
    assert screening["matched_value"] == "-4"


def test_numbers_from_the_prompt_are_not_mistaken_for_the_answer():
    """题面里的系数、步骤序号不能被误判为答案——误伤会让引导变得没法用。"""
    question = _bare_answer_question()
    for text in (
        "题目里的 x^2-6x+5，你先看 -6 这个系数在配方时怎么处理？",
        "请把第 2 步的依据写出来。",
        "你说配完之后常数项算错，能说说你配到哪一步吗？",
    ):
        screening = screen_guidance_turn(
            {"question": text, "focus": "", "closing": ""}, question
        )
        assert screening["safe"] is True, text


def test_answer_digit_boundary_avoids_substring_false_positives():
    """-4 不能在 -42 上误报，也不能在 14 里命中。"""
    question = _bare_answer_question()
    screening = screen_guidance_turn(
        {"question": "如果把常数项写成 -42，你怎么检查它对不对？", "focus": "", "closing": ""},
        question,
    )

    assert screening["safe"] is True


def test_unit_bearing_answer_value_is_also_caught():
    """带单位的答案（50 km/h）同样要拦下裸数值。"""
    question = {
        "prompt": "求全程平均速度。",
        "question_type": "numeric_response",
        "answer_spec": {
            "correct_answer": "50 km/h",
            "solution_spec": {"final_answer": "50 km/h", "steps": []},
        },
    }
    screening = screen_guidance_turn(
        {"question": "其实结果就是 50，你核对一下。", "focus": "", "closing": ""},
        question,
    )

    assert screening["safe"] is False
    assert screening["reason"] == "reveals_final_answer"
