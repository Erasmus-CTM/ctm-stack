"""Regressions for the seven previously ungraded upstream input/error cases."""
from itertools import product
import json
from pathlib import Path
import sys

import pytest
import sympy as sp
from stack_sympy import InvalidAnswer, Unsupported, answer_test, evaluate, parse
from stack_sympy.expressions import form_latex
from stack_sympy.logic import validate_logic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from native_compliance.common import matches_desired
from native_compliance.python_runner import classify_case, evaluate_case

LEGACY = json.loads((ROOT / 'tests/native_compliance/fixtures.json').read_text())['cases']
SEVEN = [LEGACY[i - 1] for i in (495, 496, 497, 498, 500, 1697, 1735)]


@pytest.mark.parametrize('case', SEVEN, ids=lambda c: str(c['ordinal']))
def test_seven_cases_are_supported_and_match_the_authored_result(case):
    assert classify_case(case) == {'kind': 'supported'}
    observed = evaluate_case(case)
    assert observed['kind'] == 'result' and observed['valid']
    assert matches_desired(observed, case['expected_score'], case.get('answer_note', ''))
    direct = answer_test(case['test'], case['student'], case['teacher'], case['options'])
    assert direct['valid'] and direct['correct'] == observed['correct']


@pytest.mark.parametrize('operator', ['implies', 'xor', 'xnor'])
def test_operator_truth_tables_and_held_round_trip(operator):
    for a, b in product((False, True), repeat=2):
        expected = {'implies': (not a) or b, 'xor': a != b, 'xnor': a == b}[operator]
        value = evaluate(f'{str(a).lower()} {operator} {str(b).lower()}')
        assert validate_logic(value)[1] == (sp.true if expected else sp.false)
        assert evaluate(str(value)) == value
    latex = {'implies': r'\rightarrow', 'xor': r'\oplus', 'xnor': r'\leftrightarrow'}[operator]
    assert latex in form_latex(parse(f'A {operator} B'))
    assert latex in sp.latex(evaluate(f'A {operator} B'))


@pytest.mark.parametrize('left,right,correct', [
    ('A or B implies C', '(A or B) implies C', True),
    ('A xor B implies C or D', 'A xor (B implies (C or D))', True),
    ('A implies B implies C', '(A implies B) implies C', True),
    ('A implies B implies C', 'A implies (B implies C)', False),
    ('A xnor B xnor C', 'A xor B xor C', True),
    ('A xnor B xnor C', '(A xnor B) and (B xnor C)', False),
    ('A implies B', 'B implies A', False),
])
def test_stack_precedence_associativity_and_negative_controls(left, right, correct):
    assert answer_test('AlgEquiv', left, right)['correct'] is correct


@pytest.mark.parametrize('source', ['x=0 implies y=0', 'x=0 xor y=0', 'x=0 xnor y=0'])
def test_new_operators_do_not_extend_equation_domain(source):
    with pytest.raises(Unsupported):
        validate_logic(evaluate(source))


@pytest.mark.parametrize('test', ['NumAbsolute', 'NumRelative'])
@pytest.mark.parametrize('option', ['', '   ', '(x', 'x)', '1+', '(1+2'])
def test_malformed_numeric_options_use_default_for_accept_and_reject(test, option):
    for student, correct in [('1.049', True), ('1.051', False)]:
        result = answer_test(test, student, '1', option)
        assert result['valid'] and result['correct'] is correct
        observed = evaluate_case({'id': 'numeric-default', 'test': test, 'student': student,
                                  'teacher': '1', 'options': option})
        assert observed['kind'] == 'result' and observed['correct'] is correct


@pytest.mark.parametrize('test', ['NumAbsolute', 'NumRelative'])
@pytest.mark.parametrize('option', ['x', '1/0', '%i', 'sqrt(-1)'])
def test_parseable_bad_tolerances_are_not_replaced(test, option):
    case = {'id': 'invalid-tolerance', 'test': test, 'student': '1', 'teacher': '1', 'options': option}
    assert evaluate_case(case)['kind'] == 'invalid_option'
    with pytest.raises((InvalidAnswer, Unsupported)):
        answer_test(test, '1', '1', option)


def test_unknown_functions_and_resource_limits_are_not_defaulted():
    for option in ['unknown(1)', '1' * 1201]:
        observed = evaluate_case({'id': 'unsupported-tolerance', 'test': 'NumAbsolute',
                                  'student': '1', 'teacher': '1', 'options': option})
        assert observed['kind'] == 'unsupported'
