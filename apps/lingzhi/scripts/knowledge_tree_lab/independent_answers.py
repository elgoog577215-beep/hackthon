"""Conservative answer comparison; nonliteral reasoning is explicitly unknown."""
import ast
import re
from .pipeline import digest


def literal_prefix(text):
    if not isinstance(text,str):return None
    text=text.strip().strip('`').strip()
    boolean=re.match(r'^(True|False)(?=$|[\s。；;，,.])',text)
    if boolean:return ('bool',boolean.group(1)=='True')
    if not text.startswith('['):return None
    # At most 512 chars; literal_eval never executes calls/names/attributes.
    for i,char in enumerate(text[:512]):
        if char!=']':continue
        try:
            value=ast.literal_eval(text[:i+1])
            if isinstance(value,list):return ('list',value)
        except (SyntaxError,ValueError):pass
    return None


def compare(candidate,audit):
    reviews={r['key']:r for r in audit.get('reviews',[])};rows=[]
    for p in candidate['points']:
        for field in ('check','transfer'):
            generated=p[field]['answer'];independent=reviews.get(p['key'],{}).get(field+'_answer')
            left=literal_prefix(generated);right=literal_prefix(independent)
            status='needs_semantic_review'
            if left is not None and right is not None:
                status='literal_agreement' if left==right else 'answer_mismatch'
            rows.append({'point_key':p['key'],'field':field,'generated':generated,'independent':independent,
                         'status':status,'limit':'字面值一致只校验结果，不证明解释、题目考点或补救正确'})
    return {'candidate_digest':digest(candidate),'audit_digest':digest(audit),'rows':rows,
            'ready_for_adoption':False}
