"""Flat finite collections across parser, frozen XML, grading and preflight."""
from pathlib import Path
import copy
import json
import pytest
import sympy as sp

from stack_sympy import answer_test, evaluate, Unsupported
from stack_sympy.expressions import HeldSet, assignments, form_latex, parse, MAX_COLLECTION_ITEMS
from stack_sympy.engine import grade, instantiate, validate, run_question_tests, _source, _qtest_answer
from stack_sympy.importer import import_xml, UnsupportedQuestion
from scripts.native_compliance.python_runner import classify_case, evaluate_case

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('student,teacher,correct', [
    ('[]','[]',True), ('[1,2]','[1,2]',True), ('[2,1]','[1,2]',False),
    ('[1,1]','[1]',False), ('[x+x,sin(x)^2+cos(x)^2]','[2*x,1]',True),
    ('{}','{}',True), ('{2,1}','{1,2}',True), ('{1,1+1,2}','{2,1}',True),
    ('{2/4,x+x}','{2*x,1/2}',True), ('{1,3}','{1,2}',False),
    # Prepared member comparison is intentionally weaker than scalar AlgEquiv.
    ('{(x+1)^2}','{x^2+2*x+1}',False),
    ('{sin(x)^2+cos(x)^2}','{1}',False),
])
def test_collection_algequiv(student, teacher, correct):
    result = answer_test('AlgEquiv',student,teacher)
    assert result['valid'] and result['correct'] is correct and result['cas_valid']


@pytest.mark.parametrize('test,student,teacher', [
    ('AlgEquiv','1','[1]'), ('AlgEquiv','[1]','{1}'), ('AlgEquiv','{1}','1'),
    ('Sets','[1]','{1}'), ('Sets','{1}','1'),
])
def test_type_mismatch_is_syntactically_valid_cas_inapplicable(test,student,teacher):
    result=answer_test(test,student,teacher)
    assert result['valid'] and not result['cas_valid'] and not result['correct']


@pytest.mark.parametrize('source', ['[true]','{x=1}','[x or y]',
                                     '['+','.join(['1']*(MAX_COLLECTION_ITEMS+1))+']'])
def test_flat_scalar_boundary(source):
    with pytest.raises(Unsupported):
        evaluate(source,student=True)
    case=dict(id='boundary',test='AlgEquiv',student=source,teacher='[1]',options='')
    assert classify_case(case)['kind']=='unsupported'


@pytest.mark.parametrize('test', ['FacForm','SingleFrac','LowestTerms','NumAbsolute','NumRelative','NumDecPlaces'])
def test_collections_reject_other_answer_tests(test):
    with pytest.raises(Unsupported,match='Collections require'):
        answer_test(test,'[1]','[1]','1')
    assert classify_case(dict(test=test,student='[1]',teacher='[1]',options='1'))['kind']=='unsupported'


def test_sets_feedback_and_original_multiplicity_survive_alias_and_freeze():
    env=assignments('ta:{1,2}; response:{1,1+1,2}; nested:[[1],[2]]; choice:rand([1,2]); selected:nested[2];')
    frozen={name:_source(value) for name,value in env.items()}
    thawed={name:evaluate(source) for name,source in frozen.items()}
    assert len(thawed['response'].args)==3
    correct=answer_test('Sets','response','ta',env=thawed)
    assert correct['correct'] and 'duplicates' in correct['note']
    wrong=answer_test('Sets','{1,3,3}','{1,2}')
    assert not wrong['correct']
    assert all(s in wrong['feedback'] for s in ['Repeated','Extra elements: 3','Missing elements: 2'])
    assert answer_test('Sets','{}','{}')['correct']
    assert evaluate('nested[2]',env)==[sp.Integer(2)]
    assert evaluate('nested',env,student=True)==[[sp.Integer(1)],[sp.Integer(2)]]
    assert evaluate('['+','.join(['1']*MAX_COLLECTION_ITEMS)+']',student=True)


def test_written_previews_and_member_validation():
    assert form_latex(parse('{x+x,2/4,1,1}')) == r'\left\{x + x, \frac{2}{4}, 1, 1\right\}'
    assert form_latex(parse('[]'))==r'\left[\right]'
    assert not answer_test('Sets','{1/0}','{1}')['valid']
    assert evaluate_case(dict(id='bad-teacher',test='Sets',student='{1}',teacher='{1/0}',options=''))['kind']=='invalid_teacher'


def question():
    return import_xml(ROOT/'questions/finite-collections.xml')[0]


def test_frozen_xml_collections_validate_grade_and_replay():
    q=question();variant=instantiate(q,17);a=variant['env']['a']
    answers={'sequence':f'[{a},2*x]', 'members':f'{{2*x,{a}}}', 'explained':f'{{{a},2*x,2*x}}'}
    json.dumps(variant)
    preview=validate(q,answers,variant=variant)
    assert preview['status']=='valid' and 'score' not in preview
    assert r'\left\{' in preview['inputs']['explained']['latex']
    result=grade(q,answers,variant=variant)
    assert result['score']==1 and 'Repeated' in result['feedback']
    assert run_question_tests(q,seeds=[17,29,47])['passed']
    answers['sequence']=f'[2*x,{a}]'
    assert grade(q,answers,variant=variant)['prts']['ordered']['score']==0
    answers['sequence']=f'{{{a},2*x}}'
    assert validate(q,answers,variant=variant)['status']=='invalid'
    q['inputs'][0]['checkanswertype']=False
    assert grade(q,answers,variant=variant)['prts']['ordered']['score']==0
    assert _qtest_answer(q,'{1,1+1,2}',{},preserve_form=True)=='{1,(1+1),2}'


def test_question_build_fails_for_outside_scope_and_nested_aliases():
    for test in ['LowestTerms','NumAbsolute']:
        q=question();q['prts'][0]['nodes'][0]['test']=test
        with pytest.raises(UnsupportedQuestion,match='Collections require'):
            instantiate(q,17)
    q=question();q['variables']+=' broken:[[true]];';q['inputs'][0]['teacher']='broken'
    with pytest.raises(UnsupportedQuestion,match='scalar'):
        instantiate(q,17)
    q=question();q['inputs'][0]['type']='numerical'
    with pytest.raises(UnsupportedQuestion,match='numerical answer'):
        instantiate(q,17)
    q=question();q['variables']+=' f:[float(1/3)];'
    with pytest.raises(UnsupportedQuestion,match='floating-point variables'):
        instantiate(q,17)



@pytest.mark.parametrize('left,right', [('452','4.52*10^2'),('100.4-80.0','20.4'),('1/3','0.3333333333333333')])
def test_list_elements_preserve_scalar_literal_float_semantics(left,right):
    assert answer_test('AlgEquiv',f'[{left}]',f'[{right}]')['correct'] is answer_test('AlgEquiv',left,right)['correct']



def test_author_feedback_variables_can_index_typed_input_lists():
    q=question();prt=q['prts'][0];prt['feedbackvariables']='head:sequence[1];'
    prt['nodes'][0]['student']='head';prt['nodes'][0]['teacher']='a'
    variant=instantiate(q,17);a=variant['env']['a']
    answers={'sequence':f'[{a},x]', 'members':f'{{{a},2*x}}', 'explained':f'{{{a},2*x}}'}
    assert grade(q,answers,variant=variant)['score']==1
    answers['sequence']='[999,x]'
    assert grade(q,answers,variant=variant)['prts']['ordered']['score']==0


@pytest.mark.parametrize('response',['1/[1]','[1]/2'])
def test_lowest_terms_validation_rejects_collection_arithmetic(response):
    q=question();q['inputs'][0]['requirelowestterms']=True;v=instantiate(q,17)
    answers={'sequence':response,'members':'{1}','explained':'{1}'}
    assert validate(q,answers,variant=v)['status']=='invalid'
    assert grade(q,answers,variant=v)['status']=='invalid'


@pytest.mark.parametrize('definition',['ordered:[4.52*10^2,x];','d:4.52; ordered:[d*10^2,x];'])
def test_decimal_collection_definitions_fail_closed_when_freezing(definition):
    q=question();q['variables']='a:6; unordered:{6,2*x};'+definition
    with pytest.raises(UnsupportedQuestion,match='decimal collection variables'):
        instantiate(q,17)


@pytest.mark.parametrize('test', ['AlgEquiv','Sets'])
def test_set_trig_members_remain_structural(test):
    assert not answer_test(test,'{sin(x)^2+cos(x)^2}','{1}')['correct']
    expression='{'+ '*'.join(f'sin(x{i})' for i in range(32))+'}'
    assert answer_test(test,expression,expression)['correct']
