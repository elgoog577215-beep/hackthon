"""Notation roles are interpreted before variable and atomic-property checks."""
import pytest
from course_repository import CourseDocumentConflict


def fact(subject, prop, value):
    return {'form':'fact','subject':subject,'property':prop,'value':value,'conditions':[],'attachments':[]}


@pytest.mark.parametrize('value', [r'$\frac{d^2s}{dt^2}$', r'$\dfrac{d^{2}Q}{d t^{2}}$', r'$\frac{\mathrm{d}^2 f}{\mathrm{d}x^2}$'])
def test_differential_operators_are_not_free_quantity_variables(value):
    from knowledge_semantic_contract import quality_point
    p=fact('函数','数学表达',value)
    compiled,audit=quality_point(p,'函数的数学表达为'+value+'。',semantic_roles=True)
    assert value in compiled['claim']
    assert any(r['symbol']=='d' and r['role']=='differential_operator' for r in audit['quantity_notation_roles'])
    with pytest.raises(CourseDocumentConflict): quality_point(p,'函数的数学表达为'+value+'。')


@pytest.mark.parametrize('value', ['m/s', 'm/s$^2$', r'$\mathrm{m}\,\mathrm{s}^{-2}$', r'$\frac{m}{s^2}$'])
def test_units_in_an_explicit_unit_field_do_not_become_undefined_m_variables(value):
    from knowledge_semantic_contract import quality_point
    compiled,audit=quality_point(fact('速度','单位',value),'速度的单位为'+value+'。',semantic_roles=True)
    assert any(r['symbol']=='m' and r['role']=='unit' for r in audit['quantity_notation_roles'])


@pytest.mark.parametrize('value', ['d+1', r'$\frac{d}{m}$', r'$\frac{d^2f(d,x)}{dx^2}$', 'm/s'])
def test_free_variables_are_still_required_even_inside_differential_expressions(value):
    from knowledge_semantic_contract import quality_point
    with pytest.raises(CourseDocumentConflict,match='数量符号'):
        quality_point(fact('函数','数学表达',value),'函数的数学表达为'+value+'。',semantic_roles=True)


def test_a_relation_to_one_counterpart_is_one_property_and_grounded_in_the_source():
    from knowledge_semantic_contract import quality_point, point_variants
    from jsonschema import validate
    p=fact('静止点','与极值点关系','未必是位置函数的极值点')
    source='静止点未必是位置函数的极值点。'
    _,audit=quality_point(p,source,semantic_roles=True)
    assert audit['property_kind']=='single_relation' and audit['relation_target']=='极值点'
    validate(p,point_variants(['静止点'],contract='knowledge_extract_v9',semantic_roles=True))
    with pytest.raises(CourseDocumentConflict): quality_point(p,source)
    with pytest.raises(CourseDocumentConflict,match='关系对象'):
        quality_point(p,'静止点的一般规则。',semantic_roles=True)


def test_multiple_independent_properties_are_not_relaxed_by_relation_support():
    from knowledge_semantic_contract import quality_point
    with pytest.raises(CourseDocumentConflict,match='独立属性'):
        quality_point(fact('方法','与时间和空间复杂度关系','不同'),'方法涉及时间和空间复杂度。',semantic_roles=True)
