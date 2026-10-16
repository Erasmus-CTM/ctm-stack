"""Function proofs, rejection-only probes, and held STACK logical semantics."""
import sympy as sp
import pytest
from unittest.mock import patch
from stack_sympy import answer_test, evaluate, parse, Unsupported, InvalidAnswer
from stack_sympy.expressions import form_latex, Logical, Equation
from stack_sympy.equivalence import numerically_distinct, elementary_equivalent
from stack_sympy.logic import validate_logic


@pytest.mark.parametrize('left,right', [
    ('1/(1+exp(-2*x))', 'tanh(x)/2+1/2'),
    ('cosh(x)^2-sinh(x)^2', '1'), ('2*sinh(x)', 'exp(x)-exp(-x)'),
    ('cosech(3*x)+1','csch(3*x)+1'), ('cosec(x)', '1/sin(x)'),
    ('sech(x)', '1/cosh(x)'), ('coth(x)', 'cosh(x)/sinh(x)'),
    ('sec(x)', '1/cos(x)'), ('cot(x)', 'cos(x)/sin(x)'),
])
def test_elementary_identities(left, right):
    assert answer_test('AlgEquiv', left, right)['correct']


@pytest.mark.parametrize('source', ['csch(0)', 'cosec(0)', 'coth(0)', 'true+1', 'sin(x=0)'])
def test_poles_and_mixed_types_rejected(source):
    with pytest.raises((InvalidAnswer, Unsupported)):
        evaluate(source, student=True)


def test_numerical_screen_only_rejects_and_short_circuits_bad_candidates():
    x, y = sp.symbols('x y')
    assert numerically_distinct(sp.cosh(x), sp.sinh(x))
    assert numerically_distinct(x+y, 2*x)  # union of variables, distinct probes
    with patch('stack_sympy.equivalence.sp.cancel', side_effect=AssertionError('expensive path')):
        assert not elementary_equivalent(sp.cosh(x), sp.sinh(x))
    # These different polynomials agree at both selected probe points.
    p = (sp.sqrt(2)+sp.pi)/4
    candidate = x + (x-2)*(x-p)
    assert not numerically_distinct(candidate, x)
    assert not elementary_equivalent(candidate, x)
    # Close samples do not grant a tolerance to AlgEquiv.
    assert not elementary_equivalent(x+sp.Rational(1,10**20), x)
    assert not numerically_distinct(sp.tanh(x), 1/(1+sp.exp(-2*x))*2-1)
    # First probe hits a pole. The subsequent probe may still reject.
    assert numerically_distinct(1/(x-2), 1/(x-2)+1)
    assert not numerically_distinct(sp.I*x, sp.I*x+sp.I)  # nonreal probes skipped


@pytest.mark.parametrize('left,right', [
    ('a and b', 'b nounand a'), ('not(a and b)', 'not a or not b'),
    ('a or a', 'a and true'), ('a or not a','true'), ('not true','false'),
    ('a or b and c', 'a or (b and c)'),
    ('nounnot(a nounor b)', '(not a) and (not b)'),
    ('true','x=x'), ('false','1=2'),
])
def test_pure_boolean_equivalence(left, right):
    assert answer_test('AlgEquiv',left,right)['correct']


@pytest.mark.parametrize('left,right', [
    ('a and b','a or b'), ('true','1'), ('a=0','a'), ('false','x=1'),
])
def test_boolean_type_and_truth_differences(left,right):
    assert not answer_test('AlgEquiv',left,right)['correct']


@pytest.mark.parametrize('left,right,correct', [
    ('a=0 or b=0','a*b=0',True), ('a*b=0','a=0 or b=0',True),
    ('a*x=a*y','a=0 or x=y',True), ('a*x=a*y','x=y',False),
    ('a^3*b^3=0','a=0 or b=0',False), ('a^3*b^3=0','a*b=0',False),
    ('(x-2)^2=0','x=2',False), ('x^2=4','x=2 or x=-2',True),
    ('(x-1)*(x-4)=0 or (x-2)*(x-4)=0','x=1 or x=2 or x=4',False),
    ('(x-1)*(x-4)=0 or (x-2)*(x-4)=0','x=1 or x=2 or x=4 or x=4',True),
    ('x+y=i','y=i-x',True), ('x/2=y/3','3*x=2*y',True),
    ('x=0 or x=0','x^2=0',True), ('2*x=2','x=1',True),
])
def test_polynomial_equation_semantics(left,right,correct):
    assert answer_test('AlgEquiv',left,right)['correct'] is correct


@pytest.mark.parametrize('source', [
    'x/x=1', '0/x=0', '(x^2-1)/(x-1)=x+1', 'sin(x)=0', 'x^(-1)=1',
    'x^(1/2)=1', 'x=0 and y=0', 'not(x=0)', 'x=0 or a',
    '(a+b+c+d+e+f+g+h)^100=0', 'a or b or c or d or f or g or h or j or k',
])
def test_scope_boundaries_are_explicit(source):
    with pytest.raises(Unsupported):
        validate_logic(evaluate(source))


def test_held_types_preserve_branches_and_serialize():
    value = evaluate('x=0 or x=0')
    assert isinstance(value, Logical) and len(value.operands) == 2
    assert isinstance(value.operands[0], Equation)
    assert evaluate(str(value)) == value
    assert r'\lor' in form_latex(parse('a=0 or b=0'))
    assert r'\lnot' in sp.latex(evaluate('not a'))
    with pytest.raises(Unsupported, match='require AlgEquiv'):
        answer_test('EqualComAss','true','true')


def test_stack_type_applicability_and_equation_boolean_asymmetry():
    for left, right in [('1','x=1'),('x=x','true'),('1=2','false'),('a or a','a')]:
        result = answer_test('AlgEquiv', left, right)
        assert result['valid'] and not result['correct'] and not result['cas_valid']
    assert answer_test('AlgEquiv','false','1=2')['correct']


def test_numeric_principal_complex_root_and_equalcomass_applicability():
    left = '(4*sqrt(3)*%i+4)^(1/5)'
    right = '8^(1/5)*(cos(%pi/15)+%i*sin(%pi/15))'
    assert answer_test('AlgEquiv', left, right)['correct']
    result = answer_test('EqualComAss', left, right)
    assert result['valid'] and result['cas_valid'] and not result['correct']
    assert answer_test('AlgEquiv','5/4*exp(%i*%pi/6)','5*sqrt(3)/8+5/8*%i')['correct']
    # Equality of fifth powers does not establish equality of principal roots.
    assert not answer_test('AlgEquiv','(-1)^(1/5)','-1')['correct']
    assert not answer_test('AlgEquiv','((-1)*(-1))^(1/2)','(-1)^(1/2)*(-1)^(1/2)')['correct']
    assert not answer_test('AlgEquiv','(z^5)^(1/5)','z')['correct']
