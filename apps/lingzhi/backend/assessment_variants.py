"""Bounded atomic variant planning and private, pre-solve choice allocation."""
from collections import Counter
import secrets

from course_versioning import stable_hash

VARIANT_ROLES = ('direct', 'contrast', 'transfer')


def expand_atomic_variants(slots: list[dict], count: int) -> list[dict]:
    if type(count) is not int or not 1 <= count <= len(VARIANT_ROLES):
        raise ValueError('assessment_variant_count must be an integer between 1 and 3')
    result = []
    for slot in slots:
        for index, role in enumerate(VARIANT_ROLES[:count]):
            key = slot['generation_key'] if index == 0 else stable_hash(
                {'initial_slot': slot['generation_key'], 'variant_role': role}, prefix='aks_')
            result.append({**slot, 'slot_id': key, 'generation_key': key,
                           'variant_index': index, 'variant_role': role,
                           'assessment_evidence_key': key})
    return result


class ChoicePositionAllocator:
    """Balance each option arity across a run; retain positions during repair.

    Allocation stays private and precedes solver/reviewer calls. Existing saved
    questions are never relabelled. Random tie breaking avoids fixed A/B cycles.
    """
    def __init__(self):
        self.counts = {}
        self.positions = {}

    def allocate(self, slot_id: str, size: int) -> int:
        key = (slot_id, size)
        if key not in self.positions:
            counts = self.counts.setdefault(size, Counter({i: 0 for i in range(size)}))
            low = min(counts.values())
            position = secrets.choice([i for i in range(size) if counts[i] == low])
            self.positions[key] = position
            counts[position] += 1
        return self.positions[key]


def variant_instruction(slot: dict, kind: str) -> str:
    role = slot.get('variant_role', 'direct')
    if role == 'direct':
        return '直接判断：一个最小实例。'
    # These are semantic strategies, shared across all IDs/courses with the rule.
    alternatives = {
        'assignment_sequence': (
            '对照同一个不能整除的整数除法赋给int和double两种目标，问两者存储的数值对。',
            '给出先声明的两个int变量，再用独立赋值语句赋给double变量；问右侧求值及存储的值和类型。不能仍是一条字面量初始化。'),
        'conversion_scope': (
            '将cast放在带括号的整个整数商之外，直接问转换的作用范围及先后。不要转单个操作数。',
            '并列两个表达式，分别转换除数与转换整个整数商，问两个数值组成的有序对；使用不能整除的整数。'),
        'syntactic_binding': (
            '给内层if加完整花括号块，使指定else属于外层if，直接问语法归属。',
            '使用三个嵌套if和两个else，明确标记所问else（代码注释只作位置标号）；问该else属于哪个原始条件，不补花括号。'),
        'uncontrolled_statement': (
            '在条件为假的if(cond);后放一个含赋值的花括号块，问块执行后的变量值。',
            '在条件为假的if(cond);后放一条自增语句，再给出该变量；问值。必须显式初始化，错误规则是把随后语句误当条件体。'),
        'condition_evaluation_trace': (
            '三条件if/else-if链：首条件为假、第二个为真、第三个也为真；问实际求值的条件序列。',
            '四条件if/else-if链：前两个为假、第三个为真、第四个也为真；问哪些条件被求值。'),
        'next_control_action': (
            '使用+=2形式更新表达式，在某次明确到达continue时问下一次条件判断前计数变量的值。其后的循环体赋值被跳过，不累加多轮。',
            '使用递减for和条件触发的continue，问执行continue后下一次条件判断前的状态及动作顺序；余下循环体含可跳过的赋值。'),
        'exit_state': (
            '采用递减for，在已知条件break后问for更新变量本身的值（与递增实例有方向差异）。',
            '采用步长大于1的+=更新，在循环体先改变更新变量一次再break，问退出后的该变量，保留break直接退出行为。'),
    }
    if kind in alternatives:
        return alternatives[kind][0 if role == 'contrast' else 1] + ' 本变式取代直接判断模板的结构限制，仍只考同一个完整规则。'
    return (
        '对照辨析：给两个有结构差异的最小实例，问结果的有序对；只改变目标规则的一方面构造错误预测。'
        if role == 'contrast' else
        '迁移应用：在已学范围内改变表达式结构或控制方向/语句位置后直接观察目标规则，不能仅换数字、变量名或改写问句。'
    )
