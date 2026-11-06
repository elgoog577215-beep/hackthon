"""Source-bound reference ranges authored inside the shared handout stream.

Markers select existing prose, never a second model-written summary. Invalid or
unfinished metadata cannot reject or discard teaching content.
"""
import json
import re

REFERENCE_SCHEMA_VERSION = 'handout_reference_v1'
REFERENCE_KINDS = {'definition', 'theorem', 'result', 'formula', 'rule', 'method'}


def reference_writing_guide() -> str:
    return r'''
阅读视图共用这份正文，不另输出速览摘要或公式清单。教学块是讲解单位，速览条目是可独立查用的知识单位，两者不必一一对应。
在正文第一次完整陈述定义、定理、核心公式、规则或方法时，用以下独占行标记圈定现有正文：
<!-- reference:{"kind":"theorem","title":"具体定理名称"} -->
[这里直接写正文中的完整定理：先给适用条件，再给结论或公式；这段只写一次]
<!-- reference:end -->
kind 仅取 definition、theorem、result、formula、rule、method。它表示知识性质，外层 block.type 仍表示教学用途。
每个范围只含一个可查用的知识：标题具体；变量约定、成立条件、限制、分情况结论必须和表达式在同一范围；方法保留必要输入条件及完整关键步骤，编程规则可含最短语法或代码。
动机、长解释、证明、完整算例放在范围之外，紧接着连续讲解；不要为速览缩短正文或拆碎教学块。同一块有多个定义时分别圈定。
每个 definition、theorem、result、rule、method 块的核心表达都应圈定，不能只给其中最后一条公式加标记；同一块里的多个正式定义分别圈定。解释块只在确有可查用的结论时圈定。
以下是一个完整的输出格式示例，仅示范元数据与正文的嵌套关系，不要照搬到无关课程：
<!-- block:{"type":"definition","title":"条件概率","key":"conditional_probability"} -->
<!-- reference:{"kind":"definition","title":"条件概率"} -->
设 $A,B$ 为事件，且 $P(B)>0$。定义 $P(A\mid B)=P(A\cap B)/P(B)$。
<!-- reference:end -->
这里继续解释条件如何缩小样本空间，解释属于同一正文块，但不属于速览范围。
因此先写 block 行，再在块内写 reference 起止行；三类元数据注释都是输出协议，允许保留，不能因为正文禁止 HTML 就省略它们。
不为每段标记，不为凑类型编造定理，不把数值算例包装成一般公式，不标练习、答案、折叠提示。范围不能嵌套或跨教学块，标记不能放在代码围栏内。缺少可独立查用的知识时不标。
'''


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate reference metadata')
        result[key] = value
    return result


def parse_reference_ranges(text: str) -> dict:
    output, entries, issues = [], [], []
    active = None
    fence = ''
    folded = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        token = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line.rstrip('\r\n'))
        if token:
            mark, tail = token.groups()
            if not fence:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not tail.strip():
                fence = ''
            output.append(line); offset += len(line)
            continue
        stripped = line.strip()
        if not fence and stripped.startswith('<!-- reference:'):
            if stripped == '<!-- reference:end -->':
                if active:
                    meta, start, valid = active
                    body = ''.join(output)[start:offset]
                    left = len(body) - len(body.lstrip())
                    body = body.strip()
                    if valid and body:
                        entries.append({**meta, 'start': start + left, 'end': start + left + len(body), 'content': body})
                else:
                    issues.append('unmatched_end')
                active = None
            else:
                if active:
                    issues.append('nested_range')
                    active = (active[0], active[1], False)
                else:
                    try:
                        if not stripped.endswith('-->'):
                            raise ValueError
                        meta = json.loads(stripped[len('<!-- reference:'):-3], object_pairs_hook=_unique_fields)
                        if not isinstance(meta, dict) or meta.get('kind') not in REFERENCE_KINDS:
                            raise ValueError
                        title = meta.get('title')
                        if not isinstance(title, str) or not title.strip() or len(title) > 160:
                            raise ValueError
                        active = ({'kind': meta['kind'], 'title': title.strip()}, offset, not folded)
                    except (ValueError, TypeError):
                        issues.append('invalid_metadata')
            output.append('\n'); offset += 1
            continue
        if not fence:
            for tag in re.finditer(r'</?details\b[^>]*>', line, re.I):
                folded = max(0, folded + (-1 if tag[0].startswith('</') else 1))
                if active:
                    active = (active[0], active[1], False)
        output.append(line); offset += len(line)
    if active:
        issues.append('unfinished_range')
    content = ''.join(output)
    trim = len(content) - len(content.lstrip())
    content = content.strip()
    for index, entry in enumerate(entries):
        entry.update(id=f'r{index + 1}', start=entry['start'] - trim, end=entry['end'] - trim)
    return {'content': content, 'reference_schema_version': REFERENCE_SCHEMA_VERSION,
            'references': entries, 'reference_issues': sorted(set(issues))}
