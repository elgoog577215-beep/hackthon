"""Source-bound terminology and read-only navigation of frozen knowledge evidence."""
from copy import deepcopy
import re
import unicodedata


TERM_SCHEMA = 'knowledge_source_terms_v1'
_ANNOTATION = re.compile(r'([\u3400-\u9fff][\u3400-\u9fffA-Za-z0-9+ /\-]{0,35})[（(]([A-Za-z][A-Za-z0-9 ,./+\-:]{1,100})[）)]')


def _normal(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


def _strings(value):
    return list(dict.fromkeys(s.strip() for s in value if isinstance(s, str) and 0 < len(s.strip()) <= 160)) if isinstance(value, list) else []


def _contains(value, source):
    needle, haystack = _normal(value), _normal(source)
    if not needle:
        return False
    if re.fullmatch(r'[a-z0-9 ]+', needle):
        return bool(re.search(r'(?<![a-z0-9])' + re.escape(needle) + r'(?![a-z0-9])', haystack))
    return needle in haystack


def _related(record, point, *, name_only=False):
    content = point.get('name', '') if name_only else f"{point.get('name', '')} {point.get('statement', '')}"
    return any(_contains(value, content) for value in [record['name'], record['english_name'], *record['abbreviations']])


def _specific_related(records, point, *, name_only=False):
    content = _normal(point.get('name', '') if name_only else f"{point.get('name', '')} {point.get('statement', '')}")
    spans = []
    for index, record in enumerate(records):
        for value in [record['name'], record['english_name'], *record['abbreviations']]:
            needle = _normal(value)
            if not needle: continue
            pattern = re.escape(needle)
            if re.fullmatch(r'[a-z0-9 ]+', needle): pattern = r'(?<![a-z0-9])' + pattern + r'(?![a-z0-9])'
            spans.extend((index, match.start(), match.end()) for match in re.finditer(pattern, content))
    return {_normal(records[index]['english_name']) for index, start, end in spans
            if not any(other_start <= start and end <= other_end and other_end-other_start > end-start
                       for _, other_start, other_end in spans)}


def enrich_point(point, *, proposed_terms=None, source_passages=None):
    """Add presentation metadata; stable knowledge and semantic revision IDs stay intact."""
    result = deepcopy(point)
    quotes = source_passages if source_passages is not None else point.get('source_quotes') or []
    found = []
    for source in quotes:
        raw_quote = source.get('quote') or ''
        clean = re.sub(r'[*_`]+(?=\s*[（(])', '', raw_quote)
        clean = re.sub(r'[*_`]+', '|', clean)
        for match in _ANNOTATION.finditer(clean):
            label = match[1].strip()
            label = re.sub(r'^.*(?:也称|又称|称为|称作|简称|另有|变为)', '', label)
            name_core = re.sub(r'(?:的定义|定义|的作用|作用|的规则|规则)$', '', point.get('name', ''))
            prefix = label[:-len(name_core)] if name_core and label.endswith(name_core) else ''
            if prefix and re.fullmatch(r'(?:(?:使用|采用|称为|称作|简称|一种|该|这种|此处的))+', prefix):
                label = name_core
            parts = [s.strip() for s in re.split(r'[,，]', match[2]) if s.strip()]
            abbreviations = [s for s in parts if re.fullmatch(r'[A-Z][A-Z0-9\-]{1,12}', s)]
            english = ', '.join(s for s in parts if s not in abbreviations) or match[2].strip()
            if re.fullmatch(r'(?:Level|Case|Step|Figure|Table)\s*\d+', english, re.IGNORECASE):
                continue
            annotation = re.search(re.escape(label) + r'(?:\*\*|__)?\s*[（(]' + re.escape(match[2]) + r'[）)]', raw_quote)
            found.append({'name': label, 'english_name': english, 'abbreviations': abbreviations,
                'aliases': [], 'origin': 'source_annotation', 'status': 'source_text_matched',
                'evidence_refs': [{'evidence_id': source['evidence_id'], 'quote': annotation[0] if annotation else raw_quote}]})
    relevant = _specific_related(found, point, name_only=True)
    if not relevant:
        relevant = _specific_related(found, point)
    confirmed = [r for r in found if _normal(r['english_name']) in relevant]
    candidates = deepcopy(point.get('term_candidates') or [])
    for existing in point.get('terms') or []:
        exact = any(_normal(r['name']) == _normal(existing.get('name')) and _normal(r['english_name']) == _normal(existing.get('english_name')) for r in found)
        suffix_conflict = (existing.get('origin') == 'source_annotation' and bool(existing.get('name')) and not exact
            and any(_normal(r['english_name']) == _normal(existing.get('english_name')) and _normal(r['name']) != _normal(existing['name'])
                    and _normal(r['name']).endswith(_normal(existing['name'])) for r in found))
        if suffix_conflict:
            candidates.append({**deepcopy(existing), 'origin': 'legacy_source_annotation', 'status': 'source_unconfirmed',
                               'reason': 'short_label_inside_another_source_entity'})
        else: confirmed.append(deepcopy(existing))
    by_key = {q.get('source_key', q['evidence_id']): q for q in quotes}
    for proposed in (proposed_terms or [])[:30]:
        if not isinstance(proposed, dict):
            continue
        record = {'name': str(proposed.get('name') or '')[:160], 'english_name': str(proposed.get('english_name') or '')[:160],
            'abbreviations': _strings(proposed.get('abbreviations')), 'aliases': _strings(proposed.get('aliases'))}
        source = by_key.get(proposed.get('source_key'))
        quote = str(proposed.get('quote') or '')
        values = [record['name'], record['english_name'], *record['abbreviations'], *record['aliases']]
        annotated_pair = any(_normal(r['name']) == _normal(record['name']) and
            _normal(r['english_name']) == _normal(record['english_name']) for r in found)
        identity_token = (_normal(record['name']) == _normal(record['english_name'])
                          and bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9_\-]*', record['name'])))
        declared_names = {_normal(v) for r in found if _normal(r['english_name']) == _normal(record['english_name'])
                          for v in [r['name'], r['english_name'], *r['abbreviations']]}
        if identity_token: declared_names.add(_normal(record['name']))
        if (source and quote and quote in source['quote'] and _related(record, point)
                and (annotated_pair or identity_token) and all(_contains(v, quote) for v in values if v)
                and all(_normal(v) in declared_names for v in [*record['aliases'], *record['abbreviations']])):
            confirmed.append({**record, 'origin': 'source_annotation', 'status': 'source_text_matched',
                'evidence_refs': [{'evidence_id': source['evidence_id'], 'quote': quote}]})
        elif any(values):
            candidates.append({**record, 'origin': 'model_suggested', 'status': 'source_unconfirmed'})
    grouped = {}
    for record in confirmed:
        key = (_normal(record.get('english_name')), _normal(record.get('name')))
        if not any(key):
            continue
        if key not in grouped:
            grouped[key] = deepcopy(record)
        else:
            current = grouped[key]
            current['aliases'] = _strings([*current.get('aliases', []), record.get('name', ''), *record.get('aliases', [])])
            current['abbreviations'] = _strings([*current.get('abbreviations', []), *record.get('abbreviations', [])])
            for ref in record.get('evidence_refs') or []:
                if ref not in current.setdefault('evidence_refs', []):
                    current['evidence_refs'].append(deepcopy(ref))
    result['terms'] = list(grouped.values())
    result['term_candidates'] = [dict(r) for r in candidates if r not in result['terms']]
    result['aliases'] = _strings([*point.get('aliases', []), *[
        value for r in result['terms'] for value in [r.get('name', ''), r.get('english_name', ''),
            *r.get('abbreviations', []), *r.get('aliases', [])]]])
    result['terminology_schema'] = TERM_SCHEMA
    result.setdefault('extraction_method', 'unspecified')
    return result


def project_tree(tree):
    if not tree:
        return tree
    result = deepcopy(tree)
    result['knowledge_points'] = [enrich_point(p) for p in tree.get('knowledge_points', [])]
    return result


def project_view(view):
    """Legacy metadata is a projection, never a course migration or new baseline."""
    view['tree'] = project_tree(view.get('tree'))
    view['candidate'] = project_tree(view.get('candidate'))
    view['history'] = [project_tree(tree) for tree in view.get('history', [])]
    view['candidates'] = [{**candidate, 'tree': project_tree(candidate['tree'])} for candidate in view.get('candidates', [])]
    return view


class KnowledgeSourceNotFound(Exception):
    pass


def frozen_split_matches(state, ref, evidence_id, quote, content):
    """Reproduce the existing splitter; never use approximate text matching."""
    from material_evidence import _split_source
    parts = set(_split_source(content))
    for job in state.get('jobs', {}).values():
        context = (job.get('request_snapshot') or {}).get('knowledge_generation_context') or {}
        refs = context.get('handout_source_refs') or {}
        for unit in (context.get('evidence_package') or {}).get('units', []):
            frozen = unit.get('source_text', '')
            if (unit.get('evidence_id') == evidence_id and quote and quote in frozen
                    and frozen in parts and any(refs.get(key) == ref for key in unit.get('block_ids', []))):
                return True
    return False


def locate_source(raw, state, tree_revision, knowledge_id, evidence_id):
    trees = [raw.get('course_knowledge_base') or {}, *(raw.get('knowledge_first_history') or {}).values()]
    trees.extend((j.get('checkpoint') or {}).get('candidate') or {} for j in state.get('jobs', {}).values()
                 if j.get('type') == 'course_knowledge_tree_generation' and j.get('status') == 'completed')
    tree = next((t for t in trees if t.get('revision_id') == tree_revision), None)
    point = next((p for p in (tree or {}).get('knowledge_points', []) if p.get('knowledge_id') == knowledge_id), None)
    source = next((q for q in (point or {}).get('source_quotes', []) if q.get('evidence_id') == evidence_id), None)
    if not source:
        raise KnowledgeSourceNotFound()
    quote = str(source.get('quote') or '')
    ref = source.get('handout_ref') or {}
    result = {'tree_revision': tree_revision, 'knowledge_id': knowledge_id, 'evidence_id': evidence_id,
        'quote': quote, 'locator': deepcopy(source.get('locator') or {}), 'handout_ref': deepcopy(ref),
        'quote_scope': source.get('quote_scope', 'source_passage'),
        'source_kind': 'generated_handout' if ref else source.get('source_kind', 'source_snapshot'), 'available': False,
        'content': '', 'reason': 'source_revision_missing' if ref else 'source_snapshot_missing'}
    if ref:
        lesson = state.get('lessons', {}).get(ref.get('lesson_id')) or {}
        revision = next((r for r in lesson.get('script_revisions', []) if r.get('revision_id') == ref.get('script_revision_id')), None)
        section = next((s for s in (revision or {}).get('sections', []) if s.get('section_node_id') == ref.get('section_id')), None)
        block = next((b for b in (section or {}).get('blocks', []) if b.get('block_id') == ref.get('block_id')), None)
        if revision and not block:
            result['reason'] = 'source_block_missing'
        content = str((block or {}).get('content') or '')
    else:
        # Only inspect frozen sources owned by this course and referenced by this point.
        units = (u for j in state.get('jobs', {}).values()
                 for u in (((j.get('request_snapshot') or {}).get('knowledge_generation_context') or {}).get('evidence_package') or {}).get('units', []))
        unit = next((u for u in units if u.get('evidence_id') == evidence_id and quote in u.get('source_text', '')), None)
        content = str((unit or {}).get('source_text') or '')
        if unit and result['source_kind'] == 'source_snapshot':
            result['source_kind'] = 'provided_material'
    if content and quote and quote in content:
        result.update(available=True, content=content, quote_start=content.index(quote),
                      quote_end=content.index(quote) + len(quote), reason='')
    elif content and ref and frozen_split_matches(state, ref, evidence_id, quote, content):
        # Split passages can elide layout separators. Show the original block,
        # retain its recorded quote, and do not invent literal character offsets.
        result.update(available=True, content=content, quote_match='frozen_split_passage', reason='')
    elif content:
        result['reason'] = 'source_quote_mismatch'
    return result
