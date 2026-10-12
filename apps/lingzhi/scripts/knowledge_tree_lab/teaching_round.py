"""Frozen WenCode-style capability evaluation. No production writes/model retries."""
from pathlib import Path
from copy import deepcopy
import argparse
import hashlib
import json

from .pipeline import read, save, digest, identity

APP = Path(__file__).resolve().parents[2]
UNITS = [
    ("T1", "types", "判定字面量类型", [1, 2, 3]),
    ("T2", "types", "按适用规则确定操作数转换", [4, 5, 6]),
    ("T3", "types", "区分运算、显式转换与接收转换", [7, 8, 9, 10]),
    ("T4", "types", "判断整数转换的值与可移植性", [11, 12, 13]),
    ("T5", "types", "区分浮点转换的截断、范围与精度", [14, 15, 16]),
    ("I1", "if", "沿条件与分支体追踪一次执行", [1, 2, 3, 8]),
    ("I2", "if", "按语法确定 else 归属与可达性", [4, 5, 6, 7]),
    ("I3", "if", "区分选择链与独立 if 的状态变化", [9, 10, 11, 12]),
    ("F1", "for", "列出 for 各阶段与执行次数", [1, 2, 3, 4, 5]),
    ("F2", "for", "推导省略子句后的实际控制流", [6, 7, 8, 9]),
    ("F3", "for", "确定单语句、复合语句与空循环体", [10, 11]),
    ("F4", "for", "分别追踪 continue、break 与 return", [12, 13, 14]),
    ("F5", "for", "判定 switch 与循环嵌套中的转移目标", [15, 16]),
    ("F6", "for", "区分变量作用域与退出后状态", [17, 18, 19]),
    ("F7", "for", "区分无符号终止失败与有符号溢出", [20, 21]),
]

# New transfer tasks reviewed before the model run. These test changed contexts,
# not a verbatim replay of the diagnostic bank. No model-generated code executes.
TRANSFER = {
"T1": ("分别给出 42、1U、6.25、6.25f 的类型。42 可由 int 表示。", "int；unsigned int；double；float。", "无后缀且在 int 范围内的十进制整数、值为1的 U 字面量、无后缀浮点和 f 后缀分别应用相应类型规则。"),
"T2": ("在 int 不能容纳 unsigned short 全部值的实现上，先判断表达式中的 unsigned short 值需要整数提升时提升到何种类型；另分别判断 int 与 double、int 与 unsigned int 的通常算术转换方向。三个问题彼此独立。", "unsigned int；int 转 double；int 转 unsigned int。", "第一问有明确的整数提升场景和类型范围假设；后两问分别适用指定的类型组合，不给所有混合运算强行加整数提升步骤。"),
"T3": ("设 int a=9,b=4；分别求 double x=a/b、double y=(double)a/b、double z=(double)(a/b) 初始化后的值，并说明 a 的类型和值是否改变。", "x=2.0，y=2.25，z=2.0；a 仍为 int，值为9。", "两个 int 先相除向零截断；先转操作数才进行浮点除法；转换结果或接收类型不能恢复丢失的小数。只读取并转换 a 不修改它。"),
"T4": ("分别判断：(unsigned int)-2；把可由 short 表示的整数 17 转为 short；把明确超出 int 范围的整数转为 int。哪些可由 C17 确定数值？", "前者为 UINT_MAX-1，第二项为17；第三项结果由实现定义，或产生实现定义的信号，不能给统一数值。", "无符号目标按 UINT_MAX+1 取模；目标可表示则保值；超范围转有符号类型不等于有符号算术溢出。"),
"T5": ("假设 -4 可由 int 表示，判断 (int)-4.75 的值；判断 (unsigned int)-2.5 是否能用整数模转换求值；若整数 X 在 double 的数值范围内，能否据此保证 (double)X 精确等于 X？", "-4；不能，截断后的-2不可由 unsigned int 表示，行为未定义；不能保证精确相等。", "浮点转整数先向零截断，再检查目标可表示范围；整数到浮点的范围与有效精度是不同约束。"),
"I1": ("分别从 int x=-2,y=0 开始执行 A: if(x){x=0;y=1;}else y=2; B: if(x); y=3;。给出各自终值并说明是否再次选分支。", "A: x=0,y=1，不再选 else；B: x=-2,y=3，分号是 if 的空语句体，y=3 独立执行。", "负数非零为真；分支内修改条件变量不回头重新判断；分号决定控制体，不以排版决定。"),
"I2": ("设 x=5。比较 A: if(a) if(b) x=1; else x=2; 与 B: if(a){if(b)x=1;}else x=2;。对(a,b)=(1,0)及(0,0)分别给出 x。", "A: 2、5；B: 5、2。", "A 的 else 属于内层 if，a 假时内层整体不执行；B 的 else 位于真分支复合语句之外，归外层。"),
"I3": ("分别从 int x=1,y=0 开始执行 A: if(x==1)x=2;else if(x==2)y=7; B: if(x==1)x=2;if(x==2)y=7;。比较终值及第二个条件是否求值。", "A: x=2,y=0，后续 else-if 条件不再求值；B: x=2,y=7，第二个独立 if 用新值2判断。", "选择链首命中即跳过后续分支；独立判断顺序执行并读取已修改状态。"),
"F1": ("在 for(int i=2;i<5;i++){ /* 无跳转且不改 i */ } 中，列出入体 i 序列以及初始化、控制判断、迭代表达式的次数；再将首值改为5比较。", "首值2：入体2、3、4；初始化1次、判断4次、迭代3次。首值5：不入体；初始化1次、判断1次、迭代0次。", "初始化一次；每次入体前判断；正常体后迭代；退出还需一次假判断。"),
"F2": ("初值 int i=2。A: for(;i<5;){i+=2;} 的终值是什么？B: for(;;){break;} 的空条件如何解释？头部两个分号能否省掉？", "A 终值6；B 的省略条件按非零常量处理，因 break 退出；两个分号不能省。", "省略初始化保留已有状态，省略迭代不暗加 i++；省略条件与语法分隔符是不同问题。"),
"F3": ("分别从 int i=0,c=0 开始：A: for(;i<2;i++); c++; B: for(;i<2;i++){c++;}。比较 c 的终值并标出循环体范围。", "A 的 c=1，循环体是空语句；B 的 c=2，循环体是包含 c++ 的复合语句。两者 i 都为2。", "紧随头部的一条语句为循环体；复合语句整体是一条语句；空语句后的独立语句只在循环结束后执行。"),
"F4": ("分别追踪从 i=0 开始且条件 i<4、迭代 i++ 的 for，在 i==1 时执行 continue、break、return 的路径。每种情况下是否执行本轮剩余体、i++、循环后的语句？return 位于 void 函数。", "continue 跳过剩余体，执行 i++ 再判断，若后来正常退出可执行循环后语句；break 跳过剩余体与本轮 i++，直接到循环后；return 跳过剩余体、i++ 与当前函数中循环后语句，结束函数。", "三种转移目标不同；return 是函数退出；continue 不是 break，for 的 continue 路径仍含迭代。"),
"F5": ("for 体包含 switch，switch 后还有语句 S，最内层循环就是该 for。switch 分支中分别执行 break 与 continue 时，S 和 for 的迭代表达式是否会执行？设第三部分非空，S 无跳转且正常结束。", "break 只退出 switch，随后执行 S，再执行迭代表达式；continue 跳过 S，执行 for 的迭代表达式后重新判断。", "break 寻找最内层循环或 switch；continue 的目标是最内层循环，switch 不拦截它。"),
"F6": ("A: for(int j=0;j<2;j++){} 后在块外读取 j 是否有效？B: int j;for(j=0;j<5;j++){j++;} 后 j 是多少？两个代码段独立讨论。", "A 无效，j 的作用域已结束；B 的 j=6。", "B 入体 j 依次为0、2、4，每轮体内和头部各加1；最后判定6<5为假，外部变量仍可读取。"),
"F7": ("A: unsigned int u=0;for(;u>=0;u--){} 是否会因该条件为假而退出？B: int i=INT_MAX;for(;i<=INT_MAX;i++){} 首轮体后是否还能给出标准确定的终值？均无额外跳转。", "A 不会，unsigned int 始终非负，递减可回绕；B 首轮体后 i++ 有符号溢出，行为未定义，不能给标准确定终值。", "无符号回绕有定义，但该条件不提供退出；有符号 INT_MAX 加1不能按无符号回绕推算。")
}

PROMPT = """对标给定 WenCode 精修范式，补全一个 C17 教学能力包。输入知识事实、题目与正确答案已复核，不得修改，也不得新增知识ID。
能力应能观察学生实际操作，覆盖本组全部知识点；不要用“理解/掌握”代替可观察行为。
为每个知识短键各写一条达标标准，写明学生需给出的证据、必须满足的条件；使用给定检查题引用。
给出三个具体且不同的错误信念 A/B/C，至少关联一个真实知识短键。错因应是学生可能持有的错误规则，不是“粗心/没理解”。
选择输入 probes 的2至4题作为区分题，不能把 RETEST 作为区分题。对每个错误信念逐题给出“假如学生持有且持续应用此规则会怎样回答”及推理。
错误信念不适用于某题时写“无预测”，不可假定该学生同时持有别的错误。不能为了让矩阵不同而编造不由错因推出的预测。
至少一题能暴露每种错误；每对假设至少一题有明确且不同的预测；可比较多题回答组合与解释。若输入证据不够，明确写 unresolved，不自造正确答案或伪装已区分。
针对每条错因给出2至3步具体补救，含要画/写/修改的对象和检查方式。训练任务可引用题库；复测必须引用 RETEST，写达标证据但不要复写或改写正确答案。
正确答案、知识ID、修订和正式记录ID由程序从引用解析。模型只写教学内容和假设预测。所有诊断均是待验证假设，不声称凭一次错误答案就确诊。
严格返回JSON（中文）：
{"unit_key":"原值","skill":{"name":"能力名称","observable_behavior":"能完成的动作与产物","task":"具体训练要求","steps":["步骤"],"boundaries":["应用边界"]},
"criteria":[{"point_key":"K-T01","probe_key":"Q-T01","observable_performance":"这一点的达标证据","failure_evidence":"未达标表现"}],
"diagnostic_probe_keys":["Q-T01","Q-T02"],
"mistakes":[{"key":"A","name":"具体错因","point_keys":["K-T01"],"wrong_rule":"错误信念的明确规则","observable_error":"能看到的作答/轨迹表现",
"predictions":[{"probe_key":"Q-T01","answer":"假设下的回答或无预测","reason":"只应用该假设如何推出"}],"repair_steps":["具体行动","检查证据"]}],
"practice":{"task":"具体训练任务","steps":["动作"],"evidence":"需提交什么","retest_key":"RETEST","mastery_requirements":["复测达标条件"]},
"unresolved":[]}。
三个 mistakes 分别为 A/B/C，每个 predictions 必须与 diagnostic_probe_keys 一一对应。criteria 必须覆盖所有给定知识短键。
总输出保持精炼，每个回答/理由约20至60字，完整性优先，不超过8500 tokens。"""


def prepare(root, course_path):
    require_new = root / "manifest.json"
    if require_new.exists():
        raise ValueError("round_already_frozen")
    course = read(course_path)
    tree = course["course_knowledge_base"]
    package = read(APP / "backend/resources/knowledge_first/c17.json")
    save(root / "source-tree.json", tree)
    save(root / "source-material.json", package)
    jobs, units = [], []
    for key, topic, name, numbers in UNITS:
        bundle = package["bundles"][topic]
        prefix = {"types": "T", "if": "I", "for": "F"}[topic]
        keys = [f"K-{prefix}{n:02d}" for n in numbers]
        points = [p for p in tree["knowledge_points"] if p["key"] in keys]
        probes = [{"key": q["key"], "point_keys": q["knowledge_keys"], "question": q["question"],
                   "answer": q["answer"], "rationale": q["rationale"], "conditions": q["conditions"]}
                  for q in bundle["exercise_bank"] if set(q["knowledge_keys"]) <= set(keys)]
        for e in bundle["example_bank"]:
            if set(e["knowledge_keys"]) <= set(keys):
                probes.append({"key": e["key"], "point_keys": e["knowledge_keys"],
                    "question": "给出标准输出并说明执行轨迹：" + e["code"], "answer": e["answer_stdout"],
                    "conditions": [e["context"]], "answer_ref": e["answer_ref"]})
        q, answer, reason = TRANSFER[key]
        retest = {"key": "RETEST", "point_keys": keys, "question": q, "answer": answer, "rationale": reason,
                  "origin": "codex_pre_run_reviewed_transfer", "conditions": ["C17；各题所列前提成立"]}
        unit = {"unit_key": key, "topic": topic, "name": name, "points": points, "probes": probes, "retest": retest,
                "reference_pattern": "概念对象与边界→可观察能力→具体错误规则/症状→区分证据→针对修复→改变情境复测→可判定达标标准"}
        units.append(unit)
        jobs.append({"id": key, "instruction": PROMPT, "input": unit, "max_tokens": 11000})
    save(root / "units.json", units)
    save(root / "jobs.json", jobs)
    save(root / "eval-definition.json", {
        "schema": "wencode_teaching_eval_v1", "scope": "49个既有知识点，15个操作能力组；不扩展到全课",
        "requirements": ["49点各有独立可观察标准和冻结检查题", "15能力组各有实际操作与边界", "每组3具体错因及独立修复步骤",
            "预测由错误规则推出；不靠同义异文制造区分", "每组改变情境复测且保留正确答案", "知识点ID/事实/版本不变",
            "结构通过不冒充语义通过；原千问与编辑修订分别记录"],
        "semantic_dimensions": ["学科正确", "实际测试所标知识", "错因与预测一致", "真能区分假设", "补救具体且针对", "复测迁移与达标证据"]})
    inputs = ["source-tree.json", "source-material.json", "units.json", "jobs.json", "eval-definition.json"]
    save(root / "manifest.json", {"schema": "teaching_round_v1", "source_course_id": course["course_id"],
        "source_document_revision": course["course_document_revision"], "source_knowledge_revision": tree["revision_id"],
        "model_calls_max": len(jobs), "input_hashes": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in inputs}})
    print("Frozen", len(jobs), "single-attempt Qwen jobs for", sum(len(u["points"]) for u in units), "points")


def assess(unit, doc):
    errors = []
    warnings = []
    keys = {p["key"] for p in unit["points"]}
    probes = {p["key"]: p for p in unit["probes"]}
    def check(ok, code):
        if not ok: errors.append(code)
    check(doc.get("unit_key") == unit["unit_key"], "unit_key")
    skill = doc.get("skill") or {}
    check(isinstance(skill.get("name"), str) and len(skill["name"]) >= 2 and
          all(isinstance(skill.get(k), str) and len(skill[k]) >= 8 for k in ["observable_behavior", "task"]), "skill_text")
    check(len(skill.get("steps", [])) >= 2 and bool(skill.get("boundaries")), "skill_steps_boundary")
    criteria = doc.get("criteria") or []
    check(len(criteria) == len(keys) and {c.get("point_key") for c in criteria} == keys, "criteria_coverage")
    for c in criteria:
        check(c.get("probe_key") in probes and c.get("point_key") in probes.get(c.get("probe_key"), {}).get("point_keys", []), "criterion_target:" + str(c.get("point_key")))
        check(bool(c.get("observable_performance")) and bool(c.get("failure_evidence")), "criterion_evidence")
    selected = doc.get("diagnostic_probe_keys") or []
    check(2 <= len(selected) <= 4 and len(set(selected)) == len(selected) and set(selected) <= set(probes), "diagnostic_refs")
    mistakes = doc.get("mistakes") or []
    check(len(mistakes) == 3 and {m.get("key") for m in mistakes} == {"A", "B", "C"}, "mistake_count")
    for m in mistakes:
        check(bool(m.get("point_keys")) and set(m["point_keys"]) <= keys, "mistake_point_refs")
        check(all(bool(m.get(k)) for k in ["name", "wrong_rule", "observable_error"]) and len(m.get("repair_steps", [])) >= 2, "mistake_depth")
        ps = m.get("predictions") or []
        check(len(ps) == len(selected) and {p.get("probe_key") for p in ps} == set(selected), "prediction_refs")
        check(all(p.get("answer") and p.get("reason") for p in ps), "prediction_evidence")
    normalized_questions = ["".join(probes[k]["question"].split()) for k in selected if k in probes]
    if len(normalized_questions) != len(set(normalized_questions)):
        warnings.append("duplicate_probe_content")
    for a, first in enumerate(mistakes):
        left = {p.get("probe_key"): p.get("answer") for p in first.get("predictions", [])}
        for second in mistakes[a+1:]:
            right = {p.get("probe_key"): p.get("answer") for p in second.get("predictions", [])}
            known = [k for k in set(left) & set(right) if left[k] and right[k] and "无预测" not in left[k] and "无预测" not in right[k]]
            if not known or all(left[k] == right[k] for k in known):
                warnings.append("no_demonstrated_pair_separation:" + str(first.get("key")) + ":" + str(second.get("key")))
    practice = doc.get("practice") or {}
    check(practice.get("retest_key") == "RETEST" and bool(practice.get("task")) and bool(practice.get("evidence")) and len(practice.get("steps", [])) >= 2 and bool(practice.get("mastery_requirements")), "practice_transfer")
    # Distinct wording is NOT a semantic diagnostic pass. Review each vector.
    return {"structure_passed": not errors, "errors": errors, "warnings": warnings, "unresolved": doc.get("unresolved", []),
            "semantic_status": "pending_independent_review", "diagnostic_validated": False}


def compile_round(root):
    units = read(root / "units.json")
    results = []
    for unit in units:
        file = root / "calls" / unit["unit_key"] / "parsed.json"
        normalized = root / "format-normalized" / (unit["unit_key"] + ".json")
        if normalized.exists():
            file = normalized
        if not file.exists():
            results.append({"unit_key": unit["unit_key"], "assessment": {"structure_passed": False, "errors": ["missing_model_result"]}})
            continue
        doc = read(file)
        results.append({"unit_key": unit["unit_key"], "input": unit, "generated": doc, "assessment": assess(unit, doc)})
    save(root / "qwen-candidate.json", results)
    print(json.dumps({"units": len(results), "structural_pass": sum(r['assessment']['structure_passed'] for r in results),
        "issues": {r['unit_key']: r['assessment']['errors'] for r in results if r['assessment']['errors']}}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "compile"])
    parser.add_argument("root", type=Path)
    parser.add_argument("--course", type=Path)
    args = parser.parse_args()
    if args.action == "prepare": prepare(args.root, args.course)
    else: compile_round(args.root)
