"""Reviewed C17 misconception families. Qwen chooses parameters, never truth.

Counterfactual programs encode a stipulated erroneous learner rule. Their outputs
are predictions under that rule, NOT alternate correct interpretations of C.
"""
from .pipeline import Rejected, identity, digest

FAMILIES = {
    "types": {
        "family": "integer_division_receiver_v1",
        "hypothesis_a": "误以为两个int的除法也保留数学上的小数商。",
        "hypothesis_b": "知道int除法会截断，但误以为左侧double接收变量会反向把右侧int除法变成浮点除法。",
        "repair_a": "先判定运算操作数类型：两个int相除在有定义时得到向零截断的整数商；需要小数时先转换一个操作数。",
        "repair_b": "区分右侧表达式求值与接收转换：左侧double只转换已经算出的值，不会恢复已丢弃的小数。",
        "parameter_contract": "n,d为正整数；2<=d<n<=30；n不能被d整除；retest_n/retest_d也满足同样约束且与n/d不是同一对。",
    },
    "if": {
        "family": "dangling_else_indentation_v1",
        "hypothesis_a": "误以为else与视觉上缩进同列的if配对，而不是由C语法决定。",
        "hypothesis_b": "误以为无花括号嵌套if中的else总与最外层if配对。",
        "repair_a": "忽略缩进提示，按语法允许的最近if配对；再用花括号明确期望边界。",
        "repair_b": "先识别内层完整if/else结构；外层不进入时，内层if和else都不执行。",
        "parameter_contract": "initial、then_value、else_value、retest_initial均为0..20整数；四个数彼此不同。",
    },
    "for": {
        "family": "continue_exit_or_skip_update_v1",
        "hypothesis_a": "误以为continue等同于break，遇到后直接退出整个for，不再更新。",
        "hypothesis_b": "误以为continue只跳过本轮剩余循环体和第三部分更新，直接回到条件判断。",
        "repair_a": "continue不会结束整个循环；用执行轨迹确认它仍会执行for第三部分，随后判断条件。",
        "repair_b": "把for更新位置显式画在continue之后：只有break退出该for才跳过该次更新。",
        "parameter_contract": "3<=limit<=8；1<=trigger<=limit-2；retest_limit比limit大1且<=9。模板会在触发continue前合法改变i以保证每个错误模拟也能终止。",
    },
}


def validate_parameters(topic, params):
    expected = {"types": {"n", "d", "retest_n", "retest_d"},
                "if": {"initial", "then_value", "else_value", "retest_initial"},
                "for": {"limit", "trigger", "retest_limit"}}[topic]
    if not isinstance(params, dict) or set(params) != expected or any(type(v) is not int for v in params.values()):
        raise Rejected("diagnostic_parameter_schema")
    if topic == "types":
        pairs = [(params["n"], params["d"]), (params["retest_n"], params["retest_d"])]
        if not all(2 <= d < n <= 30 and n % d for n, d in pairs) or pairs[0] == pairs[1]:
            raise Rejected("division_parameters_do_not_discriminate")
    elif topic == "if":
        if not all(0 <= v <= 20 for v in params.values()) or len(set(params.values())) != 4:
            raise Rejected("if_values_do_not_discriminate")
    elif not (3 <= params["limit"] <= 8 and 1 <= params["trigger"] <= params["limit"] - 2 and params["retest_limit"] == params["limit"] + 1):
        raise Rejected("loop_parameters_not_bounded")


def _if_code(a, b, initial, yes, no, indent, pairing="correct"):
    declarations = f"int a={a}, b={b}, v={initial};\n"
    if pairing == "outer":
        body = f"if(a) {{\n  if(b) v={yes};\n}} else v={no};\n"
    else:
        body = f"if(a)\n  if(b) v={yes};\n{indent}else v={no};\n"
    return declarations + body + 'printf("%d\\n",v);'


def _for_code(limit, trigger, jump, belief="correct"):
    if belief == "b":
        return (f"int i=0, hits=0;\nfor(;i<{limit};) {{\n hits++;\n"
                f" if(i=={trigger}) {{i={jump}; continue;}}\n i++;\n}}\n" + 'printf("%d %d\\n",i,hits);')
    transfer = "break" if belief == "a" else "continue"
    return (f"int i=0, hits=0;\nfor(;i<{limit};i++) {{\n hits++;\n"
            f" if(i=={trigger}) {{i={jump}; {transfer};}}\n}}\n" + 'printf("%d %d\\n",i,hits);')


def build_diagnostic(topic, params, knowledge_ids, scope):
    validate_parameters(topic, params)
    programs = {}
    if topic == "types":
        n, d, rn, rd = (params[k] for k in ("n", "d", "retest_n", "retest_d"))
        programs["symptom"] = {
            "correct": f'double x={n}/{d}; printf("%.2f\\n",x);',
            "a": f'double x=(double){n}/{d}; printf("%.2f\\n",x);',
            "b": f'double x=(double){n}/{d}; printf("%.2f\\n",x);'}
        direct = f'printf("%.2f\\n",(double)({n}/{d}));'
        programs["diagnostic"] = {"correct": direct, "a": f'printf("%.2f\\n",(double){n}/{d});', "b": direct}
        programs["retest"] = {"correct": f'printf("%.2f %.2f\\n",(double)({rn}/{rd}),(double){rn}/{rd});',
            "a": f'printf("%.2f %.2f\\n",(double){rn}/{rd},(double){rn}/{rd});',
            "b": f'printf("%.2f %.2f\\n",(double)({rn}/{rd}),(double){rn}/{rd});'}
    elif topic == "if":
        initial, yes, no, ri = (params[k] for k in ("initial", "then_value", "else_value", "retest_initial"))
        for role, a, b, value, indent in (("symptom",1,0,initial,""),("diagnostic",1,0,initial,"  "),("retest",0,0,ri,"")):
            correct = _if_code(a,b,value,yes,no,indent)
            outer = _if_code(a,b,value,yes,no,indent,"outer")
            programs[role] = {"correct":correct,"a":outer if indent=="" else correct,"b":outer}
    else:
        limit, trigger, rl = (params[k] for k in ("limit","trigger","retest_limit"))
        for role, boundary, jump in (("symptom",limit,limit),("diagnostic",limit,trigger+1),("retest",rl,rl)):
            programs[role] = {belief:_for_code(boundary,trigger,jump,belief) for belief in ("correct","a","b")}
    checks, roles = [], {}
    for role, versions in programs.items():
        roles[role] = {}
        for belief, code in versions.items():
            key = f"diag_{topic}_{role}_{belief}"
            check = {"id":identity(scope,"check",key),"key":key,"knowledge_ids":knowledge_ids,
                "kind":"runtime","question":"预测此完整代码的标准输出。" if belief=="correct" else "错误信念的反事实模拟；不是正确C语义。",
                "code":code,"sample_return_type":"void","predicted_stdout":"",
                "explanation":"输出由编译执行回执绑定，不使用模型提供的数值答案。",
                "platform_assumptions":[],"origin":"reviewed_diagnostic_template",
                "counterfactual":belief!="correct","semantic_status":"reviewed_template"}
            checks.append(check)
            roles[role][belief] = check["id"]
    return {"family":FAMILIES[topic]["family"],"parameters":params,"knowledge_ids":knowledge_ids,
        "hypothesis_a":FAMILIES[topic]["hypothesis_a"],"hypothesis_b":FAMILIES[topic]["hypothesis_b"],
        "repair_a":FAMILIES[topic]["repair_a"],"repair_b":FAMILIES[topic]["repair_b"],
        "origin":"codex_reviewed_hypothesis_family_with_qwen_selected_parameters",
        "checks":checks,"roles":roles,"template_semantics_reviewed":True}


def grade_diagnostic(plan, receipts):
    by_id = {r["check_id"]:r for r in receipts}
    from .pipeline import code_hash
    by_check = {c["id"]:c for c in plan["checks"]}
    observations, problems = {}, []
    for role, variants in plan["roles"].items():
        observations[role] = {}
        for belief, cid in variants.items():
            r = by_id.get(cid)
            if not r or r.get("status")!="executed" or r.get("returncode")!=0 or r.get("optimization_agrees") is not True or r.get("code_hash")!=code_hash(by_check[cid]):
                problems.append(f"unverified:{role}:{belief}")
            else:
                observations[role][belief] = {"value":r["stdout"],"check_id":cid,"receipt_hash":digest(r),"code_hash":r["code_hash"]}
    if not problems:
        values = {role:{belief:item["value"].split() for belief,item in obs.items()} for role,obs in observations.items()}
        s, d = values["symptom"], values["diagnostic"]
        if not (s["a"]==s["b"] and s["a"]!=s["correct"]): problems.append("not_shared_wrong_prediction")
        if d["a"]==d["b"]: problems.append("not_discriminating")
        if plan["roles"]["retest"]["correct"]==plan["roles"]["diagnostic"]["correct"]: problems.append("reused_retest")
    return {"observations":observations,"problems":problems,"numeric_contract_passed":not problems,
            "scope":"只验证给定错误模型和样本的逻辑可区分性，不证明真实学生持有这些信念或诊断有效率。"}
