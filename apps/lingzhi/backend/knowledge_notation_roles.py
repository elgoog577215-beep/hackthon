"""Conservative notation roles; never rewrite formulas or certify their truth."""
import re

IMPLICIT_RELATION_PATTERN = r'与[^、;；，,与和及]+?(?:的)?(?:关系|联系|区别|差异)'


def relation_target(prop):
    match = re.fullmatch(r'与([^、;；，,与和及]+?)(?:的)?(?:关系|联系|区别|差异)', prop)
    return match.group(1) if match else None


def _group(value, start):
    while start < len(value) and value[start].isspace(): start += 1
    if start >= len(value) or value[start] != '{': return None
    depth = 0
    for i in range(start, len(value)):
        if value[i] == '{': depth += 1
        elif value[i] == '}':
            depth -= 1
            if not depth: return value[start+1:i], start+1, i+1
    return None


def quantity_roles(value, *, unit_context=False):
    """Disambiguate tracked n/m/d variables from typed operator/unit spans."""
    spans = []; roles = []
    operator = r'(?:\\mathrm\s*\{\s*d\s*\}|d)'
    order = r'(?:\s*\^\s*(?:\{([1-9][0-9]*)\}|([1-9][0-9]*)))?'
    units = r'(?:mol|kat|min|rad|Bq|Gy|Sv|Pa|Wb|lm|lx|kg|mm|cm|km|ms|cd|sr|m|s|g|A|K|N|J|W|C|V|F|S|T|H|h|d)'
    atom = rf'(?:\\(?:mathrm|text)\{{\s*{units}\s*\}}|{units})'
    power = r'(?:\s*\^\s*(?:\{[-+]?[0-9]+\}|[-+]?[0-9]+))?'
    separator = r'(?:\s*[/·*]\s*|\s*\\[,;!]\s*|\s+)'
    product = rf'{atom}{power}(?:{separator}{atom}{power})*'
    for command in re.finditer(r'\\(?:dfrac|tfrac|frac)\s*', value):
        numerator = _group(value, command.end())
        denominator = _group(value, numerator[2]) if numerator else None
        if not numerator or not denominator: continue
        num, num_start, _ = numerator; den, den_start, _ = denominator
        n = re.match(r'\s*' + operator + order, num)
        d = re.match(r'\s*' + operator + r'\s*(?:\\,\s*)?(?:\\[A-Za-z]+|[A-Za-z])' + order + r'\s*$', den)
        if n and d and (n.group(1) or n.group(2) or '1') == (d.group(1) or d.group(2) or '1'):
            den_operator = re.match(r'\s*' + operator, den)
            for start, end in ((num_start, num_start+n.end()), (den_start, den_start+den_operator.end())):
                spans.append((start,end));roles.append({'symbol':'d','role':'differential_operator','start':start,'end':end})
        if unit_context and re.fullmatch(product, num.strip()) and re.fullmatch(product, den.strip()):
            spans.extend(((num_start,num_start+len(num)),(den_start,den_start+len(den))))
    if unit_context:
        for match in re.finditer(rf'(?<![A-Za-z0-9_]){atom}{power}(?:{separator}{atom}{power})+(?![A-Za-z0-9_])', value):
            spans.append(match.span())
        if re.fullmatch(product, value.strip('$ \t\n')): spans.append((0,len(value)))
    free = set()
    for match in re.finditer(r'\b[nmd]\b', value):
        bound = next(((a,b) for a,b in spans if a <= match.start() < b), None)
        if not bound: free.add(match.group())
        elif not any(r['role']=='differential_operator' and r['start'] <= match.start() < r['end'] for r in roles):
            roles.append({'symbol':match.group(),'role':'unit','start':match.start(),'end':match.end()})
    return free, roles
