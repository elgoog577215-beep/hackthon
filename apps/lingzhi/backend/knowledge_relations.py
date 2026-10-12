"""Two-ended lookup for one canonical directed relation."""


def relation_index(tree):
    index = {p['knowledge_id']: {'incoming': [], 'outgoing': []} for p in tree.get('knowledge_points', [])}
    for relation in tree.get('relations', []):
        source = relation.get('source_id') or relation.get('source_knowledge_id')
        target = relation.get('target_id') or relation.get('target_knowledge_id')
        rid = relation.get('id') or relation.get('relation_id')
        if not rid or source not in index or target not in index or source == target:
            continue
        if rid not in index[source]['outgoing']:
            index[source]['outgoing'].append(rid)
            index[target]['incoming'].append(rid)
    return index
