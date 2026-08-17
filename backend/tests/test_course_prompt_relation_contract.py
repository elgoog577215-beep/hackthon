"""批次 prompt 的关系契约必须与编译器的丢弃门一致（需求 A1）。

判据不是"prompt 里出现了六个词"，而是"prompt 让模型照抄的样例，本身能过
编译器那道门"。`_compile_relations` 对 `derives` 缺 `derivation_steps`、
`contrasts_with` 缺 `distinction` 的候选是整条丢弃的：样例若不带这两个字段，
模型学到的就是一种必定被丢弃的写法，而丢弃发生在编译期、没有任何提示。
"""

from __future__ import annotations

import json

from course_knowledge_base import RELATION_TYPES, _compile_relations, _normalize_name
from course_prompt_composer import CoursePromptComposer


def _batch_prompt() -> str:
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


def _example_relations(prompt: str) -> list[dict]:
    """把 JSON Schema 段落里的 knowledge_relations 样例取出来。

    prompt 是 f-string，花括号在输出里已经是单层，所以这里直接按数组边界截取
    并交给 json.loads —— 样例本身必须是合法 JSON，这一点也是断言的一部分。
    """
    start = prompt.index('"knowledge_relations": [')
    body = prompt[start + len('"knowledge_relations": '):]
    depth = 0
    for index, char in enumerate(body):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return json.loads(body[: index + 1])
    raise AssertionError("prompt 里的 knowledge_relations 样例没有闭合")


def test_constraints_name_every_relation_type() -> None:
    """六类关系必须逐个出现在约束里，模型才可能选对类型。"""
    prompt = _batch_prompt()
    constraints = prompt[prompt.index("## 约束"): prompt.index("## JSON Schema")]

    missing = sorted(name for name in RELATION_TYPES if f"`{name}`" not in constraints)

    assert missing == [], f"约束里没有说明这些关系类型：{missing}"


def test_constraints_state_the_two_required_fields() -> None:
    """带必填字段的两类关系必须在约束里点明字段名与缺失后果。"""
    constraints = _batch_prompt()
    constraints = constraints[
        constraints.index("## 约束"): constraints.index("## JSON Schema")
    ]

    assert "derivation_steps" in constraints
    assert "distinction" in constraints
    assert "丢弃" in constraints, "必须让模型知道缺字段会导致整条关系被丢弃"


def test_constraints_require_per_section_relation_attribution() -> None:
    """关系必须逐节写，不能攒到批次最后一节（G-1 真机实测出来的失败形态）。

    2026-08-17 两次真机（claude-opus-5，同一门课）都是这个分布：

        L2-1-1 0   L2-1-2 0   L2-1-3 5
        L2-2-1 0   L2-2-2 0   L2-2-3 7/6

    有产出的恰好是**每章最后一节**，两次都是——不是随机波动。批次按章切
    （`build_teaching_plan_batches` 优先在章边界断开），所以"每章最后一节"
    就是"每批次最后一节"。

    注意这**不是**校验层漏判：`teaching_batch:unrelated_relation` 已经要求
    每条关系至少连接本节新知识，所以写在最后一节的那些关系是合法的。
    问题在前面几节**一条都不写**——模型把关系攒到批次末尾统一处理了。

    也不是代码缺陷：3.12 那次（DeepSeek）6 节全部有产出，同一套代码同一门课。

    所以锁的是"prompt 里存在一条按小节分摊关系的要求"。
    """
    prompt = _batch_prompt()
    constraints = prompt[prompt.index("## 约束"): prompt.index("## JSON Schema")]

    assert "每一节都要各自写出" in constraints or "逐节" in constraints, (
        "约束里没有要求逐节写关系，模型会把整批关系攒到最后一节"
    )
    assert "最后一节" in constraints, "必须点名'攒到最后一节'这个具体失败形态"


def test_constraints_do_not_license_an_empty_relation_set() -> None:
    """"某一类没有"不能被读成"整节没有关系"。

    原文"本节只有两三个知识点时没有这几类是正常的"紧跟在"留空、宁缺毋滥"之后，
    连起来读就是一句"小节点少可以不写关系"的许可。三节零关系的实测结果与这句
    话的走向一致。这条断言确保覆盖要求不会被同段落里的宽免语句抵消。
    """
    prompt = _batch_prompt()
    constraints = prompt[prompt.index("## 约束"): prompt.index("## JSON Schema")]

    assert "不等于" in constraints, "缺少把'某类缺席'与'整节零关系'区分开的说明"


def test_example_covers_all_six_relation_types() -> None:
    """JSON 样例必须覆盖全部六类——这是实验结论，不是设计偏好。

    lz-web-search 做了六次真实生成对照，同主题同规模下唯一变量是样例覆盖的
    类数，产出类数随之变化：

        样例 1 类 -> 产出 1 类（修复前）
        样例 4 类 -> 产出 3 类（74b83906，FAIL）
        样例 6 类 -> 产出 4 类（PASS，验收线 >= 4）

    也就是说**模型跟 JSON 样例走，不跟散文枚举走**：`74b83906` 已经在约束里
    点名了六类，但样例只给四类，样例外的两类在四次运行中一次都没出现过。
    `generalizes` 尤其明显——不在样例时 0/4，补进样例后立刻出现。

    所以这条断言锁的是"六类都在样例里"，比 `>= 4` 更严：退回 4 类会让真实
    产出掉回 3 类，而验收线是 4。
    """
    types = {item.get("relation_type") for item in _example_relations(_batch_prompt())}

    missing = sorted(RELATION_TYPES - types)
    assert missing == [], f"样例缺这些类型，实测会导致模型不产出它们：{missing}"
    assert types <= RELATION_TYPES, f"样例用了不存在的类型：{sorted(types - RELATION_TYPES)}"


def test_every_example_relation_survives_the_compiler_gate() -> None:
    """真正的判据：照抄样例的输出不会被 `_compile_relations` 丢弃。"""
    examples = _example_relations(_batch_prompt())
    # 计划层会把 source_key/target_key 换成名字，编译器按名字解析。
    names = {
        key: f"知识点{key}"
        for item in examples
        for key in (item["source_key"], item["target_key"])
    }
    candidates = [
        {
            **{k: v for k, v in item.items() if k not in {"source_key", "target_key"}},
            "source_name": names[item["source_key"]],
            "target_name": names[item["target_key"]],
        }
        for item in examples
    ]
    point_by_name = {
        _normalize_name(name): {"knowledge_id": f"ckp_{key}", "name": name}
        for key, name in names.items()
    }
    invalid: list[dict] = []
    unresolved: list[dict] = []

    compiled = _compile_relations(
        "course-1", candidates, point_by_name, {}, invalid, unresolved,
    )

    assert [item["rejection_reason"] for item in invalid] == []
    assert unresolved == []
    assert len(compiled) == len(examples)


# --- 三类"实测从未产出"的关系需要触发引导（A1 真机验收后补） -----------------
#
# lz-web-search 用 2 小节课程实跑对照：非前置关系 0 -> 8 条，出现类型数 1/6 ->
# 3/6，prompt 修复确实生效。但 equivalent_to / contrasts_with / generalizes
# 三类**一条都没出现**。样本太小是可能原因之一，但另一个可能是：prompt 只说了
# 每类"是什么"，没说"什么时候该去找一条"。定义能让模型在已经想到关系时选对
# 类型，却不会促使它去**发现**关系。
#
# 所以补的是触发条件而不是更多定义，且必须是学科无关的可判断信号——写"数学里
# 可以用等价"对物理课没有意义。


def test_three_missing_types_have_explicit_triggers() -> None:
    """三类关系必须各有一条"什么时候该用"的触发引导，不能只有定义。"""
    prompt = _batch_prompt()
    constraints = prompt[prompt.index("## 约束"): prompt.index("## JSON Schema")]
    triggers = constraints[constraints.index("寻找关系时"):]

    for name in ("equivalent_to", "contrasts_with", "generalizes"):
        assert f"`{name}`" in triggers, f"{name} 缺少触发引导"


def test_triggers_are_actionable_signals_not_restatements() -> None:
    """触发条件必须指向可判断的信号，而不是把定义换个说法重写一遍。

    判据取三个具体锚点：`contrasts_with` 挂到 `confused_with` 字段（该字段本来
    就在易错点 schema 里，模型填了它就等于已经承认两者易混）；`equivalent_to`
    指向"同一对象的两种表述"；`generalizes` 指向特例/一般的包含判断。
    """
    prompt = _batch_prompt()
    triggers = prompt[prompt.index("寻找关系时"): prompt.index("## JSON Schema")]

    assert "confused_with" in triggers
    assert "两种表述" in triggers or "两种写法" in triggers
    assert "特例" in triggers


def test_triggers_do_not_invite_fabrication() -> None:
    """给了触发条件更要守住底线：不成立就不写，宁缺毋滥。"""
    prompt = _batch_prompt()
    triggers = prompt[prompt.index("寻找关系时"): prompt.index("## JSON Schema")]

    assert "不成立" in triggers or "不要为凑数" in triggers


# --- equivalent_to 的数据锚点触发（Gap A2） ---------------------------------
#
# 六次真实生成里 `equivalent_to` 一条都没出现。排查后**排除**了两个常见猜测：
#
# 1. "样例措辞太抽象"——不成立：实测六类样例中 `equivalent_to` 的 reason
#    是**最长最具体**的一条（24 字），比产出正常的 `contrasts_with`（6 字）
#    和 `prerequisite`（6 字）都具体。
# 2. "对称关系语义门槛高"——不成立：`contrasts_with` 同为对称关系
#    （`SYMMETRIC_RELATION_TYPES`），却能稳定产出。
#
# 真正的差别是**有没有数据锚点**：`contrasts_with` 挂在易错点的
# `confused_with` 字段上，模型填了那个字段就等于承认两者易混，触发条件来自
# 它自己的产出；而 `equivalent_to` 此前只有一句描述，没有任何字段能触发。
#
# 所以补的是同类锚点：`knowledge_type == "representation"`（schema 里本就
# 存在的取值）。同一对象的两个 representation 之间天然是等价关系。


def test_equivalent_to_has_a_data_anchored_trigger() -> None:
    """`equivalent_to` 必须挂到 schema 里真实存在的字段上，而不是只有描述。

    判据是锚点必须可判断：`representation` 是 `KNOWLEDGE_TYPES` 的合法取值，
    模型给某个知识点标了这个类型，就有据可依去找它的等价对象。
    """
    from course_knowledge_base import KNOWLEDGE_TYPES

    prompt = _batch_prompt()
    triggers = prompt[prompt.index("寻找关系时"): prompt.index("## JSON Schema")]

    assert "representation" in triggers
    assert "representation" in KNOWLEDGE_TYPES, "锚点必须是 schema 里真实存在的类型"
    assert "`equivalent_to`" in triggers


def test_equivalent_to_trigger_names_a_checkable_condition() -> None:
    """触发条件要能被判断，不能是"两者等价时就写等价"这种同义反复。"""
    prompt = _batch_prompt()
    triggers = prompt[prompt.index("寻找关系时"): prompt.index("## JSON Schema")]
    # 取 equivalent_to 那一条的上下文（前后各 300 字），不做负索引切片——
    # 负索引在关键词靠前时会绕回字符串末尾，断言就测到了别处。
    at = triggers.index("`equivalent_to`")
    section = triggers[max(0, at - 300): at + 300]

    # 必须给出"怎么认出来"的具体信号，而不是重复类型定义。
    assert "同一" in section, "要说清是同一对象/同一结论的不同表达"
    assert "换了写法" in section or "另一种写法" in section, "要给出可判断的识别标准"


def test_prompt_lists_every_legal_knowledge_type() -> None:
    """prompt 必须列出 `knowledge_type` 的全部合法取值。

    实测根因：prompt 从来没告诉模型这个字段能填什么，JSON 样例里只示范了
    `definition`。结果 qwen 生成时**发明了 `relationship`**（不在词表里），
    而 `representation` 一次都没出现——即使课程主题就是"一次函数的多种表示"、
    需求里明写了要标 representation。

    后果不只是"少一个类型"：`course_knowledge_base.py:177-178` 会把非法值
    **静默改写成 `definition`**，没有任何提示。所以模型填错、系统改错、
    没人知道。这与 A1 的教训同构——模型跟样例走，样例里没有的它不会用。
    """
    from course_knowledge_base import KNOWLEDGE_TYPES

    prompt = _batch_prompt()
    constraints = prompt[prompt.index("## 约束"): prompt.index("## JSON Schema")]

    missing = sorted(name for name in KNOWLEDGE_TYPES if name not in constraints)
    assert missing == [], f"约束里没有给出这些合法 knowledge_type：{missing}"


def test_skeleton_prompt_requires_splitting_representations() -> None:
    """骨架阶段必须要求把同一对象的多种表示拆成独立知识点。

    为什么必须在骨架阶段而不是批次阶段：实测三次批次阶段提示全部失败
    （representation 恒为 0），根因是骨架 prompt 写着"每节通常 2-4 个原子
    知识点"——**要求拆表示法与这条名额限制直接冲突**，两条矛盾指令下模型
    选择了不拆。所以拆分名额必须在分配名额的那一层给出。

    同 provider 对照实测（千问 qwen3.6-35b-a3b）：
        A 组（骨架未改）：representation 0
        B 组（骨架加规则）：representation 3 / 2（跑两次）
    """
    composer = CoursePromptComposer()
    prompt = composer.build_teaching_plan_skeleton_v3_prompt(
        course_title="一次函数",
        positioning="能用一次函数刻画线性变化",
        learning_objectives=["能在解析式与图像之间互相转换"],
        planning_context={"sections": [], "module_catalog": []},
    )

    assert "representation" in prompt, "骨架必须点名 representation 类型"
    assert "equivalent_to" in prompt, "要说清表示法之间用哪种关系相连"
    # 关键：必须明确"可以超过 4 个"，否则与既有名额约束冲突，模型会选择不拆。
    assert "超过 4 个" in prompt or "可以超过" in prompt
