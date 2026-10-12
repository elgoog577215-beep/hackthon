"""Build frozen, small Qwen jobs for the reviewed-core experiment."""
from pathlib import Path
import argparse
import hashlib
from .pipeline import read,save
from .diagnostic_templates import FAMILIES

CHECK_PROMPT = """为输入的每一个知识点生成一条独立的概念检查。核心命题已经校正，不得修改。
每点恰好一条，point_id原样返回；不得合并多个点。最多六点，全部完成。
检查应能判断学生是否理解该点。问题中写明必要条件；答案简短、唯一可判定；不要在解释中先写错答案再自我修正。
本轮只生成静态概念题，不生成待执行程序；可使用简短C表达式或语句说明问题，避免复杂计算、平台假设和未定义行为求输出。
必须直接测试目标规则，不能只问概念名字，也不能引用该点但实际测试别的知识。
例如“赋值接收类型会否改变右侧运算类型”必须设置有该接收类型的题；测试改值后判断必须确实存在状态变化。
只输出 {"items":[{"point_id":"输入ID","question":"问题","answer":"正确回答","rationale":"简短理由","tests_target":"该题如何直接检查这个点"}]}。
不得写其他字段或Markdown围栏。仅输出最后确定的答案，不输出思考过程。"""

DIAG_PROMPT = """根据输入的已审阅诊断家族，为本课生成一套具体实例的参数。
两种错误信念和代码模板已经固定，不能改变假设、自行写代码或编造预测答案；预测将由程序执行正确代码和错因模拟代码取得。
选择易读的小整数，严格满足parameter_contract。返回
{"family":"给定family原值","parameters":{给定参数名:整数,...},"teaching_note":"一句说明如何引导学生比较共同表现、区分题和复测，不写数值答案或断言真实学生错因"}。
只输出JSON，不添加其他字段。"""

REL_PROMPT = """从给定知识点中选取确有教学价值的少量关系，可为空；不要为凑数量而连边。
只允许contrasts_with（两规则对比）或prerequisite（先修→后学）。语法配对不依赖运行真假；int/double转换不以整数提升为required前置。
不要声称高频错误或学生普遍混淆。未知confidence由程序置null；strength仅0.3/0.6/1.0；necessity仅prerequisite用required/recommended，否则null。
端点仅用真实点ID，不能返回父分类或已退役节点。
返回 {"relations":[{"key":"r1","source_id":"ID","target_id":"ID","type":"contrasts_with","necessity":null,"strength":0.6,"reason":"具体依据","context":"教学任务","distinction":"关键差异","derivation_steps":[]}]}。
最多三条。只输出JSON，简短说明，不写思考过程。"""


def build_jobs(root):
    jobs=[]
    for topic in ("types","if","for"):
        core=read(root/topic/"corrected-core.json")
        for index in range(0,len(core["points"]),6):
            jobs.append({"id":f"{topic}-checks-{index//6+1}","topic":topic,"kind":"checks","max_tokens":5000,
                "instruction":CHECK_PROMPT,"input":{"course":"C17基础程序设计，初学者","points":core["points"][index:index+6]}})
        jobs.append({"id":topic+"-diagnostic","topic":topic,"kind":"diagnostic","max_tokens":1500,
            "instruction":DIAG_PROMPT,"input":FAMILIES[topic]})
        jobs.append({"id":topic+"-relations","topic":topic,"kind":"relations","max_tokens":3000,
            "instruction":REL_PROMPT,"input":{"points":[{k:p[k] for k in ("id","name","statement","conditions")} for p in core["points"]]}})
    save(root/"jobs.json",jobs)
    save(root/"protocol.json",{"version":"v4-reviewed-core-small-batches-counterfactual-diagnostics",
        "frozen_before_calls":True,"max_model_calls":len(jobs)+3,"initial_jobs":len(jobs),"max_targeted_repairs_per_topic":1,
        "model":"existing qwen3.8-27b","thinking":False,"attempts_per_call":1,
        "provenance":"Core explicitly corrected by Codex from v3. Qwen generates per-point checks, diagnostic parameters and relations; not an unassisted generation benchmark.",
        "acceptance":{"coverage":"all original 34 units plus every source fact addressed","atomicity":"no unresolved compound point; applications separate",
          "correctness":"no known factual or answer errors","checks":"every point has a separately reviewed aligned check",
          "diagnostics":"3/3 reviewed wrong-belief models generate shared wrong symptom and distinct diagnostic predictions; fresh retest",
          "relations":"all retained relations independently reviewed; bad ones cannot be called accepted",
          "evidence":"all correct and counterfactual diagnostic programs compiled/run O0/O2 with exact hashes",
          "scope":"three-topic experimental content baseline only, not a complete course, teacher adoption or production release"},
        "holdouts":"Previous holdout_probes.json is never included in jobs. Template boundary regressions are new code tests, not model answer accuracy."})
    frozen=[root/"fixtures.json",root/"eval_definition.json",root/"holdout_probes.json",root/"jobs.json",root/"protocol.json",root/"compiler-environment.json"]
    frozen += [root/t/"corrected-core.json" for t in ("types","if","for")]
    save(root/"manifest.json",{"input_hashes":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen},"model_calls_max":len(jobs)+3})
    print("Prepared",len(jobs),"initial jobs and up to 3 targeted repairs")


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("root",type=Path)
    build_jobs(parser.parse_args().root)
