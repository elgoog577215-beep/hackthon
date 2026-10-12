"""Freeze a controlled follow-up using the production shared context adapter."""
from pathlib import Path
import sys
import argparse
from copy import deepcopy
from .pipeline import read, save, digest

APP = Path(__file__).resolve().parents[2]
MODES = {"python":"programming_engineering", "calculus":"math_formal", "physics":"natural_science", "history":"humanities_social"}


def fixture_course(fixture):
    from course_knowledge_context import documents_from_text_sources
    cid = "context-trial-" + fixture["key"]
    docs, bindings = documents_from_text_sources(cid, fixture["materials"])
    return {"course_id":cid, "course_name":fixture["title"], "generation_request_revision":1,
        "generation_request":{"subject":fixture["title"], "requirements":fixture["profile"],
            "pedagogy_mode":MODES.get(fixture["key"],"auto"), "course_intent":{"learning_goal":fixture["title"]}},
        "knowledge_scope_units":[{"node_id":fixture["key"], "title":fixture["title"],
            "learning_objective":fixture["title"], "scope_boundary":fixture["profile"]}],
        "parsed_documents":docs,"material_bindings":bindings}


def prepare(root, baseline):
    if (root/"manifest.json").exists():raise ValueError("comparison_already_frozen")
    sys.path.insert(0,str(APP/"backend"))
    from course_knowledge_context import build_knowledge_generation_context, knowledge_context_prompt
    old=read(baseline/"manifest.json")
    assert all(digest(read(baseline/n))==h for n,h in old["input_hashes"].items())
    fixtures=read(baseline/"fixtures.json");prompts=read(baseline/"prompts.json")
    save(root/"fixtures.json",fixtures);save(root/"prompts.json",prompts)
    contexts={}
    for c in fixtures + [{"key":"unknown","title":"组织行为学","profile":"未知学段与范围","materials":[]}]:
        course=fixture_course(c)
        context=build_knowledge_generation_context(course)
        save(root/"source-courses"/(c["key"]+".json"),course)
        contexts[c["key"]]=knowledge_context_prompt(context)
    save(root/"shared-contexts.json",contexts)
    save(root/"eval.json", {**read(baseline/"eval.json"), "baseline_root":str(baseline),
        "controlled_inputs":"材料、题库、复测、system/tree/teaching提示词及模型参数与上一轮一致；新增共享上下文",
        "changed_inputs":["已声明的学科主模式（按实验课程类型指定）","原教学模块/质量提示","原范围合同","原证据编译与冻结包及引用映射"],
        "not_isolated_effect":"同时增加多个上游上下文字段；单次顺序试跑，不可将差异因果归于某一个字段或宣称稳定提升",
        "semantic_axes":["知识粒度","课程针对性与条件","题目实际考点与参数绑定","错因预测与区分逻辑"],
        "repaired_model_content":False,"production_course_mutation":False})
    names=["fixtures.json","prompts.json","eval.json","shared-contexts.json"]
    save(root/"manifest.json",{"model_calls_max":9,"baseline_inputs":{"fixtures":digest(fixtures),"prompts":digest(prompts)},
        "input_hashes":{n:digest(read(root/n)) for n in names}})
    print("Frozen shared contexts",[(k,c['subject_pedagogy_profile']['primary_mode'],len(c['evidence_package']['units'])) for k,c in contexts.items()])


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);p.add_argument("baseline",type=Path);a=p.parse_args();prepare(a.root,a.baseline)
