"""Legacy extraction contract values and source term choices."""
import re

LEGACY_CONTRACT = 'knowledge_extract_v1'
FOCUS_CONTRACT = 'knowledge_extract_v2'
COMPLETE_CONTRACT = 'knowledge_extract_v3'
LITERAL_CONTRACT = 'knowledge_extract_v4'
PARTS_CONTRACT = 'knowledge_extract_v5'
SEMANTIC_CONTRACT = 'knowledge_extract_v6'
WIRE_CONTRACT = 'knowledge_extract_v7'
SCALAR_CONTRACT = 'knowledge_extract_v8'
CONTRACT = 'knowledge_extract_v9'
CONTRACTS = {LEGACY_CONTRACT, FOCUS_CONTRACT, COMPLETE_CONTRACT, LITERAL_CONTRACT, PARTS_CONTRACT, SEMANTIC_CONTRACT, WIRE_CONTRACT, SCALAR_CONTRACT, CONTRACT}


def focus_options(content):
    """Literal lexical anchors, not inferred terminology or certified subjects."""
    terms = []
    def add(term):
        term = term.strip()
        if term and len(term) <= 100 and term in content and term not in terms:
            terms.append(term)
    for marked in re.findall(r'`([^`\n]+)`|\*\*([^*\n]+)\*\*|\$([^$\n]+)\$', content):
        for term in marked:
            if term: add(term)
    for token in re.findall(r'[\u3400-\u9fff]+|[A-Za-z_][A-Za-z_0-9]*(?:\([^()\n]{0,30}\))?', content):
        add(token)
        # Split only at literal grammatical separators; never paraphrase anchors.
        for term in re.split(r'定义为|称为|通过|表示|包括|执行|遵循|插入|移除|返回|发生|的|是|将|把|在|从|向|为|与|和|并|则|当|若', token):
            add(term)
    if not terms:
        for token in re.findall(r'\S{1,100}', content): add(token)
    return {f'F{i}': term for i, term in enumerate(terms, 1)}


def focus_choices(content):
    options = list(focus_options(content).values())
    short = [term for term in options if re.fullmatch(r'[\u3400-\u9fff]{1,8}|[A-Za-z_][A-Za-z_0-9]{0,39}(?:\(\))?', term)]
    return short or options
