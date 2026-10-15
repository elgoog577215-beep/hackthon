import itertools
import math
from fractions import Fraction

from assessment_fact_evidence import build_computed_candidate, evaluate_fact_evidence, treap_expected_depth


def test_tree_expectations_match_exhaustive_insertion_orders():
    for n in range(1,7):
        totals=[0]*n
        orders=list(itertools.permutations(range(1,n+1)))
        for order in orders:
            tree={}
            for key in order:
                root=order[0]
                depth=0
                while root in tree:
                    branch=0 if key<root else 1
                    child=tree[root][branch]
                    if child is None:
                        tree[root][branch]=key
                        break
                    root=child
                    depth+=1
                tree[key]=[None,None]
                totals[key-1]+=depth if key==order[0] else depth+1
        for rank in range(1,n+1):
            assert treap_expected_depth(n,rank)==Fraction(totals[rank-1],len(orders))


def test_array_cost_matches_closed_form_at_every_supported_size():
    for count in range(1,33):
        c=build_computed_candidate({"kind":"dynamic_array","append_count":count})
        result=evaluate_fact_evidence(c["question_spec"],c["solution"])["result"]
        assert result==count+2**count.bit_length()-1


def test_range_sums_match_prefix_difference_for_all_subranges():
    values=[3,-2,0,7,-8,1,5]
    prefix=[0,*itertools.accumulate(values)]
    for left in range(len(values)):
        for right in range(left,len(values)):
            c=build_computed_candidate({"kind":"range_sum","values":values,"start":left,"end":right})
            assert evaluate_fact_evidence(c["question_spec"],c["solution"])["result"]==prefix[right+1]-prefix[left]


def test_zipf_quantiles_match_integer_weight_oracle_including_exact_thresholds():
    for n in range(1,13):
        for alpha in range(4):
            unit=math.lcm(*(k**alpha for k in range(1,n+1)))
            weights=[unit//(k**alpha) for k in range(1,n+1)]
            total=sum(weights)
            for threshold in (Fraction(1,4),Fraction(1,2),Fraction(9,10),Fraction(1)):
                expected=next(i for i,mass in enumerate(itertools.accumulate(weights),1) if mass*threshold.denominator>=total*threshold.numerator)
                c=build_computed_candidate({"kind":"zipf_coverage","n":n,"alpha":alpha,"threshold":str(threshold)})
                assert evaluate_fact_evidence(c["question_spec"],c["solution"])["result"]==expected


def test_computed_problem_renders_readable_inputs_without_internal_plan_keys():
    c=build_computed_candidate({"kind":"arithmetic","expression":"16384/8"})
    assert "16384/8" in c["question_spec"]["stimulus"]["rendered_text"]
    assert '"kind"' not in c["question_spec"]["stimulus"]["rendered_text"]
