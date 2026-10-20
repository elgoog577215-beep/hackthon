# 知识树隔离实验

这是知识树生成机制的可重复实验工具，不是第二套课程知识库，也不写入课程、讲义或学生记录。
产品要求见 [课程知识树](../../docs/功能设计/课程知识树.md)。接入产品时须复用已有课程知识库的保存责任。

## 本轮机制

- 模型生成教学命题和分类路径；程序生成分类与知识 ID。
- 模型给出“这个点替换成这些命题”的语义意图；程序按原点进行独立事务，保存旧修订与替代映射。单个意图无效时保留该点，其余有效意图可以保存，回执逐项报告。
- 拆分或修订后，受影响的检查、关联与诊断进入 `invalidated`，等待重新绑定；不把旧关系盲目复制给所有子点。
- 每个点有检查；不完整时保留 `pending_checks`。静态答案及知识解释仍需内容审阅。
- 运行题的模型答案只保存为 `predicted_stdout`；样本正确答案来自精确源码、环境与编译运行回执。代码改变或运行失败时撤销核验状态。
- 易错点只引用共同表现题、区分题和复测题。两种错误信念的共同预测须相同且错误，区分题预测须不同；数值合同通过仍不代表错误信念及补救具有教学效度。

## 运行

从应用目录执行，使用已有后端依赖环境。把本目录 `fixtures/c17` 下的四份冻结输入复制到一个新的隔离目录，再用本机编译器生成 `compiler-environment.json`；不要复制别人的环境数值。`eval_definition.json` 保留前轮的评估口径，本轮调用编排由 `protocol.json` 确定。

```powershell
python -m unittest scripts.knowledge_tree_lab.test_pipeline -v
python -m scripts.knowledge_tree_lab.compiler --gcc <gcc路径> --output <隔离实验目录>/compiler-environment.json
python -m scripts.knowledge_tree_lab.run <隔离实验目录> core
python -m scripts.knowledge_tree_lab.prepare <隔离实验目录> core --gcc <gcc路径>
python -m scripts.knowledge_tree_lab.run <隔离实验目录> atomize
python -m scripts.knowledge_tree_lab.prepare <隔离实验目录> atomize --gcc <gcc路径>
python -m scripts.knowledge_tree_lab.run <隔离实验目录> teach
python -m scripts.knowledge_tree_lab.prepare <隔离实验目录> teach --gcc <gcc路径>
```

首次准备教学结果只做结构整理，未获准的代码显示 `eligibility_review_required`。检查生成的 `initial.unverified.json`，确认代码有限、行为有定义、没有外部副作用，再将对应 `code_hash(check)` 放入该主题 `execution-approvals.json` 的 `approved_hashes` 列表，并记录审阅理由。再次 prepare teach 才执行代码并生成修正范围。

```powershell
python -m scripts.knowledge_tree_lab.run <隔离实验目录> repair
python -m scripts.knowledge_tree_lab.prepare <隔离实验目录> repair --gcc <gcc路径>
# 新代码必须重新检查并按精确哈希许可，然后只重算本地核验：
python -m scripts.knowledge_tree_lab.prepare <隔离实验目录> final --gcc <gcc路径>
```

四个阶段每主题各一次，共最多 12 次真实请求。已开始的同一阶段拒绝重复调用；失败不自动采样重试。程序使用现有 `AIBase` 与批准的模型路由，不保存凭据到实验文件。提示、原始响应、解析结果和调用统计均保留。保留题不进入提示。

`compiler.py` 不是通用沙箱：有限语法过滤、超时和 O0/O2 一致性不能证明任意 C 程序安全，也不能排除全部未定义行为。此实验的执行资格由审阅后的精确哈希控制；产品接入需独立受限执行环境。

## 结果解释

链式法则的独立深化实验见[诊断样板](../../docs/研究/链式法则诊断深化样板.md)及[验收记录](../../docs/验收/链式法则诊断深化-2026-10-20.md)。`python -m scripts.knowledge_tree_lab.chain_rule_demo --output <仓库外新目录>` 只作虚构病例回放；显式 `--model` 才执行一次真实 Qwen 小题判分。没有预期病例标签进入模型输入，不保存正式学习事实或画像；固定模式不是通用诊断引擎，候选不能直接变成生产确诊。

`final.json` 是可检查候选，`state=candidate`，不是已发布基线。分别查看结构回执、代码回执、遗漏检查、语义评估；不能把 JSON 可解析、字段齐全或少量代码通过称作全课准确。模型自审不替代教师审定。实验结果不触发讲义内容审核、改写或重跑。

`export.py` 将三组候选组织成单根树和阅读版，需先单独完成 `assessment.json` 语义评估。第三轮评估与原始回执的位置见[实测报告](../../docs/验收/知识树语义拆分与答案绑定实测-2026-10-11.md)。评估意见不应回填到同轮模型提示后又当作独立验收。

## 第四轮：先校正核心，再分批生成检查

第四轮不是 v3 无辅助重跑。`correct_sample.py` 显式修正 v3 核心并拆分复合点；`round4_jobs.py` 冻结每批最多六点的检查任务、诊断参数任务及关系任务。`run_jobs.py` 使用相同 Qwen 路由执行 15 个初始任务，最多再执行每主题一次定向修正，共 18 次。

`diagnostic_templates.py` 固定三组经 Codex 核对的错误信念及可执行反事实模拟。模型只能选择经过类型/范围约束的参数，不能写任意待执行代码、改换错误信念或提供权威答案。输出来自正确程序及模拟程序的精确回执。模板覆盖有限，不能当成支持所有课程诊断的通用引擎。

```powershell
python -m scripts.knowledge_tree_lab.correct_sample <v3实验目录> <v4隔离目录>
python -m scripts.knowledge_tree_lab.compiler --gcc <gcc路径> --output <v4隔离目录>/compiler-environment.json
python -m scripts.knowledge_tree_lab.round4_jobs <v4隔离目录>
python -m scripts.knowledge_tree_lab.run_jobs <v4隔离目录>
python -m scripts.knowledge_tree_lab.round4_prepare <v4隔离目录> --gcc <gcc路径>
# 内容复核后，在实验目录冻结repair-jobs.json及其哈希，最多三项：
python -m scripts.knowledge_tree_lab.run_jobs <v4隔离目录> --jobs repair-jobs.json
python -m scripts.knowledge_tree_lab.finalize_round4 <v4隔离目录>
python -m scripts.knowledge_tree_lab.probe_round4 <v4隔离目录> --gcc <gcc路径>
python -m unittest scripts.knowledge_tree_lab.test_pipeline scripts.knowledge_tree_lab.test_round4 -v
```

先按前文复制原资料、评估定义、保留题到新的隔离目录。v4 的修正任务和逐题评估是本次内容审查记录，见[第四轮报告](../../docs/验收/知识树讲义基线样板第四轮-2026-10-11.md)及其中原始证据目录，不应伪装成通用自动判分器。`finalize_round4.py` 含本轮明确的 Codex 编辑，并另外保存千问未编辑候选，禁止把最终通过数记为千问全自动通过。

`acceptance.py` 校验每点的检查与审阅、树引用、范围/来源处置、诊断及修订哈希。语义评语由复核者提交；代码只能检验其齐全与版本一致，不证明评语自身正确。正式产品仍须复用已有知识库与任务采用责任。

## 从第四轮基线试写讲义

`handout_trial.py` 固定整份知识修订、规范术语、各讲知识范围与已核验例子。每讲一次主请求，千问写正文并选择引用；渲染器从冻结输入插入代码和答案。试写的内容核对是用户指定的独立实验，不作为生产讲义保存门槛，不调用模型自审、改写或重跑。

```powershell
python -m scripts.knowledge_tree_lab.handout_trial <新的试写目录> build --baseline docs/研究/C语言三组知识树讲义基线样本.json --evidence <v4实验目录>
python -m scripts.knowledge_tree_lab.run_jobs <新的试写目录>
python -m scripts.knowledge_tree_lab.handout_trial <新的试写目录> export --destination <样稿输出目录>
python -m scripts.knowledge_tree_lab.check_handout_assets <新的试写目录> <样稿输出目录> --gcc <gcc路径>
python -m unittest scripts.knowledge_tree_lab.test_handout_trial -v
```

首次实测见[试写及一致性报告](../../docs/验收/知识树到讲义首次试写-2026-10-11.md)。模型正文原样保存，返回段落结构时可以兼容显示，但不伪造块级知识绑定；输入范围表也不冒充实际解释覆盖。当前输入适配器已经补充同组综合应用投影，首次实测的冻结输入保持原样，未重跑。

## 用户指定的讲义修订

`revise_handouts.py` 记录针对首次试写三讲的 Codex 编辑，补齐引用、诊断、总结及综合应用。它没有模型调用，也不是通用的自动修稿服务；必须保留原请求和响应。修订稿带独立来源标记，不能再显示为千问首次原文。

```powershell
python -m scripts.knowledge_tree_lab.revise_handouts <首次试写证据目录> <新的修订证据目录> <修订稿目录>
python -m scripts.knowledge_tree_lab.check_handout_assets <修订证据目录> <修订稿目录> --gcc <gcc路径>
```

只改正文、没有改例题代码或答案时，可添加 `--reuse-execution`，仅在代码、环境与答案均匹配时复用已有执行回执；不重复计数或声称重新执行。来源正文与渲染结果仍重新核对。`revision-manifest.json` 记录父响应哈希及修订内容哈希。

本轮最终结果见[修订复核报告](../../docs/验收/知识树讲义修订复核-2026-10-11.md)。结构有效、代码通过和内容评语分别保存；限定样板可用不等于学科教师确认或生产生成链路验收。
