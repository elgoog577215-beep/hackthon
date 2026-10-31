"""Pure equivalence decisions shared by proposals and pair confirmation."""
from copy import deepcopy
import re
from generic_knowledge import normalized,require
SCOPED_CONTRACT="knowledge_equivalence_v4"

def complementary_targets(a, b):
    """An explicit opposite Boolean parameter changes the check target.

    This is a conservative guard over the semantic slot, not a course-name or
    source-key exception. Other property differences still need semantic review.
    """
    properties = [p.get('atomic_contract', {}).get('property', '') for p in (a, b)]
    matches = [list(re.finditer(r'为(真|假)', prop)) for prop in properties]
    if any(len(found) != 1 for found in matches): return False
    left, right = (found[0] for found in matches)
    templates = [re.sub(r'为[真假]', '为{布尔值}', normalized(prop)) for prop in properties]
    return templates[0] == templates[1] and left.group(1) != right.group(1)

def validate_groups(value, points, *, notation_scope=False):
    require(isinstance(value, dict) and set(value) - {'_format_normalizations'} == {'groups'} and isinstance(value['groups'], list)
            and len(value['groups']) <= len(points) // 2, '等价核对响应无效')
    lookup = {p['key']: p for p in points}; used = set(); groups = []
    for group in value['groups']:
        fields = {'canonical_key', 'member_keys', 'relation', 'forward_reason', 'reverse_reason'}
        require(isinstance(group, dict) and set(group) == fields, '等价组字段无效')
        members = group['member_keys']; canonical = group['canonical_key']
        require(isinstance(members, list) and 2 <= len(members) <= len(points)
                and all(isinstance(k, str) and k in lookup for k in members)
                and len(set(members)) == len(members) and not used.intersection(members)
                and isinstance(canonical, str) and canonical in members, '等价组越界、重复或存在链式合并')
        require(group['relation'] == 'equivalent' and all(isinstance(group[k], str) and 0 < len(group[k].strip()) <= 24000
                for k in ('forward_reason', 'reverse_reason')), '只有给出双向依据的同义知识可合并')
        from knowledge_scope_notation import scope_signature
        scopes = {scope_signature(lookup[k]) if notation_scope else tuple(sorted(normalized(c) for c in lookup[k].get('conditions', []))) for k in members}
        require(len(scopes) == 1, '成立条件不同的知识不能自动等价合并')
        require(not any(complementary_targets(lookup[a], lookup[b]) for i, a in enumerate(members) for b in members[i+1:]),
                '互补的真假检查目标不能作为同义知识合并')
        used.update(members)
        groups.append({**deepcopy(group), 'semantics_verified': False, 'evidence_kind': 'same_model_equivalence_review'})
    return groups
