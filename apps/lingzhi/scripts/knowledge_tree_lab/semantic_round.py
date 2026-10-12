"""Freeze semantic-contract intervention; same four materials and old questions."""
import argparse
from pathlib import Path
from .pipeline import read, save, digest
from .semantic_contract import VERSION

TREE_ADDITION = """
本轮增加：知识叶子只写可复用规则；具体案例事实放examples，不另造案例知识点。先逐句检查材料中的否定、不能推断、适用条件有无承载，不能因为没有对应检查题就丢掉规则。可分两条独立判断的命题请拆开。
relations里的prerequisite方向固定为先修知识→后学知识；没有必要依赖就不连线。meta_question必须真正检查该叶子，不只要求举例。事实与推断分开，证据不足不强行断言矛盾、因果或动机。
"""

TEACHING = """为给定树生成1—2个能力包覆盖每个知识点，采用teaching_semantic_contract_v1。先逐题检查实际要求的输出，再匹配知识点，不因题号合法就视为考点一致。
输入question_bank冻结了题干、答案、题目修订及用途。程序按引用装入答案，你不得在criteria另写答案/pass_evidence。binding仅解释哪个题目动作直接检查哪个规则；不能把只用到的先修当作直接考点，不能偷换对象/数字/初始状态。没有合适题就在supplemental_probes增加最少N1…题（具体题干、候选答案/开放评分准则、来源），不得强绑。补题答案仍待独立核验。
训练task只引用practice题，每题独立重置。迁移只引用transfer题，不把它的原题/同参数变体写进训练、区分或补救。复测涉及别的能力时明确prerequisite_point_keys，并在达标条件要求已掌握前置知识。
错因每能力1—2条即可：每条只假定一种明确的错误规则，其余已知条件保持不变。把题目的实体、关系、操作代入规则，逐步列derivation，再给prediction；不能把施力者偷换受力者、必要条件偷换充分条件、记载偷换已证实事实。错因无法推出结果时写prediction=无预测，说明limits；不得为了不同答案暗加第二种误解。假设诊断只是假说，单次错误不能证明心理原因。discrimination只能比较本次写出的具体预测；未验证的其他题别声称可区分。相同预测/共存/无预测时保留不确定。
每个补救步骤必须有source_ref和source_quote（从course.materials的text逐字截取的完整相关规则）、action（让学生具体做什么）、check_key（practice题，正确答案由程序插入）、scope_limit（这条规则不能扩大成什么）。动作必须直接针对错因且不能引入材料外的新事实或新数值结论。引用对了不代表动作自动正确，写完检查动作与原文是否同义、是否扩大结论。
历史等开放题保留多种有证据的解释，不按唯一立场/关键词判分；产量的记载不是已核验产量数据。所有gaps如实保留，不能让教学正文和树互相矛盾。
输出严格JSON，结构如下（示意值不是本课答案）：
{"supplemental_probes":[{"key":"N1","question":"具体输入与单点问题","answer":"候选正确答案或开放评分依据","evidence_type":"reasoning|exact|rubric","source_refs":["M1"]}],"skills":[{"key":"S1","name":"能力","point_keys":["P1"],"observable_behavior":"可见动作","task":{"probe_keys":["Q1"],"state_policy":"independent_reset","expected_evidence":"提交何种推理/轨迹"},"criteria":[{"point_key":"P1","probe_key":"Q1","question_revision":"照抄Q的revision；N题省略","binding":{"target":"这个点的单条规则","required_evidence":"题干实际要求的行为，不另写正确答案","why_direct":"该行为为何直接检查此规则"}}],"mistakes":[{"key":"A","point_keys":["P1"],"wrong_rule":"一条错误规则","probe_key":"Q1","derivation":["固定的题目条件","规则应用","推出结果"],"prediction":"该规则单独应用时的错误回答","limits":"可支持或不可排除的假说","repair_steps":[{"source_ref":"M1","source_quote":"逐字原文","action":"具体操作","check_key":"Q1","scope_limit":"不能泛化成的结论"}]}],"discrimination":{"probe_keys":["Q1"],"distinguishes":"引用已列出预测说明可区分的假说","limits":"不可确定的原因/共存"},"retest":{"key":"R1","question_revision":"照抄revision","prerequisite_point_keys":[],"why_transfer":"改变的情境以及仍检查的规则"},"mastery_requirements":["可判定条件；错因诊断只作候选解释"]}],"gaps":[]}。
简练但推导必须完整。无需添加另一套示例答案或重写冻结题目。
"""


def prepare(root, baseline):
    if (root/'manifest.json').exists():
        raise ValueError('already_frozen')
    old = read(baseline/'manifest.json')
    assert all(digest(read(baseline/n)) == h for n,h in old['input_hashes'].items())
    for name in ('fixtures.json', 'shared-contexts.json'):
        save(root/name, read(baseline/name))
    prompts = read(baseline/'prompts.json')
    prompts['tree'] += TREE_ADDITION
    prompts['teaching'] = TEACHING
    save(root/'prompts.json', prompts)
    save(root/'eval.json', {'baseline_root': str(baseline), 'protocol': VERSION,
        'fixed': ['四门材料与画像/上下文', '24道原检查题和8道复测', '模型与调用参数'],
        'changed': ['通用原子化和边界提示', '显式题干语义绑定及冻结答案程序装配',
                    '允许按缺口补题（候选答案独立复核）', '错误规则推导链', '逐字材料锚定补救'],
        'max_calls': 9, 'no_model_retries': True, 'no_course_writes': True,
        'review_axes': ['粒度及逐句材料覆盖', '原题及补题语义绑定', '单一错因预测推导',
                        '补救不引入新错', '复测独立性与前置依赖', '跨内容一致性'],
        'usable': '所有元知识有直接检查；答案正确；无错误绑定/错误推导/错误补救；完整材料边界；开放题保留多解；无关键待补项',
        'mechanical_not_semantic': True,
        'limit': '每课一微单元一次运行；补题增加了资源，不是相同题量的纯提示词因果实验；不证明整课或真实学生诊断效度'})
    names = ['fixtures.json', 'shared-contexts.json', 'prompts.json', 'eval.json']
    save(root/'manifest.json', {'model_calls_max': 9, 'protocol': VERSION,
        'input_hashes': {n: digest(read(root/n)) for n in names}})


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('baseline',type=Path)
    a=p.parse_args();prepare(a.root,a.baseline)
