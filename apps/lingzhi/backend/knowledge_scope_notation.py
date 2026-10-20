"""Conservative comparison hints for declared symbols, never equivalence proof."""
import re


def scope_signature(point):
    statement=re.sub(r'\s+','',str(point.get('statement',''))).replace('$','')
    result=[]
    for condition in point.get('conditions',[]):
        literal=re.sub(r'\s+','',condition)
        text=re.sub(r'^\$([A-Za-zΑ-Ωα-ω][A-Za-zΑ-Ωα-ω0-9_]*(?:\([A-Za-zΑ-Ωα-ω][A-Za-zΑ-Ωα-ω0-9_]*\))?)\$(?=表示)',r'\1',literal)
        declaration=re.fullmatch(r'([A-Za-zΑ-Ωα-ω][A-Za-zΑ-Ωα-ω0-9_]*)(?:\(([A-Za-zΑ-Ωα-ω][A-Za-zΑ-Ωα-ω0-9_]*)\))?表示([^。；;,，]+)[。]?',text)
        if not declaration:
            result.append(('literal',literal));continue
        symbol,argument,referent=declaration.groups()
        calls=set(re.findall(r'(?<![A-Za-z0-9_])'+re.escape(symbol)+r"['′]*\(([A-Za-zΑ-Ωα-ω][A-Za-zΑ-Ωα-ω0-9_]*)\)",statement))
        if calls and len(calls)==1 and (argument is None or argument in calls):
            result.append(('declared_function',symbol,next(iter(calls)),referent))
        else:result.append(('declared_symbol',symbol,argument or '',referent))
    return tuple(sorted(result))
