"""Independent Codex adjudication of this frozen Qwen round, not a model grader.

Findings refer to exact output fields. No semantic repair is counted as Qwen
success; the sole F2 bracket repair is separately logged and preserves text.
"""
from pathlib import Path
import argparse
from copy import deepcopy
from .pipeline import read, save, digest, identity
from .teaching_round import compile_round

# All assertions below were checked against the raw output and frozen prompts.
# An absent prediction is unknown evidence, never evidence against a hypothesis.
FINDINGS = {
"T1": [
 ("mistakes.B.repair_steps", "无后缀→int、U→unsigned int 等对照表丢失数值范围限制，不能推广到任意大整数常量。"),
 ("mistakes.C.repair_steps", "float a=3.14 的编译告警不保证出现，不能用有无告警证明字面量类型；应使用规则或适用的类型检查。"),
 ("mistakes.*.predictions", "A/B/C 分别作用于互不重合题目；无预测不能排除另一错因，尚未满足预定的成对区分证据标准。")],
"T2": [
 ("mistakes.A.predictions[Q-T06]", "窄整数一律提升为int，不推出int/unsigned int比较时unsigned int转int；这里偷加了另一个错误规则。"),
 ("mistakes.B.wrong_rule", "把最小秩和保留负数合为一个或条件，预测不唯一；其补救又错误地泛化成总是向高秩转换。"),
 ("mistakes.C.repair_steps", "固定32位、补码位拷贝没有题设保证；C17的整数转无符号应按值域同余解释。"),
 ("mistakes.C.predictions[Q-T06]", "Q-T06问转换后的类型，模型预测却是数值0或Error，问答对象不一致。")],
"T3": [
 ("mistakes.A.wrong_rule", "把负数向下取整与接收类型反向传播捆成一条错因；又给出变量被转换改类型的预测，超出该假设。"),
 ("mistakes.A.repair_steps", "把C标准7.16.2当作除法条款，来源错误；乘除规则在6.5.5。"),
 ("mistakes.C.repair_steps", "声称只有赋值、自增、自减才改变对象，遗漏函数调用等可带来的修改。"),
 ("practice.steps", "预期输出把a写成10，冻结复测的a=9；与本包后面的达标条件自相矛盾。")],
"T4": [
 ("skill.boundaries", "将_Bool纳入本组整数转换范围，但所引模转换/保值规则明确排除_Bool。"),
 ("mistakes.C.wrong_rule", "执行位运算不必改变可表示值；不能据此必然推出100转short会改变，假设不足以决定预测。"),
 ("mistakes.C.repair_steps", "检查目标short的范围时给出INT_MIN/INT_MAX，目标类型不匹配。")],
"T5": [
 ("mistakes.B.predictions", "没有unsigned int为32位的前提，却把预测固定为4294967295。"),
 ("mistakes.B.repair_steps / practice", "要求执行越界浮点转整数并打印结果作验证；该行为未定义，某次输出不能作为正确性或可移植性证据。"),
 ("mistakes.C.repair_steps", "double约2^53需要具体格式假设，输入明确不假定所有实现精度相同。")],
"I1": [
 ("mistakes.C.repair_steps", "把 if(a)x=1;{y=2;} 标为错误示范并要求比较执行差异；它与 if(a){x=1;}y=2; 的y均独立执行，不能证明所宣称的差异。"),
 ("mistakes.C.wrong_rule", "缩进控制与忽略分号被合并，预测还追加跳过后续全部代码的假设，错因不可独立定位。"),
 ("practice.task", "引用一段未给出的混合代码并要求重构，没有原始代码及预期功能合同，训练需再补输入。")],
"I2": [
 ("mistakes.A.wrong_rule", "缩进归属与机械文本就近可能给出相反判断，不能合成同一确定性假设。"),
 ("mistakes.A/B.repair_steps", "不能把特定块外else的限制泛化成任何else连线都不跨花括号；如 if(a){x=1;}else x=2; 本来合法。"),
 ("diagnostic_probe_keys", "Q-I04与Q-I07为完全相同的代码与问题，不构成两个独立区分证据；这是冻结输入题库本身的局限。")],
"I3": [
 ("mistakes.B.predictions[Q-I12]", "B假设跳过第二个独立if，却回答第二个条件求值为假。未求值与求值为0是不同观察结果，当前预测掩盖了区别。"),
 ("mistakes.C.predictions", "理由多处承认无预测，却自行填入正确答案；不能把未定义的假设外行为当作已知正确。"),
 ("practice.task", "要求分析一段混合的5行代码但未给代码。复测本身完整，可用作训练输入，原训练字段尚不自足。")],
"F1": [
 ("mistakes.B.wrong_rule / predictions", "把不同执行时机合并，预测给出10或12；还从更新时机错因推断出少算退出判断，加入了另一个错因。"),
 ("mistakes.A.predictions[Q-F03]", "只规定首判假仍入体，不足以推出最终i=-1；若随后正常执行头部i++则是0，需明确错误转移语义。"),
 ("mistakes.B.observable_error", "把迭代发生在条件判断之前写成错误表现，而正常for的体后迭代本就先于下一次条件判断。")],
"F2": [
 ("raw_json", "repair_steps尾部多余/错配括号导致原始JSON解析失败；仅格式修复后才可入结构检查。"),
 ("mistakes.B.repair_steps", "把 for(;;) 改为 for(1;) 是非法C语法；显式真条件应保留两个分号，如 for(;1;)。"),
 ("practice.mastery_requirements", "RETEST-A使用i+=2，但说明i未自增容易误成值不变化；应准确说没有头部隐式i++、体内仍修改i。")],
"F3": [
 ("mistakes.A/C.predictions", "对Q-F10预测相同，对Q-F11的A又无预测，尚不能据题组排除A/C之一；A的缩进前提也未由单行题目保证。"),
 ("mistakes.B.repair_steps", "空语句体与空复合语句体是不同语法节点，不能声称AST结构相同。格式化是否缩进也不是语义证明。"),
 ("practice", "两段代码仅第一段含Inner打印；必须分别明确输出，不能用一组Inner/Outer输出概括两段。")],
"F4": [
 ("mistakes.A/C", "A与C最终都被写成continue直接退出，在实际选题上没有有效区分；C混淆跳过更新、跳过判断和结束循环。"),
 ("mistakes.B.predictions[E-F05]", "题目要求标准输出，update after丢失两个换行边界；应区分概念性预测与精确输出。"),
 ("criteria[K-F14]", "return后的无任何后续需限定为当前函数；调用者仍会继续，不能让学生把函数返回理解成整个程序结束。")],
"F5": [
 ("mistakes.A.predictions[Q-F15]", "如果误把switch内break当成退出for，第一次就跳过switch后的printf，应预测0个A而非1个。"),
 ("mistakes.B/C", "假设分别给出下一个case、switch结束、死循环或UB等多种走向，无法形成确定可检验的错误规则。"),
 ("mistakes.C.predictions", "从不穿透switch的错误信念不能推出C语言未定义行为，这是模型把错误认知模拟与真实语言行为混淆。")],
"F6": [
 ("mistakes.A.predictions[Q-F19]", "变量作用域错误不推出忽略i+=2，预测0 1 2 3 4偷加了另一个错因。"),
 ("mistakes.B.predictions[Q-F19]", "答案0 3本身正确，但理由反复假设没有体内修改，证据链不自洽。"),
 ("mistakes.C.wrong_rule", "头部更新被忽略与体内修改无效是不同规则，不能作为同一个错因。")],
"F7": [
 ("mistakes.A.repair_steps", "unsigned int回绕数值直接写4294967295，缺少32位假设，应保留UINT_MAX。"),
 ("mistakes.C.wrong_rule / observable_error", "把正常体后先更新再判断称为错误顺序，又与达到INT_MAX会自动停止混合，纠错对象反而包含正确规则。"),
 ("practice.task", "要求对死循环/UB混合代码绘制完整执行轨迹，没有界定停止推导点；应在首个UB处停止，死循环仅给有限片段及证明。")],
}


def export(root, destination):
    compile_round(root)
    records = read(root / "qwen-candidate.json")
    assert len(records) == 15 and all("generated" in r for r in records)
    assert all(r["assessment"]["structure_passed"] for r in records), "incomplete_framework"
    tree = deepcopy(read(root / "source-tree.json"))
    old = tree["revision_id"]
    for key in ("accepted_at", "accepted_by", "generation_job_id"):
        tree.pop(key, None)
    tree["status"] = "candidate"
    tree["skill_units"] = []
    tree["mastery_criteria"] = []
    tree["diagnostic_sets"] = []
    tree["remediation_units"] = []
    tree["practice_units"] = []
    summaries = []
    lines = ["# WenCode 精修标准对照：千问教学能力补全候选", "",
             "范围：49个既有元知识点；15个能力组。原文未作语义修订，F2仅修复JSON括号。所有新增教学包整体未通过采用门槛。", ""]
    for record in records:
        key, unit, doc = record["unit_key"], record["input"], record["generated"]
        by_key = {p["key"]: p for p in unit["points"]}
        ids = [p["knowledge_id"] for p in unit["points"]]
        probes = {p["key"]: p for p in unit["probes"]}
        sid = identity("c17-teaching-v1", "skill", key)
        quality = {"reviewer": "Codex", "status": "needs_revision", "ready_for_adoption": False,
                   "issues": [{"field": f, "message": m} for f, m in FINDINGS[key]]}
        skill = {"skill_id": sid, "unit_key": key, "primary_knowledge_id": ids[0], "knowledge_ids": ids,
                 "knowledge_revision_refs": {p["knowledge_id"]: p["revision_id"] for p in unit["points"]},
                 **deepcopy(doc["skill"]), "review": quality, "generation_source": "qwen3.8-27b"}
        skill["revision_id"] = "skr_" + digest(skill)[:24]
        tree["skill_units"].append(skill)
        for c in doc["criteria"]:
            probe = probes[c["probe_key"]]
            criterion = {"criterion_id": identity(sid, "criterion", c["point_key"]), "skill_id": sid,
                         "knowledge_ids": [by_key[c["point_key"]]["knowledge_id"]],
                         "name": by_key[c["point_key"]]["name"] + "达标证据", **deepcopy(c),
                         "verification_method": "回答冻结题目并提供推理；对照正确答案与适用条件，不只比较关键词。",
                         "probe": deepcopy(probe), "answer_revision": digest(probe), "status": "candidate"}
            criterion["revision_id"] = "mcr_" + digest(criterion)[:24]
            tree["mastery_criteria"].append(criterion)
        mids = []
        for m in doc["mistakes"]:
            mid = identity(sid, "mistake", m["key"])
            mids.append(mid)
            point_ids = [by_key[k]["knowledge_id"] for k in m["point_keys"]]
            mistake = {"misconception_id": mid, "skill_id": sid, "unit_key": key, "key": key + ":" + m["key"],
                       "name": m["name"], "primary_knowledge_id": point_ids[0], "knowledge_ids": point_ids,
                       "knowledge_keys": m["point_keys"], "wrong_rule": m["wrong_rule"],
                       "observable_error_pattern": m["observable_error"], "predictions": deepcopy(m["predictions"]),
                       "discrimination": "结合区分题回答与理由核对错误规则；当前预测尚未验证，不能据此自动归因。",
                       "repair_strategy": "\n".join(m["repair_steps"]), "status": "candidate", "review_status": "needs_revision"}
            mistake["revision_id"] = "msr_" + digest(mistake)[:24]
            tree["misconceptions"].append(mistake)
            tree["remediation_units"].append({"remediation_id": identity(mid, "repair", "1"), "misconception_id": mid,
                "skill_id": sid, "knowledge_ids": point_ids, "steps": deepcopy(m["repair_steps"]), "status": "candidate"})
        tree["diagnostic_sets"].append({"diagnostic_id": identity(sid, "diagnostic", "1"), "skill_id": sid,
            "knowledge_ids": ids, "misconception_ids": mids, "probes": [deepcopy(probes[k]) for k in doc["diagnostic_probe_keys"]],
            "diagnostic_validated": False, "unknown_prediction_policy": "无预测表示未知，不是正确作答或排除证据；允许多错因共存。", "review": quality})
        tree["practice_units"].append({"practice_id": identity(sid, "practice", "1"), "skill_id": sid,
            "knowledge_ids": ids, **deepcopy(doc["practice"]), "retest": deepcopy(unit["retest"]),
            "retest_revision": digest(unit["retest"]), "status": "candidate"})
        summaries.append({"unit_key": key, "name": unit["name"], "point_count": len(ids), "structure_passed": True, **quality})
        lines += ["## " + key + " · " + unit["name"], "", "**复核：需修订，不能采用。**", ""]
        lines += ["- `" + f + "`：" + m for f, m in FINDINGS[key]]
        lines += ["", "### 能力", "", skill["observable_behavior"], "", "训练：" + skill["task"], ""]
        for c in doc["criteria"]:
            probe = probes[c["probe_key"]]
            lines += ["- **" + c["point_key"] + "**：" + c["observable_performance"],
                      "  - 检查题：" + probe["question"].replace("\n", " "), "  - 冻结答案：" + probe["answer"].replace("\n", " ")]
        lines += ["", "### 具体错因与区分预测（未验证）", ""]
        for m in doc["mistakes"]:
            lines += ["**" + m["key"] + " · " + m["name"] + "**", "", m["wrong_rule"], "", "表现：" + m["observable_error"], ""]
            lines += ["- `" + p["probe_key"] + "`：" + p["answer"] + "；理由：" + p["reason"] for p in m["predictions"]]
            lines += ["", "补救（待修订）：", ""] + ["- " + s for s in m["repair_steps"]] + [""]
        lines += ["### 迁移复测（模型调用前冻结）", "", unit["retest"]["question"], "", "正确答案：" + unit["retest"]["answer"], "", "依据：" + unit["retest"]["rationale"], ""]
    results = [read(p) for p in (root / "calls").glob("*/result.json")]
    tree["teaching_assessment"] = {"schema_version": "wencode_teaching_eval_v1", "ready_for_adoption": False,
        "review_status": "needs_revision", "knowledge_points": 49, "capability_units": 15, "criteria": 49,
        "new_mistakes": 45, "diagnostic_sets": 15, "remediation_units": 45, "transfer_tasks": 15,
        "model_calls": len(results), "model_seconds": round(sum(r.get("seconds", 0) for r in results), 2),
        "raw_parse_passed": sum(r["state"] == "completed" for r in results), "format_normalized_units": ["F2"],
        "structural_passed_units": 15, "semantic_passed_units": 0, "reviews": summaries,
        "claim_boundary": "候选教学框架已覆盖49点；新内容未达到WenCode精修语义门槛，禁止作为正式教学基线。",
        "input_limitations": ["Q-I04与Q-I07重复", "不同错因可能独立并存，不能强行作互斥三选一", "三个既有已验证诊断仍保留，新增候选未替代它们"],
        "transfer_verification": read(root / "transfer-verification.json")}
    tree["source_knowledge_revision"] = old
    tree["generation_source"] = "qwen_teaching_completion_codex_evaluated_not_semantically_rewritten"
    tree["revision_id"] = "kb_" + digest({k: v for k, v in tree.items() if k != "revision_id"})[:24]
    assert tree["knowledge_points"] == read(root / "source-tree.json")["knowledge_points"]
    assert {i for c in tree["mastery_criteria"] for i in c["knowledge_ids"]} == {p["knowledge_id"] for p in tree["knowledge_points"]}
    destination.mkdir(parents=True, exist_ok=True)
    save(root / "teaching-candidate-tree.json", tree)
    save(destination / "知识树教学补全候选.json", tree)
    save(destination / "千问原始教学候选.json", records)
    save(destination / "逐组复核.json", tree["teaching_assessment"])
    (destination / "逐组复核与教学候选.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print({k: v for k, v in tree["teaching_assessment"].items() if k not in {"reviews", "transfer_verification"}})


if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);p.add_argument("destination",type=Path);a=p.parse_args();export(a.root,a.destination)
