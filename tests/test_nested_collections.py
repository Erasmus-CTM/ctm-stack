"""Nested collection contracts, held form, native applicability and author helpers."""
from pathlib import Path
import copy
import json
import pytest
import sympy as sp
from stack_sympy import answer_test, evaluate, Unsupported, InvalidAnswer, canonical_form
from stack_sympy.expressions import HeldList, HeldSet, form_latex, parse, assignments
from stack_sympy.engine import instantiate, validate, grade, run_question_tests, _source
from stack_sympy.importer import import_xml, UnsupportedQuestion
from scripts.native_compliance.python_runner import classify_case

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('test,student,teacher,correct,applicable',[
 ('AlgEquiv','[1,[x+x]]','[1,[2*x]]',True,True),
 ('AlgEquiv','{[x+x]}','{[2*x]}',True,True),
 ('AlgEquiv','{[1,2]}','{[2,1]}',False,True),
 ('AlgEquiv','[{1,1}]','[{1}]',True,True),
 ('AlgEquiv','[[1]]','[{1}]',False,False),
 ('Sets','{[1,1]}','{[1]}',False,True),
 ('Sets','{{1,1}}','{{1}}',True,True),
 ('Sets','{[1,2],[1,2]}','{[1,2]}',True,True),
 ('SameType','[1,[2]]','[9,[3]]',True,True),
 ('SameType','[1,[2]]','[9,{3}]',False,True),
 ('SameType','[1,[2]]','[9]',True,True),
 ('SameType','{[1,2]}','{{1,2}}',True,True),
 ('SameType','1','x',True,True),
 ('SameType','1','[1]',False,True),
 ('EqualComAss','{1,2,2}','{2,1,2}',True,True),
 ('EqualComAss','{4,4}','{4}',False,True),
 ('EqualComAss','[[1,2],{3,4}]','[[1,2],{4,3}]',True,True),
 ('EqualComAss','[[1,2],{3,4}]','[[2,1],{3,4}]',False,False),
 ('EqualComAss','[{x+x},1]','[{2*x},1]',False,True),
])
def test_nested_comparisons_match_pinned_native(test,student,teacher,correct,applicable):
    result=answer_test(test,student,teacher)
    assert result['valid'] and result['correct'] is correct and result['cas_valid'] is applicable


@pytest.mark.parametrize('left,right',[('452','4.52*10^2'),('100.4-80.0','20.4'),('1/3','0.3333333333333333')])
def test_nested_list_leaves_keep_literal_float_semantics(left,right):
    assert answer_test('AlgEquiv',f'[[{left}]]',f'[[{right}]]')['correct'] is answer_test('AlgEquiv',left,right)['correct']


def test_hashable_set_members_roundtrip_and_preview_keep_raw_multiplicity():
    value=evaluate('{[1,2],{1,1},[1,2]}',student=True)
    assert isinstance(value.args[0],HeldList)
    hash(value)
    assert evaluate(_source(value))==value
    assert 'duplicates' in answer_test('Sets','{[1,2],[1,2]}','{[1,2]}')['note']
    assert 'duplicates' not in answer_test('Sets','{{1,1}}','{{1}}')['note']
    assert canonical_form('{1,1}')!=canonical_form('{1}')
    latex=form_latex(parse('{{x+x},[1,1]}'))
    assert 'x + x' in latex and r'\left[' in latex
    env=assignments('a:[[1],[2]]; b:rand(a); c:a[1];')
    assert env['b'] in ([1],[2]) and env['c']==[1]
    assert evaluate('s[1]',{'s':evaluate('{[1]}').args[0]})==1


@pytest.mark.parametrize('source,match',[
 ('['*7+'1'+']'*7,'levels'),
 ('['+','.join(['['+','.join(['1']*32)+']']*4)+']','nodes'),
 ('{[true]}','scalar'), ('[[x=1]]','scalar'),
])
def test_nested_whole_tree_bounds_and_scalar_leaves(source,match):
    with pytest.raises(Unsupported,match=match):evaluate(source,student=True)
    assert classify_case(dict(test='AlgEquiv',student=source,teacher='[1]',options=''))['kind']=='unsupported'


@pytest.mark.parametrize('source,expected',[
 ('union({1,2},{2,3})','{1,2,3}'), ('union()','{}'),
 ('intersection({1,2},{2,3})','{2}'), ('intersection({1,2})','{1,2}'),
 ('setdifference({1,2},{2})','{1}'), ('set(2,1,1)','{1,2}'),
 ('setify([2,1,1])','{1,2}'), ('listify({2/4,1/3})','[1/3,1/2]'),
 ('listify([2,1,1])','[2,1,1]'), ('cardinality({{1,1},{1}})','1'),
 ('member([x+x],{[2*x]})','true'), ('member(2,[1,2])','true'),
 ('subsetp({[x+x]},{[2*x]})','true'), ('subsetp({1,3},{1,2})','false'),
])
def test_finite_author_helpers(source,expected):
    assert answer_test('AlgEquiv',expected,source)['correct']
    with pytest.raises(InvalidAnswer,match='not allowed'):
        evaluate(source,student=True)
    with pytest.raises(Unsupported,match='simplification'):
        evaluate(source,simplify=False)


@pytest.mark.parametrize('source', ['setify({1,2})','union([1],{2})','intersection()',
                                    'cardinality([1])','subsetp([1],{1})','member(1,2)','setdifference({1})'])
def test_author_helper_types_and_arities(source):
    with pytest.raises(InvalidAnswer):evaluate(source)


@pytest.mark.parametrize('source,match',[
 ('listify({x,1})','ordering'),('listify({[1],2})','ordering'),
 ('setify([0.1])','exact fractions'),
 ('union({'+','.join(str(i) for i in range(20))+'},{'+','.join(str(i) for i in range(20,40))+'})','entries'),
])
def test_author_helper_order_precision_and_output_bounds(source,match):
    with pytest.raises(Unsupported,match=match):evaluate(source)


def base_question():return import_xml(ROOT/'questions/finite-collections.xml')[0]


def test_simplified_author_helpers_freeze_before_sets_and_form_checks():
    q=base_question();q['variables']='a:6; ordered:listify({2,1,1}); unordered:union({1,2},{2,3});'
    v=instantiate(q,17)
    assert v['env']['ordered']=='[1,2]' and len(evaluate(v['env']['unordered']).args)==3
    a={'sequence':'[1,2]','members':'{3,2,1}','explained':'{1,2,3,3}'}
    assert grade(q,a,variant=v)['score']==1
    q['prts'][1]['nodes'][0]['test']='EqualComAss'
    assert grade(q,a,variant=instantiate(q,17))['prts']['unordered']['score']==1
    a['members']='{1,2,3,3}'
    assert grade(q,a,variant=instantiate(q,17))['prts']['unordered']['score']==0
    q['variables']='a:6; ordered:[1,2]; unordered:{1,1,2};'
    assert len(evaluate(instantiate(q,17)['env']['unordered']).args)==2


@pytest.mark.parametrize('test',['Sets','EqualComAss'])
def test_held_direct_teacher_helpers_fail_closed(test):
    with pytest.raises(Unsupported,match='frozen evaluated'):
        answer_test(test,'{1,2}','setify([1,2])')
    q=base_question();q['prts'][1]['nodes'][0].update(test=test,teacher='setify([1,2])')
    with pytest.raises(UnsupportedQuestion,match='frozen evaluated'):
        instantiate(q,17)


def test_unsimplified_helper_contexts_and_feedback_variables_fail_at_build():
    q=base_question();q['simplify']=False;q['variables']='a:6; ordered:listify({1,2}); unordered:{1,2};'
    with pytest.raises(UnsupportedQuestion,match='questionsimplify=1'):instantiate(q,17)
    q=base_question();q['prts'][0]['feedbackvariables']='s:union({1},{2});'
    with pytest.raises(UnsupportedQuestion,match='frozen in simplified'):instantiate(q,17)
    q=base_question();q['simplify']=False;q['prts'][0]['nodes'][0]['teacher']='listify({1,2})'
    with pytest.raises(UnsupportedQuestion,match='questionsimplify=1'):instantiate(q,17)
    q=base_question();q['simplify']=False;q['qtests'][0]['inputs']['sequence']='listify({1,2})'
    with pytest.raises(UnsupportedQuestion,match='questionsimplify=1'):instantiate(q,17)


def test_new_xml_examples_replay_and_validate_nested_types():
    for name in ['nested-collections.xml','finite-author-helpers.xml']:
        q=import_xml(ROOT/'questions'/name)[0]
        assert run_question_tests(q,seeds=[17,29,47])['passed']


def test_nested_checkanswertype_follows_native_applicability():
    q=base_question();q['variables']='a:6; ordered:[[1],2]; unordered:{1,2};';v=instantiate(q,17)
    answers={'sequence':'[{1},2]','members':'{1,2}','explained':'{1,2}'}
    assert validate(q,answers,variant=v)['status']=='invalid'
    answers['sequence']='[{1}]'  # Wrong length: SameType is still applicable.
    assert validate(q,answers,variant=v)['status']=='valid'
    assert grade(q,answers,variant=v)['prts']['ordered']['score']==0


def test_collection_form_aliases_are_verified_transitively():
    q=base_question();q['simplify']=False;q['qtests']=[]
    q['variables']='a:6; ordered:[1,2]; unordered:{1,1,2}; alias:unordered;'
    q['prts'][1]['nodes'][0].update(test='EqualComAss',teacher='alias')
    v=instantiate(q,17)
    a={'sequence':'[1,2]','members':'{2,1,1}','explained':'{1,2}'}
    assert grade(q,a,variant=v)['prts']['unordered']['score']==1
    q['variables']='a:6; ordered:[1,2]; unordered:{x+x,2}; alias:unordered;'
    with pytest.raises(UnsupportedQuestion,match='loses unsimplified answer form'):
        instantiate(q,17)
    # A qtest alias can also lose its written form even when the teacher is stable.
    q=base_question();q['simplify']=False;q['variables']='a:6; ordered:[1,2]; unordered:{1,2}; raw:[x+x]; alias:raw;'
    q['prts'][0]['nodes'][0].update(test='EqualComAss',teacher='[2*x]')
    q['qtests'][0]['inputs']['sequence']='alias'
    with pytest.raises(UnsupportedQuestion,match='loses unsimplified answer form'):
        instantiate(q,17)


def test_mixed_transformation_cannot_hide_lost_collection_leaf_form():
    q=base_question();q['simplify']=False;q['qtests']=[]
    q['variables']='a:6; ordered:[1,2]; p:factor(x)+x+x; unordered:{p,2}; alias:unordered;'
    q['prts'][1]['nodes'][0].update(test='EqualComAss',teacher='alias')
    with pytest.raises(UnsupportedQuestion,match='loses unsimplified answer form'):
        instantiate(q,17)


@pytest.mark.parametrize('source',['{0.1}','{{0.1}}','{[0.5]}','[{1e-1}]'])
def test_decimal_set_literals_fail_closed(source):
    for test in ('AlgEquiv','Sets','EqualComAss','SameType'):
        assert not answer_test(test,source,'{1/10}')['valid']
    with pytest.raises(Unsupported,match='exact fractions'):
        evaluate(source)
    assert classify_case(dict(test='AlgEquiv',student=source,teacher='{1/10}',options=''))['kind']=='unsupported'


@pytest.mark.parametrize('where',['input','prt','qtest','castext','feedback'])
@pytest.mark.parametrize('source',['{d}','set(d)','cardinality({d,1/10})','[d]'])
def test_decimal_scalar_aliases_cannot_enter_collection_expressions(where,source):
    q=base_question();q['variables']='a:6; ordered:[1,2]; unordered:{1,2}; f:0.1; d:f;'
    if where=='input':q['inputs'][0]['teacher']=source
    if where=='prt':q['prts'][0]['nodes'][0]['teacher']=source
    if where=='qtest':q['qtests'][0]['inputs']['sequence']=source
    if where=='castext':q['questiontext']+='{@'+source+'@}'
    if where=='feedback':q['prts'][0]['nodes'][0]['true']['feedback']='{@'+source+'@}'
    with pytest.raises(UnsupportedQuestion,match='Decimal aliases'):
        instantiate(q,17)


def test_dynamic_collection_construction_and_indirect_student_alias_fail_closed():
    q=base_question();q['prts'][0]['feedbackvariables']='v:sequence;'
    q['prts'][0]['nodes'][0]['student']='v'
    with pytest.raises(UnsupportedQuestion,match='direct learner input'):
        instantiate(q,17)
    for source in ('{sequence}','setify(sequence)','member(1,sequence)'):
        q=base_question();q['prts'][0]['nodes'][0]['teacher']=source
        with pytest.raises(UnsupportedQuestion,match='derived from learner inputs'):
            instantiate(q,17)


def test_literal_list_qtest_answers_keep_binary64_arithmetic():
    from stack_sympy.engine import _qtest_answer
    q=base_question()
    source='[[100.4-80.0]]'
    assert not answer_test('AlgEquiv',_qtest_answer(q,source,{}),'[[20.4]]')['correct']


@pytest.mark.parametrize('source',['ev([100.4-80.0],simp)','[ev(100.4-80.0,simp)]','expand([[0.1]])',
                                    '[sin(0.1)]','[[sqrt(0.5)]]','[exp(0.1)]','[x+0.1]'])
def test_transformed_decimal_lists_fail_closed(source):
    with pytest.raises(Unsupported):
        answer_test('AlgEquiv','[20.4]',source)
    q=base_question();q['qtests'][0]['inputs']['sequence']=source
    with pytest.raises(UnsupportedQuestion,match='literal precision'):
        instantiate(q,17)


def test_learner_decimal_qvar_aliases_fail_validation_and_exact_teachers_keep_float_path():
    q=base_question();q['variables']='a:6; ordered:[102/5]; unordered:{1,2}; d:100.4-80.0; alias:d;'
    v=instantiate(q,17)
    for source in ('[d]','[[alias]]','{d}'):
        result=validate(q,{'sequence':source,'members':'{1,2}','explained':'{1,2}'},variant=v)
        assert not result['inputs']['sequence']['valid']
        assert 'exact fractions' in result['inputs']['sequence']['feedback']
    assert not answer_test('AlgEquiv','[100.4-80.0]','ordered',env={'ordered':[sp.Rational(102,5)]})['correct']
    assert not answer_test('AlgEquiv','[[100.4-80.0]]','ordered',env={'ordered':[[sp.Rational(102,5)]]})['correct']
