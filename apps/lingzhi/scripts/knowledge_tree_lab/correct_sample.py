"""Explicit Codex-authored corrections to the v3 sample, NOT Qwen output.

Use only on the three frozen experimental topics. No live course writes.
"""
from copy import deepcopy
from pathlib import Path
import argparse
from .pipeline import read, save, digest, apply_intents


def correct_sample(previous, destination):
    fixtures = read(destination / "fixtures.json")
    criteria = read(destination / "eval_definition.json")["coverage_criteria"]
    for topic in fixtures["topics"]:
        name = topic["id"]
        base = read(previous / name / "final.json")
        points = {p["name"]: p for p in base["points"]}
        cats = {c["id"]: c for c in base["categories"]}
        replacements, additions = {}, []

        def unit(old, title, claim, conditions, question, answer, refs=None, coverage=None):
            p = points[old]
            path, cid = [], p["parent_id"]
            while cats[cid]["parent_id"]:
                path.insert(0, cats[cid]["name"])
                cid = cats[cid]["parent_id"]
            return {"path": path, "name": title, "statement": claim,
                    "conditions": conditions, "question": question, "answer": answer,
                    "source_refs": refs or p["source_refs"], "coverage_ids": coverage or p["coverage_ids"],
                    "stop_reason": "一个可单独检查的规则；适用条件保留在规则内，不按具体数值继续拆分。"}

        def revise(old, claim, conditions, question, answer, title=None):
            replacements[old] = [unit(old, title or old, claim, conditions, question, answer)]

        if name == "types":
            revise("无符号后缀", "整数字面量 1U 的类型是 unsigned int。", ["C17", "本点讨论值为1的U后缀字面量，不推广到任意大的U后缀常量"],
                   "字面量1U的类型是什么？", "unsigned int。", "1U 的类型")
            revise("整数提升规则", "需要整数提升时，若 int 可表示原整数类型全部值，则提升为 int，否则为 unsigned int。",
                   ["C17中需要整数提升的场合", "原类型满足整数提升的适用条件；不把该步骤推广到所有混合浮点运算"],
                   "在需要整数提升的运算中，若int不能表示unsigned short的全部值，unsigned short提升为什么？", "unsigned int。")
            revise("浮点优先转换", "本课的 int 与 double 操作数进行通常算术转换时，int 操作数转换为 double。",
                   ["实数算术操作数分别为int和double", "运算有定义", "本点不描述其他有符号/无符号类型组合"],
                   "int与double相除时，转换后的共同算术类型是什么？", "double。", "int 与 double 的共同类型")
            revise("赋值求值顺序", "普通标量初始化或简单赋值把右侧表达式的值转换为目标类型；目标类型不会反向改变右侧子表达式的运算类型。",
                   ["C17普通标量初始化或简单赋值", "右侧表达式及转换有定义", "不主张赋值左右操作数固定先右后左求值"],
                   "double x=5/2中的double目标类型会把5/2本身变成浮点除法吗？", "不会。先得到int商2，再转换保存为double值2.0。", "接收类型不反向改变表达式")
            old = "转换作用域"
            replacements[old] = [
                unit(old, "显式转换的位置", "显式转换只作用于语法上指定的操作数；转换发生位置决定它在算术运算之前还是之后。",
                     ["C17算术转换", "表达式求值有定义"], "(double)5/2中的显式转换首先作用于哪个操作数？",
                     "只作用于5，随后除法按double计算；(double)(5/2)则在整数除法完成后转换其结果。"),
                unit(old, "转换表达式不改原变量", "读取变量并显式转换所得值，本身不会修改该变量的声明类型或存储值。",
                     ["操作数只是读取变量", "排除赋值、自增、函数调用等另带副作用的操作数"],
                     "int n=5;单独求值(double)n后，n的类型和值会改变吗？", "不会，n仍是int，存储值仍为5。")]
            revise("模转换", "整数转换为无符号整数类型时，结果与原整数模目标最大值加一同余，并落在目标类型范围内。",
                   ["源值为整数", "目标为非_Bool无符号整数类型", "不用于浮点转整数"],
                   "把整数-1转换为unsigned int，是否必须假设unsigned int是32位才能确定结果？", "不必，结果总是UINT_MAX。")
            revise("浮点越界", "有限实浮点值转非_Bool整数时，向零截断后的整数部分若不能由目标类型表示，行为未定义。",
                   ["源值有限", "目标为非_Bool整数类型", "按目标实际上下界判断整数部分，不对其取绝对值"],
                   "(unsigned int)-1.5能像整数-1转换那样使用取模规则吗？", "不能。截断后的-1不在unsigned int范围内，转换行为未定义。")
            revise("整数到浮点", "整数转实浮点时，目标数值范围足够并不保证精确，有限有效精度可能造成信息损失。",
                   ["整数在目标浮点数值范围内", "不假设所有C实现的double有效精度或舍入方式相同"],
                   "仅知道某整数在double的数值范围内，能否保证转换后精确不变？", "不能，还必须判断该整数能否由目标浮点格式精确表示。")
            revise("int与unsigned int的通常算术转换方向", "int与unsigned int进行通常算术转换时，int操作数转换为unsigned int。",
                   ["两操作数分别为int与unsigned int，二者转换秩相同", "不推广为任意有符号与无符号类型组合"],
                   "比较int值-1与unsigned int值1时，-1会先转换成哪种类型？", "unsigned int，转换值为UINT_MAX。")
            additions.append(unit("有符号越界", "可表示整数转换保持数值", "整数转换到另一整数类型，若目标类型能表示原值，则数值不变。",
                ["源值为整数", "目标整数类型能表示该值"], "整数100转为能够表示100的short，会改变数值吗？", "不会，数值仍为100。", ["T-S3"], ["T09"]))
        elif name == "if":
            revise("if 语句的静态分支决策", "一次普通顺序执行的if依据当时条件选择分支；分支内改变量不会自动改选或补执行另一个分支。",
                   ["普通结构化控制流", "不讨论goto跳入分支"], "if(x){x=0;}else{y=1;}中，真分支将x改成0会立即补执行else吗？", "不会。", "一次执行不重新选分支")
            revise("分支体的语句范围", "if每个分支体在语法上是一条语句；复合语句或整个嵌套if均可充当这条语句。",
                   ["普通结构化控制流"], "if(a) x=1; y=2;中，if的真分支体包含y=2吗？", "不包含，真分支体只是x=1。")
            revise("复合块对执行路径的截断", "外层if未选中包含内层if/else的分支时，整个内层选择语句都不执行。",
                   ["普通结构化控制流，无goto或标签跳入", "内层选择语句是外层该分支的一部分，不以花括号为必要条件"],
                   "a=0时，if(a) if(b) x=1; else x=2;会执行内层else吗？", "不会；外层未进入，整个内层if/else不执行。", "未进入外层则不执行内层")
            revise("else 的词法就近配对", "else结合到语法允许的、词法上最近的前面的if。",
                   ["完整合法的C17语句结构", "语法允许包含花括号边界，不能只机械找最近文本"],
                   "if(a) if(b) x=1; else x=2;中的else属于哪个if？", "内层if(b)。")
            revise("花括号显式修改 else 归属", "内层if位于外层真分支的复合语句内时，该复合语句之后的else不能跨越块边界与内层if配对。",
                   ["特指if(a){if(b) x=1;} else x=2;中块外的else", "不把块内另一个else也说成属于外层"],
                   "if(a){if(b) x=1;} else x=2;中的块外else属于哪个if？", "外层if(a)。")
            old="else if 的短路执行特性"
            replacements[old]=[
                unit(old,"else if 的语法结构","else if在C语法上是else分支中嵌套另一条if语句。",["C17语法"],"else if是独立的C关键字组合语句种类吗？","不是，它是else分支中的另一条if。"),
                unit(old,"选择链首命中后停止判断","普通顺序执行if/else-if链时，首个命中分支之后不再求值后续分支条件。",["一条if/else-if选择链", "普通结构化执行"],"if(A)...else if(B)...中A为真时，还会求值B吗？","不会。")]
            old="独立 if 的状态敏感性"
            replacements[old]=[
                unit(old,"独立 if 可以多次命中","多个独立if各自进行条件判断，前一个命中不阻止后一个也命中。",["顺序执行到各if", "无提前return等跳转"],"if(a) x++; if(b) y++;在a、b都为真时，两条自增能否都执行？","能，因为这是两条独立if。"),
                unit(old,"后续 if 读取新状态","后续独立if在自己求值时读取变量的当前值，能看到前面语句已完成的修改。",["普通顺序执行", "变量已初始化，修改及读取有定义"],"int x=1; if(x)x=0; if(x)y=1;第二条if的条件为真吗？","为假，第二次求值读到x=0。")]
            additions.append(unit("else 的词法就近配对","缩进不改变语法归属","只改变空白缩进，不改变C语句的词法记号及语法结构，因此不改变else归属。",
                ["不改变记号、花括号和注释内容", "普通if/else语句"],"把else视觉上缩进到外层if同一列，能改变合法程序中的配对吗？","不能，配对由语法决定。",["I-S2"],["I04"]))
        else:
            revise("初始化子句执行频次","每次从for入口正常进入时，初始化子句执行一次，不在该次循环的每轮开始时重复。",
                   ["普通顺序进入for", "初始化子句非空"],"同一次for执行了三轮循环体，初始化子句执行几次？","一次。")
            revise("循环体修改变量","循环体对控制变量的合法修改会影响随后更新、判断和实际入体的取值。",
                   ["变量可修改且已初始化", "各次运算有定义"],"for(int i=0;i<5;i++){记录入体i; i+=2;}的入体i有哪些？",
                   "只有0和3；第二轮结束更新到6，因条件为假不再入体。")
            revise("无符号变量倒序终止失败","unsigned int变量始终非负，因此i>=0恒真，不能让该类型的倒序循环通过此条件退出。",
                   ["i类型为unsigned int", "终止判断是i>=0", "不把i!=0等其他判断也判成无效"],
                   "unsigned int i的i>=0能在i递减后变假吗？","不能。无符号零再减一会按模回绕，回绕本身不是未定义行为。")
            revise("switch 内 break 的作用域","for体内switch中的break若最内层可退出结构是该switch，则只结束switch，随后继续执行switch之后的循环体语句。",
                   ["break未被更内层循环或switch包围", "普通结构化执行"],"for体内switch中的break会跳过switch后面的全部循环体语句直接去i++吗？","不会；先从switch后的语句继续，之后的行为取决于实际控制流。")
            old="for 头部部分的省略语义"
            replacements[old]=[
                unit(old,"省略初始化使用已有状态","省略for初始化子句不会重新赋初值，循环从已有合法状态开始。",["所读取变量已正确初始化"],"int i=2; for(;i<3;i++){}开始判断时i是多少？","2。",["F-S2"],["F06"]),
                unit(old,"省略条件视为真","for省略控制表达式时，按非零常量处理。",["C17 for语句"],"for(;;)会自动补上某个变量上限条件吗？","不会，省略的条件按非零常量处理。",["F-S2"],["F06"]),
                unit(old,"省略迭代不自动更新","省略for第三部分表示没有该处的迭代表达式，不会自动添加递增。",["状态仍可能由循环体等位置更新"],"for(;i<3;)会自动执行i++吗？","不会。",["F-S2"],["F06"]),
                unit(old,"for头部保留两个分号","for头部三部分即使省略，分隔它们的两个分号仍须保留。",["C17 for语法"],"三部分全省略的头部是for()还是for(;;)？","for(;;)。",["F-S2"],["F06"])]
            old="单语句体约束"
            replacements[old]=[
                unit(old,"for 的单语句体","for循环体是一条语句，复合语句可用来包含多条语句。",["普通结构化控制流"],"for(i=0;i<2;i++) x++; y++;的循环体含y++吗？","不含，循环体仅为x++。",["F-S2"],["F07"]),
                unit(old,"for 的空语句体","for头部后紧接的分号可以作为空语句循环体，其后的独立语句不属于这个循环体。",["for(...);后的语句是独立语句"],"for(i=0;i<2;i++); {x++;}中的x++会作为循环体重复吗？","不会，循环体为空语句；结束后再执行独立的块。",["F-S2"],["F07"])]
            additions.append(unit("首判为假与零次执行","每次入体前判断条件","for在每次进入循环体之前求值非空控制表达式，非零才进入循环体。",
                ["普通顺序执行", "控制表达式非空且求值有定义"],"for是先执行循环体再第一次判断，还是先判断再入体？","先判断再入体，并在每次入体前判断。",["F-S1"],["F02"]))
        delta={"base_hash":digest(base),"revisions":[{"point_id":points[k]["id"],"reason":"Codex逐点内容修正及原子化，非千问生成结果","units":v} for k,v in replacements.items()],"additions":additions}
        doc,receipt=apply_intents(base,delta,{p["id"] for p in base["points"]},[s["id"] for s in topic["sources"]],[c[0] for c in criteria[name]])
        assert all(i["status"]=="applied" for i in receipt["items"])
        if name=="for":
            old=next(p for p in doc["points"] if p["name"]=="嵌套转移作用域")
            refs=[p["id"] for p in doc["points"] if p["name"] in ("continue 的执行逻辑","break 退出机制")]
            doc["points"]=[p for p in doc["points"] if p["id"]!=old["id"]]
            doc["applications"]=[{"id":"application_nested_transfer","question":"分别判断内层for中的break和continue转移到哪里，之后外层从哪里继续。","knowledge_ids":refs}]
            doc["history"].append({"previous":old,"replacement_ids":refs,"reason":"复合控制流分析重分类为应用任务，不重复制造break/continue叶子。"})
        for collection in ("checks","relations","misconceptions"):
            doc["invalidated"] += [{"collection":collection,"entity":e,"reason":"本轮重新生成教学材料；旧稿保留，不能复用旧错误解释"} for e in doc[collection]]
            doc[collection]=[]
        for p in doc["points"]:
            p.update(semantic_status="codex_reviewed_sample",scope_role="required",scope_reason="本组三份冻结范围之一及对应参考摘记明确要求",observable_target=p["question"])
        doc.update(schema="knowledge_tree_lab_v4",state="reviewed_core_candidate",core_provenance="v3 Qwen core plus explicit Codex corrections; not autonomous Qwen generation")
        doc.pop("pending_checks",None)  # v3 derived teaching state is not a v4 core field.
        folder=destination/name
        save(folder/"corrected-core.json",doc)
        save(folder/"core-corrections.json",delta)
        save(folder/"core-corrections.receipt.json",receipt)
        print(name,len(doc["points"]))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("previous",type=Path)
    parser.add_argument("destination",type=Path)
    args=parser.parse_args()
    correct_sample(args.previous,args.destination)
