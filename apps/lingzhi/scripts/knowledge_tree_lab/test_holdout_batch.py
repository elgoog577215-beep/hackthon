from copy import deepcopy
from .test_foundation_round import sample
from .holdout_batch import prefix_records
from .foundation_round import validate_inventory,validate_atoms


def test_batch_ids_do_not_collide_and_preserve_facts_and_sources():
    course,inventory,atoms,_=sample();before=deepcopy((inventory,atoms))
    i1,a1=prefix_records(inventory,atoms,'M1');i2,a2=prefix_records(inventory,atoms,'M2')
    assert (inventory,atoms)==before
    assert a1['points'][0]['key']!=a2['points'][0]['key']
    assert i1['claims'][0]['quote']==inventory['claims'][0]['quote']
    assert i1['claims'][0]['source_ref']==inventory['claims'][0]['source_ref']
    assert a1['points'][0]['statement']==atoms['points'][0]['statement']
    assert not validate_atoms(i1,a1) and not validate_atoms(i2,a2)


def test_batching_does_not_silently_correct_invalid_model_output():
    course,inventory,atoms,_=sample();inventory['claims'][0]['kind']='reason'
    inventory['claims'][1]['quote']='不存在的原文'
    inv,doc=prefix_records(inventory,atoms,'M1')
    assert inv['claims'][0]['kind']=='reason'
    errors=validate_inventory(course,inv)
    assert 'claim_shape' in errors
    assert 'unanchored_quote:M1_C2' in errors
