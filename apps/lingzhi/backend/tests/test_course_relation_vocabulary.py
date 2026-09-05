"""关系网词表必须没有兜底类型（需求 B2 的常驻检查）。

B2 只要一条常驻检查：确认关系网中不出现 `related` 之类兜底类型。为什么值得
单独锁：仓库里**确实存在**这样一个词表。`subject_ontology.py:307/311` 与
`subject_knowledge.py:840` 用的是学科库的旧五类词表
`{prerequisite, application, related, confusable, derives}`，其中 `related`
还是缺省值。那是学科库自己的域，与课程关系网无关——但两套词表同名字段、同名
概念，一旦有人"统一词表"，`related` 就会漏进课程关系网。

而漏进来的后果不是报错。`related` 没有别名、不在 `RELATION_TYPES` 里，会被
`_compile_relations` 整条丢进 `invalid_relation_candidates`：关系消失、编译成功、
没有任何提示。更糟的"修法"是给它加一条别名（`related -> equivalent_to`），把
一个无语义的类型折叠进一个有语义的类型——关系网会因此写入教学上并不成立的
等价断言。所以这里同时锁住三件事：词表里没有兜底类型、兜底类型被拒、以及
不允许有人用别名把它救回来。

`_compile_relations` 而不是批次校验器是这里的被测对象：A2 的
`test_course_relation_validation` 管的是生成期那道门，本文件管的是**任何**
来源（生成、重建、存量回灌、学科库串味）最终都要过的那道编译门。
"""

from __future__ import annotations

from course_knowledge_base import (
    RELATION_TYPES,
    _compile_relations,
    _normalize_name,
    validate_course_knowledge_base,
)

# 兜底/占位语义的类型名。共同点是不说明两个知识点之间到底是什么教学关系，
# 因此无法驱动任何下游决策（学习顺序、辨析、推导展示）。
CATCH_ALL_TYPES = {
    "related",
    "relates_to",
    "relation",
    "associated",
    "association",
    "linked",
    "connected",
    "other",
    "misc",
    "unknown",
    "general",
}

# 学科库 `subject_ontology.py` / `subject_knowledge.py` 在用的旧词表。
SUBJECT_LIBRARY_TYPES = {
    "prerequisite", "application", "related", "confusable", "derives",
}


def _points(*names: str) -> dict[str, dict]:
    return {
        _normalize_name(name): {"knowledge_id": f"ckp_{index}", "name": name}
        for index, name in enumerate(names)
    }


def _compile(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """跑一遍编译门，返回 (compiled, invalid)。"""
    invalid: list[dict] = []
    unresolved: list[dict] = []
    compiled = _compile_relations(
        "course-1",
        candidates,
        _points("知识点甲", "知识点乙"),
        {},
        invalid,
        unresolved,
    )
    return compiled, invalid


def _candidate(relation_type: str, **extra) -> dict:
    return {
        "source_name": "知识点甲",
        "target_name": "知识点乙",
        "relation_type": relation_type,
        "reason": "具体语义理由",
        **extra,
    }


# --- 词表本身 ---------------------------------------------------------------


def test_relation_vocabulary_contains_no_catch_all_type() -> None:
    """六类词表里不允许出现兜底类型 —— 这是 B2 的字面要求。"""
    leaked = sorted(RELATION_TYPES & CATCH_ALL_TYPES)

    assert leaked == [], f"关系词表里混入了兜底类型：{leaked}"


def test_relation_vocabulary_is_exactly_the_six_documented_types() -> None:
    """词表被扩充时必须显式改这条断言，防止悄悄长出第七类。"""
    assert RELATION_TYPES == {
        "prerequisite",
        "derives",
        "equivalent_to",
        "contrasts_with",
        "applies_to",
        "generalizes",
    }


# --- 兜底类型进不来 ---------------------------------------------------------


def test_every_catch_all_type_is_rejected_by_the_compiler() -> None:
    """逐个兜底类型都必须被编译门拒绝，而不是只挡住 `related` 一个。"""
    survived = []
    for name in sorted(CATCH_ALL_TYPES):
        compiled, invalid = _compile([_candidate(name)])
        if compiled or not invalid:
            survived.append(name)

    assert survived == [], f"这些兜底类型没有被拒：{survived}"


def test_rejected_catch_all_type_says_why() -> None:
    """拒绝原因必须点明是类型问题，否则排查时看不出是词表不合法。"""
    _, invalid = _compile([_candidate("related")])

    assert [item["rejection_reason"] for item in invalid] == ["invalid_relation_type"]


def test_no_alias_rescues_a_catch_all_type() -> None:
    """别名表不得把兜底类型折叠进某个有语义的类型。

    这是本文件最重要的一条：给 `related` 加别名是"修掉静默丢弃"最顺手的做法，
    但它会让关系网写入教学上不成立的断言（例如把"有点关系"变成"等价"）。
    """
    for name in sorted(CATCH_ALL_TYPES):
        compiled, _ = _compile([_candidate(name)])
        assert compiled == [], f"{name} 被别名救回成了 {compiled and compiled[0]['relation_type']}"


def test_subject_library_vocabulary_does_not_pass_the_course_gate() -> None:
    """学科库那套旧词表不能整体通行 —— 只有能映射到六类的才准过。

    `application`/`confusable` 有别名、`prerequisite`/`derives` 同名，这四个应当
    通过；`related` 必须被拒。断言写成"恰好拒掉 related"而不是"全部通过"，
    这样无论哪天有人统一词表都会在这里响。
    """
    rejected = set()
    for name in sorted(SUBJECT_LIBRARY_TYPES):
        compiled, invalid = _compile([_candidate(name, **_required_fields_for(name))])
        if not compiled:
            rejected.add(name)
            # 必须是因为"类型不合法"被拒，而不是因为缺字段 —— 否则这条断言
            # 会被一个无关的缺字段错误替代掉，测不到词表边界。
            assert invalid and invalid[0]["rejection_reason"] == "invalid_relation_type"

    assert rejected == {"related"}


def _required_fields_for(relation_type: str) -> dict:
    """补齐该类型（含别名解析后）的必填字段。

    `confusable` 会被别名解析成 `contrasts_with`，因此也需要 `distinction`。
    不补的话候选会因缺字段被拒，看起来像"类型被拒"，把断言测空。
    """
    resolved = {
        "application": "applies_to",
        "confusable": "contrasts_with",
        "equivalent": "equivalent_to",
        "generalization": "generalizes",
    }.get(relation_type, relation_type)
    if resolved == "derives":
        return {"derivation_steps": ["第一步", "第二步"]}
    if resolved == "contrasts_with":
        return {"distinction": "判别维度"}
    return {}


def test_aliases_only_ever_map_into_the_six_types() -> None:
    """别名的目标必须都在词表内，不能映射到一个不存在的类型。"""
    survivors = set()
    for name in sorted(SUBJECT_LIBRARY_TYPES | {"equivalent", "generalization"}):
        compiled, _ = _compile([_candidate(name, **_required_fields_for(name))])
        survivors.update(item["relation_type"] for item in compiled)

    assert survivors <= RELATION_TYPES


# --- 校验层也要报 -----------------------------------------------------------


def test_validator_flags_a_catch_all_type_as_critical() -> None:
    """万一兜底类型绕过编译门落进了存量知识库，校验层必须报 critical。"""
    base = {
        "knowledge_points": [
            {"knowledge_id": "ckp_0", "name": "知识点甲", "statement": "命题甲"},
            {"knowledge_id": "ckp_1", "name": "知识点乙", "statement": "命题乙"},
        ],
        "relations": [{
            "relation_id": "ckr_0",
            "source_knowledge_id": "ckp_0",
            "target_knowledge_id": "ckp_1",
            "relation_type": "related",
            "reason": "有关系",
        }],
    }

    report = validate_course_knowledge_base(base)

    assert any(
        item["code"] == "invalid_relation_type" and item["severity"] == "critical"
        for item in report["issues"]
    )


# --- 两条生成路径的 prompt 都不能教出兜底类型 -------------------------------


def _rebuild_prompt_text() -> str:
    from course_knowledge_rebuild import _rebuild_prompt

    return _rebuild_prompt(
        course_name="线性代数",
        sections=[{
            "section_id": "L2-1-1",
            "title": "向量空间",
            "content_blocks": [{"block_id": "b1", "markdown": "向量空间的定义。"}],
        }],
        existing_knowledge_names=["向量"],
    )


def _batch_prompt_text() -> str:
    from course_generation.prompts import CoursePromptComposer

    return CoursePromptComposer().build_teaching_plan_batch_v3_prompt(
        course_title="一次函数",
        positioning="能用一次函数刻画真实情境中的线性变化",
        batch_spec={"batch_id": "batch-1", "section_ids": ["L2-1-2"]},
        batch_sections=[{
            "node_id": "L2-1-2",
            "title": "一次函数的图像与性质",
            "learning_objective": "能够根据图像判断一次函数的变化趋势",
            "allowed_module_ids": ["core_explanation"],
        }],
        knowledge_registry=[{
            "knowledge_key": "K001",
            "name": "一次函数图像",
            "statement": "一次函数图像是一条直线。",
            "owner_node_id": "L2-1-2",
        }],
        section_identities=[{
            "node_id": "L2-1-2",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }],
        module_catalog=[{"module_id": "core_explanation", "label": "核心教学"}],
        skeleton_revision_id="skeleton-1",
    )


def test_batch_prompt_names_the_six_types_and_no_catch_all() -> None:
    """批次生成路径：六类逐个点名，且不出现兜底类型。"""
    batch = _batch_prompt_text()

    missing = sorted(name for name in RELATION_TYPES if f"`{name}`" not in batch)
    assert missing == [], f"批次 prompt 没点名这些类型：{missing}"
    assert not _mentions_catch_all(batch), "批次 prompt 里出现了兜底类型"


def test_rebuild_prompt_bans_the_catch_all_type() -> None:
    """重建是与批次生成并列的第二条生成路径，共用同一个编译门。

    两条路径任一条漏掉词表约束，产出的关系都会被静默丢弃。重建 prompt 里本来
    就写了"禁止 related"，这条断言把它钉住，防止后来的改写把它删掉。
    """
    rebuild = _rebuild_prompt_text()

    missing = sorted(name for name in RELATION_TYPES if name not in rebuild)
    assert missing == [], f"重建 prompt 没点名这些类型：{missing}"
    assert "禁止 related" in rebuild, "重建 prompt 不再显式禁止兜底类型"


def _mentions_catch_all(prompt: str) -> bool:
    """prompt 是否把某个兜底类型当作可选类型提出来。

    只在"类型词"的位置上匹配：`relation_type` 这类字段名本身含 `relation`，
    不能因为字段名命中就判失败，所以按带引号或反引号的取值形式匹配。
    """
    lowered = prompt.lower()
    return any(
        marker in lowered
        for name in CATCH_ALL_TYPES
        for marker in (f'"{name}"', f"`{name}`", f"'{name}'")
    )
