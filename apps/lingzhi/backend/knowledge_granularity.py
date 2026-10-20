"""Versioned input guidance; never infers a student's mastery or edits a tree."""
import json


CONTRACT = 'knowledge_granularity_v1'
INPUT_MARKER = '\nINPUT_JSON:\n'
GUIDANCE = (
    '按granularity_policy判断完整知识核；它是输入审查标准，不是响应字段。'
    '继续使用原响应Schema，不输出检查项、画像、学生错因或新接口字段。'
    '颗粒度判断是候选，不因结构校验通过就宣称学科或教学效果已经验证。'
)


def policy_payload(contract=CONTRACT):
    if contract != CONTRACT:
        raise ValueError('未知知识颗粒度合同，不能静默切换规则')
    return {
        'contract': CONTRACT,
        'knowledge_unit': '本课范围和前置下，一个可完整解释、明确条件并有针对性检查的概念、规则、判断或最小方法。',
        'split_when': [
            '候选确实包含多个可分别完整陈述、具有独立边界的知识核，并能分别教学、检查和补学。',
            '拆分后每点保留必要条件、来源和原内容去向；不是只根据名称或可能出错位置拆分。',
        ],
        'keep_together': [
            '同一公式的因子、求值位置和必要条件共同组成完整规则，不拆成残缺结论。',
            '联合定义的必要限定、同一最小方法的必要步骤保持完整。',
            '同一规则的重复应用、换数值、换表示、识别与执行差异不自动形成新知识。',
        ],
        'not_knowledge': {
            'check_items': '概念辨析、规则执行、适用条件识别、多层应用和变化情境是检查角度，不按每个角度新增叶子。',
            'learner_records': '漏项等观察、概念/操作/迁移困难假设、提示后完成、独立作答、延时保持是个人事实或画像，不是共享知识；单次错答不足以确诊。',
        },
        'source_boundary': '只提取冻结来源支持的一般内容；来源不足登记疑点或缺口，不编造知识、检查结果或学生记录。只有完整命题和条件等价才复用，不按同名直接归并。',
        'examples': [
            {'case': '正文同时包含常数倍与和函数求导规则', 'decision': '分别保留两个完整规则，线性组合例题作综合应用。'},
            {'case': '链式求导公式', 'decision': '保留对应点可导条件、外层求值位置和内层导数因子的完整公式，不为漏乘或多层应用另建叶子。'},
            {'case': '商法则', 'decision': '分母非零条件、分子减法顺序和分母平方随同一完整规则保留。'},
        ],
    }


def apply_policy(prompt, contract=None):
    """An absent frozen contract preserves an old request byte for byte."""
    if contract is None:
        return prompt
    policy = policy_payload(contract)
    instruction, marker, encoded = prompt.partition(INPUT_MARKER)
    if not marker:
        raise ValueError('知识颗粒度提示缺少冻结输入')
    payload = json.loads(encoded)
    payload['granularity_policy'] = policy
    return instruction + GUIDANCE + marker + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
