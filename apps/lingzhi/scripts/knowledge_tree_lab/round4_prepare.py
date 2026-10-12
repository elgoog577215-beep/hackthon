"""Strict per-target intake plus executable diagnostic preparation for v4."""
from pathlib import Path
import argparse
from copy import deepcopy
from .pipeline import read,save,digest,identity,Rejected,compile_teaching,code_hash
from .diagnostic_templates import FAMILIES,build_diagnostic,grade_diagnostic
from .compiler import run_checks

CHECK_KEYS={"point_id","question","answer","rationale","tests_target"}


def intake_checks(expected_ids, payload):
    if not isinstance(payload,dict) or set(payload)!={"items"} or not isinstance(payload["items"],list):
        raise Rejected("check_batch_schema")
    expected=set(expected_ids);seen=set();accepted={};errors=[]
    for index,item in enumerate(payload["items"]):
        pid=item.get("point_id") if isinstance(item,dict) else None
        if not isinstance(item,dict) or set(item)!=CHECK_KEYS or not all(isinstance(v,str) and v.strip() for v in item.values()):
            errors.append({"index":index,"point_id":pid,"reason":"check_fields"});continue
        if pid not in expected:
            errors.append({"index":index,"point_id":pid,"reason":"out_of_scope"});continue
        if pid in seen:
            accepted.pop(pid,None)
            errors.append({"index":index,"point_id":pid,"reason":"duplicate_target"});continue
        seen.add(pid);accepted[pid]=deepcopy(item)
    return accepted,errors+[{'point_id':pid,'reason':'missing_check'} for pid in sorted(expected-set(accepted))]


def prepare(root, gcc):
    jobs=read(root/"jobs.json")
    for topic in ("types","if","for"):
        core=read(root/topic/"corrected-core.json")
        checks={};errors=[]
        for job in jobs:
            if job["topic"]!=topic or job["kind"]!="checks":continue
            parsed=read(root/"calls"/job["id"]/"parsed.json")
            batch,issues=intake_checks([p["id"] for p in job["input"]["points"]],parsed)
            checks.update(batch);errors.extend(issues)
        raw_relations=read(root/"calls"/(topic+"-relations")/"parsed.json")
        structural,receipts=compile_teaching(core,{"checks":[],"misconceptions":[],"relations":raw_relations.get("relations",[])})
        draft={"core":core,"primary_checks":list(checks.values()),"check_intake_errors":errors,
               "relations":structural["relations"],"raw_relations":raw_relations.get("relations",[]),
               "relation_structure":receipts}
        selected=read(root/"calls"/(topic+"-diagnostic")/"parsed.json")
        if set(selected)!={"family","parameters","teaching_note"} or selected["family"]!=FAMILIES[topic]["family"]:
            raise Rejected("diagnostic_selection_schema")
        names={
            "types":["整数除法截断","接收类型不反向改变表达式","显式转换的位置"],
            "if":["else 的词法就近配对","缩进不改变语法归属","未进入外层则不执行内层"],
            "for":["continue 的执行逻辑","break 退出机制","循环体修改变量"]}[topic]
        refs=[p["id"] for p in core["points"] if p["name"] in names]
        assert len(refs)==len(names)
        plan=build_diagnostic(topic,selected["parameters"],refs,core["scope"])
        plan["model_teaching_note"]=selected["teaching_note"]
        save(root/topic/"diagnostic-plan.json",plan)
        # Only reviewed, typed templates reach execution. Model cannot supply code.
        approvals=[code_hash(c) for c in plan["checks"]]
        save(root/topic/"execution-approvals.json",{"approved_hashes":approvals,
            "basis":"Codex-reviewed finite templates; typed integer bounds and distinct outcomes validated. Not a sandbox for arbitrary model C."})
        evidence=run_checks({"checks":plan["checks"]},gcc,root/topic/"diagnostic-code",approvals,read(root/"compiler-environment.json"))
        grade=grade_diagnostic(plan,evidence)
        save(root/topic/"diagnostic-grade.json",grade)
        draft["diagnostic"]={"plan":plan,"grade":grade}
        save(root/topic/"initial.json",draft)
        print(topic,"checks",len(checks),"intake errors",len(errors),"diagnostic",grade["numeric_contract_passed"],"relation structures",receipts,flush=True)


def apply_repairs(base, payload, scope):
    """Program owns check identity; additions only for explicitly missing targets."""
    if payload.get("base_hash")!=digest(base):raise Rejected("stale_repair")
    if set(payload)-{"base_hash","checks","relations","unresolved"}:raise Rejected("repair_fields")
    values,errors=intake_checks(scope["point_ids"],{"items":payload.get("checks",[])})
    if errors:raise Rejected("repair_checks:"+str(errors))
    result=deepcopy(base)
    existing={c["point_id"]:c for c in result["primary_checks"]}
    existing.update(values)
    result["primary_checks"]=list(existing.values())
    # The explicitly authorized relation batch may be revised or removed.
    if scope.get("relations"):
        relations=payload.get("relations")
        if not isinstance(relations,list):raise Rejected("repair_relations_missing")
        allowed=set(scope["relation_keys"])
        if any(not isinstance(r,dict) or r.get("key") not in allowed for r in relations):raise Rejected("relation_scope_escape")
        doc,receipt=compile_teaching(result["core"],{"relations":relations,"checks":[],"misconceptions":[]})
        if any(r["status"]=="rejected" for r in receipt):raise Rejected("invalid_repaired_relations")
        result["relations"]=doc["relations"]
        result["relation_structure"]=receipt
    elif payload.get("relations"):
        raise Rejected("relations_not_authorized")
    result["repair_unresolved"]=payload.get("unresolved",[])
    result["check_intake_errors"]=[] if {c["point_id"] for c in result["primary_checks"]}=={p["id"] for p in result["core"]["points"]} else base["check_intake_errors"]
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("root",type=Path);parser.add_argument("--gcc",required=True)
    args=parser.parse_args();prepare(args.root,args.gcc)
