#!/usr/bin/env python3
"""Generate and blindly review fixed, readable mini-course prompt outcomes.

This is a development-only founder review aid.  It compiles the production
content prompt for three connected calculus lessons and three connected
mechanical-design lessons, then uses the local Codex route to produce the
learner-facing Markdown.  Generated artifacts stay outside the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from codex_local_provider import CodexLocalProvider  # noqa: E402
from course_composition import attach_composition_to_plan  # noqa: E402
from course_design_contract import compile_course_design_contract  # noqa: E402
from course_difficulty import (  # noqa: E402
    assess_readiness,
    attach_difficulty_contracts_to_plan,
    compile_difficulty_profile,
    decide_adaptation,
)
from course_generation_workflow import build_course_generation_artifacts  # noqa: E402
from course_knowledge_base import compile_course_knowledge_base  # noqa: E402
from course_pedagogy import (  # noqa: E402
    attach_module_plans_to_plan,
    compile_subject_generation_template,
    resolve_pedagogy_profile,
)
from course_prompt_composer import (  # noqa: E402
    PROMPT_CONTRACT_VERSION,
    CoursePromptComposer,
)


def _knowledge(
    name: str,
    statement: str,
    *,
    knowledge_type: str = "concept",
    conditions: list[str] | None = None,
    boundaries: list[str] | None = None,
    misconception: str,
    repair: str,
    mastery: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "statement": statement,
        "knowledge_type": knowledge_type,
        "conditions": conditions or [],
        "boundaries": boundaries or [],
        "positive_examples": [],
        "counterexamples": [],
        "capability_points": [{
            "name": mastery,
            "observable_behavior": mastery,
            "required_evidence_types": ["practice_attempt"],
        }],
        "misconceptions": [{
            "name": misconception,
            "observable_error_pattern": misconception,
            "confused_with": "相邻但不同的判断对象",
            "discrimination": repair,
            "repair_strategy": repair,
        }],
        "mastery_criteria": [{
            "name": mastery,
            "observable_performance": mastery,
            "required_independence": "independent",
            "required_transfer": "variation",
            "verification_method": mastery,
            "required_evidence_types": ["practice_attempt"],
        }],
        "source_refs": [],
        "confidence": "medium",
    }


COURSES: dict[str, dict[str, Any]] = {
    "calculus": {
        "course_name": "从极限到微积分基本定理",
        "subject": "大学微积分",
        "audience": "掌握高中函数但第一次系统学习微积分的大学一年级学生",
        "requirements": (
            "用三个连续课时建立极限、导数与积分之间的逻辑链；重视定义、图像直觉、"
            "完整推理、反例和迁移，不把公式记忆当作理解。"
        ),
        "positioning": "让学生看见微积分核心对象如何由同一个极限思想连接起来",
        "final_outcome": "独立解释并证明一个简化版微积分基本定理，再用于判断一个变化率问题",
        "chapter": "极限如何连接局部变化与整体累积",
        "chapter_focus": "从精确定义进入局部线性化，再建立导数与积分的互逆关系",
        "course_spine": {
            "mode": "connected_examples",
            "title": "极限如何连接局部变化与整体累积",
            "central_question": "同一个极限思想怎样依次定义趋近、局部变化率和整体累积的变化率？",
            "fixed_facts": [],
            "allowed_variations": ["每节可选择最能暴露当前概念边界的新函数，但必须明确它是新例子"],
            "final_artifact": "一份从 ε-δ 定义到微积分基本定理的完整论证，并能处理一个净变化问题",
            "continuity_rule": "三节共享问题链而非同一数值案例；不得声称后节沿用了前节未产生的数据。",
            "required_closures": [
                {
                    "closure_id": "CALC-FTC-PROOF",
                    "requirement": "用连续性与绝对值估计给出微积分基本定理第一部分的非循环证明",
                    "target_node_id": "L2-1-3",
                    "evidence": "同时覆盖 h>0 与 h<0 的严格差商估计，不借用待证结论",
                },
                {
                    "closure_id": "CALC-NET-CHANGE-TRANSFER",
                    "requirement": "把基本定理迁移到不同于示范的净变化情境",
                    "target_node_id": "L2-1-3",
                    "evidence": "使用非零下限或会变号的新变化率，解释定积分的净变化含义",
                },
                {
                    "closure_id": "CALC-FTC-DEPENDENCY",
                    "requirement": "区分基本定理两部分的逻辑职责并交代第二部分所需桥梁",
                    "target_node_id": "L2-1-3",
                    "evidence": "明确命名零导数定理及其中值定理先修；本课未证明该桥梁时不得声称第二部分完全由前三节自足推出",
                },
                {
                    "closure_id": "CALC-DERIVATIVE-BOUNDARY",
                    "requirement": "学习者必须亲自判断连续但不可导的边界，不只阅读教师示例",
                    "target_node_id": "L2-1-2",
                    "evidence": "任务中比较绝对值函数尖点处的左右差商，并据此判断导数不存在",
                },
            ],
        },
        "sections": [
            {
                "title": "极限：把无限趋近写成可检验的承诺",
                "objective": "能解释 ε-δ 定义的量词顺序，并为简单线性函数独立构造和验证 δ(ε)",
                "scope": "只讨论一点处有限函数极限；不提前讲连续性定理、数列极限或洛必达法则",
                "assessment": ["证明 lim(x→2)(3x+1)=7，并用反例说明点值不能代替极限"],
                "spine_progression": {
                    "role": "introduce",
                    "action": "把直觉性的趋近改写成可由任意精度检验的邻域承诺",
                    "student_artifact": "一份量词顺序正确且完成正向验证的 ε-δ 证明",
                    "handoff": "已经掌握用极限定义新对象所需的精度—邻域推理",
                    "variation": "",
                },
                "knowledge": [
                    _knowledge(
                        "一点处有限函数极限",
                        "极限描述去心邻域中的函数值趋近，不要求点值存在或等于极限。",
                        knowledge_type="definition",
                        conditions=["趋近点是定义域的聚点"],
                        boundaries=["有限次代入或观察不能证明极限", "点值不决定极限"],
                        misconception="用 f(a) 或有限张数值表直接宣布极限",
                        repair="改变点值并比较去心邻域；再检查任意 ε 是否都能得到邻域保证",
                        mastery="区分点值、有限观察与邻域保证",
                    ),
                    _knowledge(
                        "函数极限的 ε-δ 定义",
                        "任意 ε>0 都对应某个 δ>0，使 0<|x-a|<δ 时 |f(x)-L|<ε。",
                        knowledge_type="definition",
                        conditions=["δ 可以依赖 ε，但不能依赖某个具体 x"],
                        boundaries=["量词顺序不能颠倒", "候选 δ 必须正向代回验证"],
                        misconception="从目标不等式反推一个 δ 后不做正向验证",
                        repair="写清任取 ε、选择 δ、任取满足邻域条件的 x、推出误差界四步",
                        mastery="独立构造并正向验证 δ(ε)",
                    ),
                ],
            },
            {
                "title": "导数：最佳局部线性近似，而不只是一条公式",
                "objective": "能从差商极限得到导数，并用局部线性化解释近似误差和可导边界",
                "scope": "只研究一元函数一点处导数和一阶局部线性化；不展开多元微分或高阶泰勒公式",
                "assessment": ["由定义求 x² 在 a 点的导数并完成线性化误差检查，再比较绝对值函数尖点处的左右差商"],
                "spine_progression": {
                    "role": "advance",
                    "action": "把极限推理用于差商，并由导数得到可评价误差的局部线性模型",
                    "student_artifact": "由定义求导并评价一次局部线性近似误差的记录",
                    "handoff": "已经能把短区间上的变化写成差商极限，并解释其局部意义",
                    "variation": "改用二次函数研究局部变化，并用绝对值函数尖点检验可导边界",
                    "closure_ids": ["CALC-DERIVATIVE-BOUNDARY"],
                },
                "knowledge": [
                    _knowledge(
                        "导数的差商极限",
                        "导数是增量比在步长趋于零时的极限，存在时给出一点处瞬时变化率。",
                        knowledge_type="definition",
                        conditions=["左右差商极限存在且相等"],
                        boundaries=["连续不保证可导", "导数不是取 h=0 后的比值"],
                        misconception="把 h 直接代成 0，或只计算右差商",
                        repair="保持 h≠0，化简后再取极限，并分别检查必要的左右行为",
                        mastery="由定义求导并判断不可导情形",
                    ),
                    _knowledge(
                        "一阶局部线性化",
                        "可导函数在一点附近可由切线作一阶近似，误差相对位移是高阶小量。",
                        knowledge_type="principle",
                        conditions=["函数在展开点可导", "位移足够小"],
                        boundaries=["远离展开点时误差可能迅速增大", "尖点处不能直接使用"],
                        misconception="把局部近似写成全局恒等式",
                        repair="明确近似中心、位移大小并用原函数值检查误差",
                        mastery="选择展开点完成估算并评价误差",
                    ),
                ],
            },
            {
                "title": "微积分基本定理：为什么累积量的变化率回到原函数",
                "objective": "能用连续性和夹逼思想解释累积函数的导数，并区分定理两部分的职责",
                "scope": "只处理连续函数的定积分与累积函数；不展开黎曼可积性的一般判据",
                "assessment": ["证明累积函数求导的一般结论，再用会变号的新变化率解决一个非零下限净变化问题"],
                "spine_progression": {
                    "role": "synthesize",
                    "action": "把短区间积分平均写成差商极限，连接导数与积分并完成全课论证",
                    "student_artifact": "微积分基本定理第一部分的非循环证明与一个净变化应用",
                    "handoff": "完成全课最终论证",
                    "variation": "使用连续函数的累积量新例子检验前两节的极限推理",
                    "closure_ids": [
                        "CALC-FTC-PROOF",
                        "CALC-NET-CHANGE-TRANSFER",
                        "CALC-FTC-DEPENDENCY",
                    ],
                },
                "knowledge": [
                    _knowledge(
                        "累积函数的差商",
                        "累积函数的增量等于短区间上的积分，其差商是该区间函数值的平均。",
                        knowledge_type="derivation",
                        conditions=["被积函数在考察点附近连续"],
                        boundaries=["区间方向改变时符号随之改变"],
                        misconception="直接把积分号消掉而不解释短区间平均值为何趋近点值",
                        repair="先写增量积分，再除以 h，最后用连续性夹逼平均值",
                        mastery="从累积函数差商推导其导数",
                    ),
                    _knowledge(
                        "微积分基本定理的两部分",
                        "第一部分把连续函数变成一个原函数，第二部分用任一原函数计算定积分。",
                        knowledge_type="theorem",
                        conditions=["第一部分要求被积函数连续", "第二部分要求存在满足条件的原函数"],
                        boundaries=["定理不是不带条件的符号消去规则"],
                        misconception="混淆累积函数求导与用原函数算定积分的逻辑方向",
                        repair="分别标出输入对象、输出结论和所用条件，再连接两部分",
                        mastery="解释、证明简化情形并用于净变化问题",
                    ),
                ],
            },
        ],
    },
    "mechanical": {
        "course_name": "小型传动轴系设计：从需求到验证",
        "subject": "机械设计",
        "audience": "学过理论力学和材料力学、第一次完成机械部件综合设计的本科生",
        "requirements": (
            "围绕一套小型带传动轴系完成需求分解、载荷路径、轴的初步尺寸、轴承选择和"
            "验证；必须比较方案、暴露假设和失效模式，不能把查公式当作设计。"
        ),
        "positioning": "把力学计算组织成可审查、可迭代的工程设计决策",
        "final_outcome": "提交一页轴系设计评审单，说明需求、模型、方案取舍、关键计算和验证边界",
        "chapter": "一条轴系怎样从任务要求走到可验证方案",
        "chapter_focus": "先冻结需求与失效准则，再建模载荷路径，最后完成部件匹配和方案复核",
        "course_spine": {
            "mode": "shared_anchor",
            "title": "4 kW 小型带传动轴系教学设计案",
            "central_question": "怎样让同一套轴系的每个尺寸选择都能追溯到需求、载荷与验证证据？",
            "fixed_facts": [
                "以下均为教学用合成数据，不代表真实企业项目或标准推荐值",
                "电机额定功率 4 kW，工作转速 600 r/min，正常工况传递扭矩为 63.7 N·m",
                "带轮节径 200 mm，紧边与松边张力比 F1/F2=3，带轮位于 C 点",
                "轴承支点 A、B 的坐标分别为 0 mm、240 mm，带轮 C 坐标为 160 mm",
                "定位端轴承 B 另承受 0.40 kN 轴向载荷；该载荷不计入竖直平面弯矩",
                "目标额定寿命为 12000 h，正常工况转速始终为 600 r/min",
                "轴径候选为 25 mm 与 30 mm；轴承候选的教学参数分别为 C=8 kN 与 C=12 kN",
            ],
            "allowed_variations": [
                "可单独引入启动工况 1.5 倍扭矩作为边界检查，但不得覆盖正常工况数据",
                "可对安全系数或支承位置做敏感性分析，必须明确它是变式而非原方案事实",
            ],
            "final_artifact": "一页可追溯的轴系设计评审单，含失败项、修订动作与重验范围",
            "continuity_rule": "三节必须沿用以上几何、载荷和寿命事实；前节未算出的结果不得声称已经得到。",
            "required_closures": [
                {
                    "closure_id": "MECH-STARTUP-STRENGTH",
                    "requirement": "闭环第一节提出的 1.5 倍启动扭矩静强度边界检查",
                    "target_node_id": "L2-1-2",
                    "evidence": "明确张力比假设，重算启动工况的带力、反力、弯矩和两个轴径名义等效应力；无许用准则时标为未验证",
                },
                {
                    "closure_id": "MECH-FINAL-STATUS",
                    "requirement": "最终评审不得引用课程中没有产生的强度、刚度或轴承选型通过证据",
                    "target_node_id": "L2-1-3",
                    "evidence": "每项严格标成通过、失败或未验证；刚度与正式选型若缺条件必须列出缺失数据",
                },
                {
                    "closure_id": "MECH-NUMERICAL-CROSSCHECK",
                    "requirement": "关键派生数值在正文、表格和反馈中保持一致",
                    "target_node_id": "L2-1-2",
                    "evidence": "用 d^-3 比例核对 25/30 mm 应力比，用启动 1.5 倍比例核对带力、反力、弯矩与名义应力；舍入值一致",
                },
            ],
        },
        "sections": [
            {
                "title": "需求、载荷工况与失效准则：先定义什么叫设计成功",
                "objective": "能把模糊任务转成可检查的性能、安全、接口和寿命要求，并识别主工况与异常工况",
                "scope": "只冻结设计输入和评价准则；不提前选择轴径、材料型号或轴承型号",
                "assessment": ["为给定电机—带轮—负载场景提交需求表、工况矩阵和失效准则清单"],
                "spine_progression": {
                    "role": "introduce",
                    "action": "把固定输入转成需求—工况—失效—验证矩阵，并区分正常与启动工况",
                    "student_artifact": "冻结的设计输入表和需求—验证矩阵",
                    "handoff": "下一节直接使用已冻结的功率、转速、带轮和支点几何建立受力模型",
                    "variation": "启动工况仅作为 1.5 倍扭矩边界检查，不改变正常工况",
                    "closure_ids": [],
                },
                "knowledge": [
                    _knowledge(
                        "工程需求与评价准则",
                        "需求必须转化为带单位、容差、优先级和验证方法的可检查约束。",
                        knowledge_type="method",
                        conditions=["区分必须满足与期望优化"],
                        boundaries=["设计变量不是需求", "标准条款需有可核验来源"],
                        misconception="把低成本、高可靠写成没有量化口径的口号",
                        repair="为每项要求补充阈值、适用工况和验证动作",
                        mastery="建立可追溯的需求—验证矩阵",
                    ),
                    _knowledge(
                        "载荷工况与失效模式",
                        "设计载荷来自传力路径和工况组合，不同失效模式可能由不同工况控制。",
                        knowledge_type="model",
                        conditions=["明确稳态、启动、冲击和异常工况的持续时间或频次"],
                        boundaries=["最大单项载荷不一定构成最危险组合"],
                        misconception="只用额定扭矩代表所有设计工况",
                        repair="沿能量和力的传递路径列工况，并逐一映射到屈服、疲劳、磨损和打滑",
                        mastery="构造工况—失效模式矩阵并指出控制工况",
                    ),
                ],
            },
            {
                "title": "载荷路径与轴的初步设计：每个数都要回到模型假设",
                "objective": "能画轴系受力图，求支反力和危险截面，并比较两种轴径或支承布置方案",
                "scope": "完成静力模型和初步尺寸；疲劳修正、轴承寿命与详细结构留到下一节验证",
                "assessment": ["给定功率、转速、带轮尺寸和支承距离，提交受力图、反力、弯矩/扭矩图和两个方案比较"],
                "spine_progression": {
                    "role": "advance",
                    "action": "由固定输入计算带张力、支反力、最大弯矩和轴径候选，并记录模型假设",
                    "student_artifact": "含平衡复核的自由体图、载荷结果和 25/30 mm 轴径比较",
                    "handoff": "向下一节交付 B 端径向反力、正常转速、轴向载荷与两个轴径候选",
                    "variation": "",
                    "closure_ids": [
                        "MECH-STARTUP-STRENGTH",
                        "MECH-NUMERICAL-CROSSCHECK",
                    ],
                },
                "knowledge": [
                    _knowledge(
                        "轴系载荷路径与自由体图",
                        "带轮力、齿轮力或联轴器力通过轴和支承闭合，受力图必须保持方向、作用点和反力一致。",
                        knowledge_type="model",
                        conditions=["几何位置、坐标方向和边界约束明确"],
                        boundaries=["忽略轴向力或悬臂距离必须有依据"],
                        misconception="只算扭矩，不把带轮径向力传到支承和弯矩",
                        repair="从外部部件沿轴逐段追踪力流，并用整体平衡复核支反力",
                        mastery="独立建立受力图并通过平衡检查",
                    ),
                    _knowledge(
                        "弯扭组合下的轴径初估",
                        "轴径初估用等效应力或设计公式筛出候选尺寸，但结果依赖材料、载荷组合和安全口径。",
                        knowledge_type="method",
                        conditions=["明确许用应力、安全系数和危险截面"],
                        boundaries=["初估不能替代疲劳、刚度和应力集中复核"],
                        misconception="得到计算直径后直接取整并宣布设计完成",
                        repair="至少比较相邻标准直径，并说明强度、质量、接口和后续复核影响",
                        mastery="形成两个候选轴径并说明取舍依据",
                    ),
                ],
            },
            {
                "title": "轴承匹配与系统验证：让薄弱环节暴露出来",
                "objective": "能将轴承寿命、轴强度/刚度、配合与维护约束合并到同一验证表，并据此修改方案",
                "scope": "完成教学场景下的系统级复核；不替代企业标准、详细公差设计或实物试验",
                "assessment": ["比较两个轴承—轴径方案，提交验证表、失败项修订和最终推荐理由"],
                "spine_progression": {
                    "role": "verify",
                    "action": "只使用上一节固定模型得到的 B 端反力，完成两套轴承—轴径方案寿命与系统边界复核",
                    "student_artifact": "含失败项、修订动作和需重验项目的最终设计评审单",
                    "handoff": "完成全课最终工程成果",
                    "variation": "",
                    "closure_ids": ["MECH-FINAL-STATUS"],
                },
                "knowledge": [
                    _knowledge(
                        "轴承等效载荷与额定寿命",
                        "轴承寿命估算把径向/轴向载荷、转速和可靠性口径转成可比较的寿命证据。",
                        knowledge_type="model",
                        conditions=["载荷谱、转速、轴承类型和可靠度口径已知"],
                        boundaries=["额定寿命是统计量，不是单个轴承的保证寿命"],
                        misconception="只按内径匹配轴承，不检查载荷方向和寿命",
                        repair="先判载荷类型与等效载荷，再计算寿命并检查安装、润滑和环境边界",
                        mastery="完成轴承候选比较并解释寿命假设",
                    ),
                    _knowledge(
                        "系统级设计验证与迭代",
                        "设计验证逐项连接需求、计算/仿真/试验证据和通过准则，失败项必须触发可追溯修改。",
                        knowledge_type="procedure",
                        conditions=["验证项覆盖控制失效模式和关键接口"],
                        boundaries=["局部强度通过不代表系统可制造、可装配或可维护"],
                        misconception="只展示通过的计算，隐藏假设和未验证项",
                        repair="设置失败注入或边界工况，记录哪项要求失败、改了什么以及需要重跑哪些验证",
                        mastery="提交包含失败项和修订闭环的设计评审单",
                    ),
                ],
            },
        ],
    },
}


def _build_course(key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spec = COURSES[key]
    profile = resolve_pedagogy_profile(
        subject=spec["subject"],
        requirements=spec["requirements"],
        requested_mode="auto",
    )
    sections: list[dict[str, Any]] = []
    for index, item in enumerate(spec["sections"], start=1):
        node_id = f"L2-1-{index}"
        sections.append({
            "node_id": node_id,
            "parent_node_id": "L1-1",
            "node_level": 2,
            "section_number": f"1.{index}",
            "title": item["title"],
            "node_name": item["title"],
            "learning_objective": item["objective"],
            "scope_boundary": item["scope"],
            "assessment": item["assessment"],
            "spine_progression": item["spine_progression"],
            "prerequisite_node_ids": [f"L2-1-{index - 1}"] if index > 1 else [],
            "key_points": [point["name"] for point in item["knowledge"]],
            "knowledge_structure": [{
                "concept_group": item["title"],
                "description": item["objective"],
                "knowledge_points": item["knowledge"],
            }],
            "misconceptions": [
                point["misconceptions"][0]["name"]
                for point in item["knowledge"]
            ],
            "grounding_contract": {
                "required_evidence_ids": [],
                "optional_evidence_ids": [],
                "allow_general_knowledge": True,
            },
        })
    plan = {
        "course_title": spec["course_name"],
        "positioning": spec["positioning"],
        "learning_objectives": [spec["final_outcome"]],
        "prerequisites": [spec["audience"]],
        "course_spine": spec["course_spine"],
        "chapters": [{
            "chapter_id": "L1-1",
            "chapter_number": 1,
            "title": spec["chapter"],
            "learning_focus": spec["chapter_focus"],
            "sections": sections,
        }],
    }
    difficulty = compile_difficulty_profile(
        "intermediate",
        primary_mode=profile.primary_mode,
        secondary_mode=profile.secondary_mode,
    )
    gap = assess_readiness(difficulty, None)
    adaptation = decide_adaptation(gap)
    attach_difficulty_contracts_to_plan(
        plan,
        profile=difficulty,
        adaptation=adaptation,
    )
    attach_module_plans_to_plan(plan, profile)
    attach_composition_to_plan(plan, "balanced")
    sections = plan["chapters"][0]["sections"]

    artifacts = build_course_generation_artifacts(
        course_id=f"content-outcome-{key}",
        topic=spec["subject"],
        difficulty="intermediate",
        style="balanced",
        requirements=spec["requirements"],
        target_audience=spec["audience"],
        course_type="systematic",
        teacher_course_brief={
            "target_audience": spec["audience"],
            "total_class_hours": 3,
            "lesson_duration_minutes": 50,
            "teaching_context": "大学小班研讨与板演",
        },
        grounding_strategy="general_knowledge",
        course_purpose="systematic",
    )
    template = compile_subject_generation_template(profile)
    contract = compile_course_design_contract(
        brief=artifacts["course_generation_brief"],
        subject_template=template,
        difficulty_profile=difficulty.to_dict(),
        gap_assessment=gap.to_dict(),
        adaptation_decision=adaptation.to_dict(),
        grounding_strategy="general_knowledge",
    )
    chapter_node = {
        "node_id": "L1-1",
        "parent_node_id": "root",
        "node_level": 1,
        "node_name": spec["chapter"],
    }
    course = {
        "course_id": f"content-outcome-{key}",
        "course_name": spec["course_name"],
        "target_audience": spec["audience"],
        "requirements": spec["requirements"],
        "difficulty": "intermediate",
        "generation_request": {
            "target_audience": spec["audience"],
            "difficulty": "intermediate",
            "teacher_course_brief": artifacts["course_generation_brief"]["teacher_course_brief"],
        },
        "teacher_course_brief": artifacts["course_generation_brief"]["teacher_course_brief"],
        "course_generation_brief": artifacts["course_generation_brief"],
        "subject_pedagogy_profile": profile.to_dict(),
        "subject_generation_template": template,
        "course_design_contract": contract,
        "difficulty_profile": difficulty.to_dict(),
        "adaptation_decision": adaptation.to_dict(),
        "course_composition_profile": plan["course_composition_profile"],
        "course_plan": plan,
        "nodes": [chapter_node, *sections],
        "course_teaching_plan": {
            "revision_id": f"teaching-{key}-fixed",
            "sections": [{
                "node_id": section["node_id"],
                "knowledge_structure": section["knowledge_structure"],
                "teaching_modules": [],
            } for section in sections],
        },
        "evidence_catalog": [],
    }
    course["course_knowledge_base"] = compile_course_knowledge_base(course)
    return course, sections


def build_fixed_content_prompts() -> dict[str, dict[str, str]]:
    composer = CoursePromptComposer()
    result: dict[str, dict[str, str]] = {}
    for course_key in COURSES:
        course, sections = _build_course(course_key)
        result[course_key] = {}
        for section in sections:
            user_prompt, system_prompt = composer.build_content_prompt(
                course_data=course,
                node=section,
                context="无上传资料；本轮只使用稳定学科知识，不得编造外部标准或型号数据。",
                detail_level="full",
            )
            result[course_key][section["node_id"]] = "\n\n".join((
                system_prompt,
                user_prompt,
            ))
    return result


async def generate(course_keys: list[str]) -> dict[str, Any]:
    composer = CoursePromptComposer()
    provider = CodexLocalProvider.from_environment()

    async def run(
        course_key: str,
        course: dict[str, Any],
        section: dict[str, Any],
    ) -> dict[str, Any]:
        user_prompt, system_prompt = composer.build_content_prompt(
            course_data=course,
            node=section,
            context="无上传资料；本轮只使用稳定学科知识，不得编造外部标准或型号数据。",
            detail_level="full",
        )
        output, telemetry = await provider.complete(
            user_prompt,
            system_prompt,
            use_fast_model=False,
            json_mode=False,
            max_tokens=4_500,
        )
        return {
            "node_id": section["node_id"],
            "title": section["node_name"],
            "telemetry": telemetry,
            "output": output,
        }

    courses: list[dict[str, Any]] = []
    calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for key in course_keys:
        course, sections = _build_course(key)
        courses.append({
            "course_key": key,
            "course_name": course["course_name"],
            "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        })
        calls.extend((key, course, section) for section in sections)
    generated = await asyncio.gather(*(run(*item) for item in calls))
    by_course = {item["course_key"]: {**item, "sections": []} for item in courses}
    for (course_key, _course, _section), output in zip(calls, generated):
        by_course[course_key]["sections"].append(output)
    return {
        "schema_version": "course_content_outcome_benchmark_v1",
        "scope": "两门固定三节课本地模型创始人通读样本，不代表生产发布门",
        "courses": list(by_course.values()),
    }


def _course_markdown(payload: dict[str, Any], course_key: str) -> str:
    course = next(
        item for item in payload.get("courses") or []
        if item.get("course_key") == course_key
    )
    sections = []
    for index, section in enumerate(course.get("sections") or [], start=1):
        sections.append(
            f"# 第 {index} 节：{section.get('title') or ''}\n\n"
            f"{section.get('output') or ''}"
        )
    return "\n\n".join(sections)


async def review_pair(
    baseline_path: Path,
    candidate_path: Path,
    course_keys: list[str],
) -> dict[str, Any]:
    """Blindly compare full readable artifacts, not prompt-token coverage."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    provider = CodexLocalProvider.from_environment()

    async def review(course_key: str) -> dict[str, Any]:
        # Deliberately hide prompt versions and file names.  A/B assignment is
        # stable so repeated reviews are comparable, but the reviewer sees only
        # learner-facing Markdown.
        version_a = _course_markdown(candidate, course_key)
        version_b = _course_markdown(baseline, course_key)
        system_prompt = """你是课程创始人的匿名内容试读者。请先忘记提示词和字段契约，只读学生最终看到的课程。

不要用“结构完整、逻辑清晰”之类空泛套话，也不要因为某版更长或字段更齐全就判它更好。先以目标学生身份连续读完三节，判断是否真的学会了；再以学科课程编辑身份检查专业准确性、前后推进、主轴案例、解释取舍、课时负荷、练习迁移和反馈是否有用。

每个批评必须引用或精确指向具体段落、例题、公式或任务。如果发现事实、数学、工程或教学硬伤，必须明确列出。最后必须选择 A、B 或 tie；只有真的无法区分时才能选 tie。

只输出 JSON：
{
  "learner_read": {"A": "具体阅读体验", "B": "具体阅读体验"},
  "editor_read": {"A": ["具体优点或缺点"], "B": ["具体优点或缺点"]},
  "hard_failures": {"A": [], "B": []},
  "winner": "A|B|tie",
  "decision": "为什么更愿意发布这一版",
  "remaining_work": ["胜出版仍应修的具体问题"]
}""".strip()
        output, telemetry = await provider.complete(
            f"## 版本 A\n\n{version_a}\n\n## 版本 B\n\n{version_b}",
            system_prompt,
            use_fast_model=False,
            json_mode=True,
            max_tokens=4_500,
        )
        return {
            "course_key": course_key,
            "anonymous_assignment": "A=candidate,B=baseline",
            "telemetry": telemetry,
            "review": json.loads(output),
        }

    reviews = await asyncio.gather(*(review(key) for key in course_keys))
    return {
        "schema_version": "course_content_blind_review_v1",
        "scope": "同模型匿名三节课通读，用于阻止提示词反向优化，不是生产统计发布门",
        "reviews": reviews,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--courses",
        nargs="+",
        choices=tuple(COURSES),
        default=list(COURSES),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.baseline) != bool(args.candidate):
        raise SystemExit("--baseline and --candidate must be provided together")
    operation = (
        review_pair(args.baseline, args.candidate, args.courses)
        if args.baseline and args.candidate
        else generate(args.courses)
    )
    payload = json.dumps(
        asyncio.run(operation),
        ensure_ascii=False,
        indent=2,
    )
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
