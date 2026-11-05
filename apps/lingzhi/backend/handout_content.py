"""Shared teaching-purpose catalog: writing guidance, never a content gate."""
import json
from pathlib import Path

HANDOUT_CONTENT_CATALOG = json.loads(
    (Path(__file__).resolve().parents[1] / 'shared' / 'handout-content-v1.json').read_text(encoding='utf-8')
)
HANDOUT_CONTENT_TYPES = {
    item['id']: (item['label']['zh'], item['role']) for item in HANDOUT_CONTENT_CATALOG['types']
}
HANDOUT_CONTENT_ALIASES = {
    label: item['id'] for item in HANDOUT_CONTENT_CATALOG['types'] for label in item['label'].values()
}
HANDOUT_CONTENT_ALIASES.update(HANDOUT_CONTENT_CATALOG['aliases'])


def handout_writing_guide() -> str:
    """Use the subtype responsibilities shown by the reader and editor."""
    lines = [
        '教学用途与写作要点（按需要选择，不要求凑齐，不是固定顺序）：',
        '默认从下列标准类型中选用；只有现有类型确实无法表达教学作用时才使用自定义类型，不为同一种作用另起近义类型名。',
        '整节围绕一个核心问题组织：让读者进入问题、理解知识、看到怎样使用，再独立检查与回顾。',
        '这些是学习职责，不是必须各建一块的模板；可合并、调整顺序，复习资料可先由题目引出知识。',
        '每块先交代本块的核心表述或完整任务，再展开依据、步骤与边界；不要用标题列表代替讲解。',
        '需要分层时用六级 Markdown 小标题组织块内内容（如“直观理解”“成立条件”“解题过程”），不重复块标题。',
        '小标题按实际内容选用，不强行凑齐；关键语句只在正文出现一次，可适量加粗，公式、代码、图表仍放在对应解释旁。',
    ]
    for group in HANDOUT_CONTENT_CATALOG['groups']:
        lines.append(group['label']['zh'] + '：')
        for item in HANDOUT_CONTENT_CATALOG['types']:
            if item['group'] == group['id'] and not item.get('legacy'):
                lines.append(f"{item['id']}（{item['label']['zh']}）：" + '；'.join(item['checkpoints']['zh']) + '。'
                             + item.get('body_guide', {}).get('zh', ''))
    return '\n'.join(lines) + '\n'
