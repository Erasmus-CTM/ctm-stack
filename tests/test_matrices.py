"""Bounded matrix values reuse scalar parsing without losing type or form."""
from pathlib import Path
import pytest
import sympy as sp
from stack_sympy import answer_test, evaluate, InvalidAnswer, Unsupported, parse, canonical_form
from stack_sympy.expressions import MatrixValue, form_latex
from stack_sympy.engine import instantiate, validate, grade, _source, _qtest_answer, run_question_tests
from stack_sympy.importer import import_xml, UnsupportedQuestion
from scripts.native_compliance.python_runner import classify_case

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('test,student,teacher,correct,applicable,note', [
    ('AlgEquiv','matrix([x+x,1/2])','matrix([2*x,2/4])',True,True,''),
    ('AlgEquiv','matrix([1],[2])','matrix([1,2])',False,True,'ATMatrix_wrongsz_rows'),
    ('AlgEquiv','matrix([1,2])','matrix([1])',False,True,'ATMatrix_wrongsz_columns'),
    ('AlgEquiv','matrix([1,2])','matrix([2,1])',False,True,'ATMatrix_wrongentries'),
    ('AlgEquiv','matrix([1])','[[1]]',False,False,''),
    ('SameType','matrix([1])','matrix([1,2],[3,4])',True,True,''),
    ('SameType','matrix([1])','[[1]]',False,True,''),
    ('EqualComAss','matrix([x+x])','matrix([2*x])',False,True,''),
    ('EqualComAss','matrix([1+2])','matrix([3])',False,True,''),
    ('EqualComAss','matrix([x+1])','matrix([1+x])',True,True,''),
    ('EqualComAss','matrix([1])','matrix([2])',False,False,''),
    ('EqualComAss','matrix([1])','matrix([1,2])',False,False,''),
])
def test_native_matrix_contract(test, student, teacher, correct, applicable, note):
    result = answer_test(test, student, teacher)
    assert result['valid'] and result['correct'] is correct
    assert result.get('cas_valid',result['valid']) is applicable
    if note:
        assert result['note'] == note


@pytest.mark.parametrize('left,right', [('100.4-80.0','20.4'),('1/3','0.3333333333333333'),('0.1','1/10')])
def test_cell_literal_precision_matches_scalar(left,right):
    assert answer_test('AlgEquiv',f'matrix([{left}])',f'matrix([{right}])')['correct'] is answer_test('AlgEquiv',left,right)['correct']
    # Frozen aliases are exact values. Decimal aliases are rejected by the
    # question compiler because their original binary64 syntax is unavailable.
    env={'m':evaluate('matrix([102/5])')}
    assert answer_test('AlgEquiv','matrix([100.4-80.0])','m',env=env)['correct'] is False


@pytest.mark.parametrize('source', ['matrix()','matrix([])','matrix([1],[])','matrix([1],[1,2])',
    'matrix(1)','matrix([[1]])','matrix([{1}])','matrix([true])','matrix([x=1])',
    'matrix([matrix([1])])','matrix([1,])',
    'matrix('+','.join('[1]' for _ in range(17))+')',
    'matrix(['+','.join('1' for _ in range(17))+'])',
    'matrix('+','.join('['+','.join('1' for _ in range(9))+']' for _ in range(8))+')'])
def test_invalid_shape_and_entries_fail_closed(source):
    assert not answer_test('AlgEquiv',source,'matrix([1])')['valid']
    with pytest.raises((InvalidAnswer,Unsupported)):
        evaluate(source)


@pytest.mark.parametrize('source', ['matrix([x+0.1])','matrix([sin(0.1)])','ev(matrix([0.1]),simp)'])
def test_transformed_decimals_and_matrix_arithmetic_are_outside_contract(source):
    with pytest.raises(Unsupported):
        evaluate(source)


def test_matrix_roundtrip_and_written_rendering():
    value=evaluate('matrix([x+x,1/2],[3,4])')
    assert isinstance(value,MatrixValue) and value.shape==(2,2)
    assert evaluate(_source(value))==value
    assert canonical_form('matrix([1,x])')==canonical_form('m',{'m':evaluate('matrix([1,x])')})
    assert canonical_form('matrix([x+x])')!=canonical_form('matrix([2*x])')
    latex=form_latex(parse('matrix([x+x,0.1,1/2])'))
    assert 'x + x' in latex and '0.1' in latex and r'\frac{1}{2}' in latex and r'\begin{pmatrix}' in latex
    for source in ('matrix([1])+matrix([2])','matrix([1])*2','sin(matrix([1]))','[matrix([1])]','{matrix([1])}',
                   'ev(matrix([1]),simp)','diff(matrix([x]),x)','expand(matrix([x+x]))'):
        with pytest.raises((Unsupported,InvalidAnswer)):
            evaluate(source,student=True)
        with pytest.raises((Unsupported,InvalidAnswer)):
            evaluate(source)


@pytest.mark.parametrize('test',['Sets','FacForm','SingleFrac','LowestTerms','NumAbsolute','NumRelative','NumDecPlaces'])
def test_explicit_port_answer_test_boundary(test):
    with pytest.raises(Unsupported,match='Matrices require'):
        answer_test(test,'matrix([1])','matrix([1])','2')
    assert classify_case(dict(test=test,student='matrix([1])',teacher='matrix([1])',options='2'))['kind']=='unsupported'


def question():
    q=import_xml(ROOT/'questions/polynomial-expansion.xml')[0]
    q.update(variables='a:rand(8)+1; ta:matrix([a,x]);',questiontext='Enter [[input:ans]] [[validation:ans]] {@ta@}',qtests=[])
    q['inputs'][0].update(type='matrix',teacher='ta',syntaxhint='',matrix=None)
    q['prts'][0]['nodes'][0].update(test='AlgEquiv',teacher='ta')
    return q


def test_frozen_variants_validation_grading_and_shape_policy():
    q=question();v=instantiate(q,17)
    assert v==instantiate(q,17)
    assert '\\begin{pmatrix}' in v['question_html']
    raw=v['env']['ta']
    assert validate(q,{'ans':raw},variant=v)['status']=='valid'
    assert grade(q,{'ans':raw},variant=v)['score']==1
    for raw in ('[[1,x]]','matrix([1])','matrix([1],[x])','matrix([,x])'):
        assert validate(q,{'ans':raw},variant=v)['status']=='invalid'
    q['inputs'][0]['matrix']={axis:dict(auto=True,initial=1,min=1,max=3) for axis in ('rows','cols')}
    v=instantiate(q,17)
    assert validate(q,{'ans':'matrix([1])'},variant=v)['status']=='valid'
    assert grade(q,{'ans':'matrix([1])'},variant=v)['score']==0


def test_qtest_replay_preserves_decimal_cells_and_form():
    q=question();env={'a':sp.Integer(2),'ta':evaluate('matrix([2,x])')}
    source='matrix([100.4-80.0])'
    assert not answer_test('AlgEquiv',_qtest_answer(q,source,env),'matrix([20.4])')['correct']
    assert _qtest_answer(q,'matrix([x+x,1/2])',env,preserve_form=True)=='matrix([(x+x),(1/2)])'
    q['qtests']=[dict(testcase=1,inputs={'ans':'ta'},expected={q['prts'][0]['name']:dict(score=1,penalty=0,note='()')})]
    assert run_question_tests(q,seeds=[17,29])['passed']


def test_held_castext_keeps_matrix_cell_operations_and_alias_loss_fails_closed():
    q=question();q['simplify']=False
    q['questiontext']+='{@matrix([x+x,1/2])@}'
    assert 'x + x' in instantiate(q,17)['question_html']
    q['variables']='a:1; ta:matrix([x+x]); alias:ta;'
    q['prts'][0]['nodes'][0].update(test='EqualComAss',teacher='alias')
    with pytest.raises(UnsupportedQuestion,match='loses unsimplified answer form'):
        instantiate(q,17)


@pytest.mark.parametrize('resizable,source', [
    (True,'matrix([1],[2],[3],[4],[5])'),
    (False,'matrix([1])'),
])
def test_qtest_matrix_shape_is_rejected_during_instantiation(resizable,source):
    q=question();q['variables']='a:1; ta:matrix([1,2],[3,4]);'
    if resizable:
        q['inputs'][0]['matrix']={axis:dict(auto=True,initial=2,min=1,max=4) for axis in ('rows','cols')}
    q['qtests']=[dict(testcase=1,inputs={'ans':source},expected={})]
    with pytest.raises(UnsupportedQuestion,match=r'qtest\[1\]/testinput\[ans\].*configured dimensions'):
        instantiate(q,17)


@pytest.mark.parametrize('axis,config', [
    ('rows',dict(auto=False,initial=1,min=1,max=1)),
    ('cols',dict(auto=False,initial=1,min=1,max=1)),
    ('rows',dict(auto=True,initial=3,min=3,max=4)),
    ('cols',dict(auto=True,initial=1,min=1,max=1)),
])
def test_matrix_teacher_shape_must_be_reachable_without_qtests(axis,config):
    q=question();q['variables']='a:1; ta:matrix([1,2],[3,4]);'
    q['inputs'][0]['matrix']={key:dict(auto=True,initial=2,min=1,max=4) for key in ('rows','cols')}
    q['inputs'][0]['matrix'][axis]=config
    assert q['qtests']==[]
    with pytest.raises(UnsupportedQuestion,match=r'input\[ans\]/tans.*teacher matrix must fit'):
        instantiate(q,17)


def test_resizable_initial_shape_can_differ_from_reachable_teacher():
    q=question();q['variables']='a:1; ta:matrix([1,2],[3,4]);'
    q['inputs'][0]['matrix']={axis:dict(auto=True,initial=1,min=1,max=4) for axis in ('rows','cols')}
    variant=instantiate(q,17)
    assert grade(q,{'ans':variant['env']['ta']},variant=variant)['score']==1


@pytest.mark.parametrize('where',['variable','teacher','qtest','castext','dynamic'])
def test_matrix_provenance_guards(where):
    q=question()
    if where=='variable':q['variables']='a:1; ta:matrix([0.1,x]);'
    if where=='teacher':q['variables']+=' d:0.1;';q['inputs'][0]['teacher']='matrix([d,x])'
    if where=='qtest':q['qtests']=[dict(testcase=1,inputs={'ans':'matrix([x+0.1])'},expected={})]
    if where=='castext':q['variables']+=' d:0.1;';q['questiontext']+='{@matrix([d])@}'
    if where=='dynamic':q['prts'][0]['nodes'][0]['teacher']='matrix([ans])'
    with pytest.raises(UnsupportedQuestion):
        instantiate(q,17)
