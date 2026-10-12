"""Keep the Qwen-only result and the explicitly edited sample separately."""
from copy import deepcopy
from pathlib import Path
import argparse
from .pipeline import read,save,digest
from .round4_prepare import apply_repairs


def finalize(root):
    for topic in ("types","if","for"):
        base=read(root/topic/"initial.json")
        model=apply_repairs(base,read(root/"calls"/(topic+"-repair")/"parsed.json"),read(root/topic/"repair-scope.json"))
        save(root/topic/"qwen-candidate.json",model)
        final=deepcopy(model);edits=[]
        final["core"].pop("pending_checks",None)
        by_name={p["name"]:p for p in final["core"]["points"]}
        by_id={c["point_id"]:c for c in final["primary_checks"]}
        if topic=="for":
            check=by_id[by_name["每次入体前判断条件"]["id"]]
            old=deepcopy(check)
            check["rationale"]="正常完成循环体后先执行第三部分，再重新求值控制表达式；条件非零才再次进入循环体。不能把入体说成发生在再次判断之前。"
            edits.append({"collection":"primary_checks","id":check["point_id"],"before":old,"after":deepcopy(check),
                "reason":"千问修正仍把重新判断和入体的顺序说反；由Codex明确修正，不计入千问自动成功。"})
            for name,extra in {
                "有符号最大值后的迭代溢出":"执行第三部分i++之前，i仍等于INT_MAX；循环体没有把它改为其他值。",
                "switch 内 continue 的目标":"最内层包围该continue的循环是所述for，没有更内层循环；第三部分非空。",
                "break 退出机制":"break退出最内层包围它的循环或switch；本点讨论实际退出所述for的路径。"
            }.items():
                point=by_name[name];old=deepcopy(point);point["conditions"].append(extra)
                edits.append({"collection":"points","id":point["id"],"before":old,"after":deepcopy(point),"reason":"收紧原有规则适用情境，避免忽略循环体改值或更内层包围结构。"})
            final["core"]["applications"][0].update(
                answer="没有更内层包围结构时，内层for的continue执行该内层for的第三部分再判断；break结束内层for，并从其后的语句继续。二者均不自动转移或结束外层for。",
                conditions=["普通结构化控制流", "没有更内层循环或switch改变跳转目标"],
                provenance="Codex明确的应用题答案，不计为千问输出")
        for point in final["core"]["points"]:
            check=by_id[point["id"]]
            check["conditions"]=deepcopy(point["conditions"])
            check["origin"]="qwen_generated_with_codex_review" if not any(e["collection"]=="primary_checks" and e["id"]==point["id"] for e in edits) else "qwen_generated_then_codex_corrected"
            if point["name"]=="头部声明的作用域":check["conditions"].append("片段位于合法函数体、已包含stdio.h，外层没有另一个名为i的声明。")
            if point["name"]=="return 结束机制":check["conditions"].append("题中return;位于返回类型为void的函数中。")
            if point["name"]=="独立 if 可以多次命中":check["conditions"].append("a、b、x、y已正确声明初始化，所有自增有定义。")
            if point["name"]=="后续 if 读取新状态":check["conditions"].append("代码片段中的y事先声明为int。")
        final["editorial_provenance"]={"reviewer":"Codex, nonblind; not a course teacher","edits":edits,
            "additional_context":"每题附知识核心的适用条件；作用域、return及简写片段另补明确的声明/函数上下文。"}
        save(root/topic/"editorial-corrections.json",final["editorial_provenance"])
        save(root/topic/"final.json",final)
        print(topic,len(final["primary_checks"]),"known model error corrected",sum(e["collection"]=="primary_checks" for e in edits))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("root",type=Path)
    finalize(parser.parse_args().root)
