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
    lines = ['教学用途与写作要点（按需要选择，不要求凑齐，不是固定顺序）：']
    for group in HANDOUT_CONTENT_CATALOG['groups']:
        lines.append(group['label']['zh'] + '：')
        for item in HANDOUT_CONTENT_CATALOG['types']:
            if item['group'] == group['id'] and not item.get('legacy'):
                lines.append(f"{item['id']}（{item['label']['zh']}）：" + '；'.join(item['checkpoints']['zh']) + '。')
    return '\n'.join(lines) + '\n'
