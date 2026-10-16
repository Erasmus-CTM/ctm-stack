"""Function semantics needed by the pinned corpus, including native edge cases."""
import pytest
import sympy as sp
from stack_sympy import InvalidAnswer, Unsupported, answer_test, canonical_form, evaluate, parse
from stack_sympy.expressions import form_latex
from stack_sympy.engine import grade, instantiate, run_question_tests
from stack_sympy.importer import UnsupportedQuestion, import_xml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('source,expected', [
    ('gcd(-12,18)', '6'), ('gcd(0,0)', '0'), ('gcd(1/2,1/3)', '1/6'),
    ('gcd(2*x+2,4*x+4)', '2*x+2'), ('gcd(x^2-1,x^2-2*x+1)', 'x-1'),
    ('mod(-7,3)', '2'), ('mod(7,-3)', '-2'), ('mod(-7,-3)', '-1'),
    ('mod(7,0)', '7'), ('mod(x,0)', 'x'), ('mod(5*%pi/2,2*%pi)', '%pi/2'),
    ('mod(7/2,3/2)', '1/2'), ('ln(%e)', '1'), ('ln(x)', 'log(x)'),
    ('ln(-1)', '%i*%pi'), ('sin(Pi/2)+cos(PI)', '0'),
])
def test_scalar_function_semantics(source, expected):
    assert sp.simplify(evaluate(source, student=True)-evaluate(expected)) == 0
    assert answer_test('AlgEquiv', source, expected)['correct']


def test_log_alias_retains_form_and_branch_semantics():
    assert canonical_form('ln(x)') == canonical_form('log(x)')
    assert answer_test('EqualComAss', 'ln(x)', 'log(x)')['correct']
    assert not answer_test('EqualComAss', 'ln(%e)', '1')['correct']
    assert not answer_test('AlgEquiv', 'ln(x^2)', '2*ln(x)')['correct']
    assert r'\ln' in form_latex(parse('ln(x)'))
    with pytest.raises(Unsupported, match='branch-aware proof'):
        answer_test('AlgEquiv', 'ln(x+%i)', 'log(x+%i)')


@pytest.mark.parametrize('source', ['gcd(sin(x),x)', 'gcd(1/x,x)', 'gcd(sqrt(2),2)',
                                   'gcd((x+1)^100,x)', 'gcd(x)', 'mod(1)', 'mod(%i,2)'])
def test_new_functions_keep_their_domain_and_resource_bounds(source):
    with pytest.raises((Unsupported, InvalidAnswer)):
        evaluate(source, student=True)


def test_numerator_denominator_helpers_preserve_content():
    assert evaluate('gcd(num((10*x+20)/(20*x)),denom((10*x+20)/(20*x)))') == 10
    # Maxima num/denom leave a sum as a numerator over 1, without ratsimp.
    assert evaluate('num(x/2+y/3)') == evaluate('x/2+y/3')
    assert evaluate('denom(x/2+y/3)') == 1
    assert evaluate('num(-3/5)') == -3
    assert evaluate('denom(-3/5)') == 5
    assert evaluate('ev(2*ln(x)/4)') == evaluate('ln(x)/2')
    with pytest.raises(InvalidAnswer):
        evaluate('num(x)', student=True)


@pytest.mark.parametrize('filename', ['AlgMap-14-1.xml', 'Logs_1.xml'])
def test_newly_supported_corpus_questions_replay_all_deployed_seeds(filename):
    question = import_xml(ROOT/'questions/corpus'/filename)[0]
    report = run_question_tests(question, seeds=question['deployedseeds'])
    assert report['passed'], report


def test_complex_question_passes_function_evaluation_but_still_requires_list_answers():
    question = import_xml(ROOT/'questions/corpus/Complex_Convert_1.xml')[0]
    with pytest.raises(UnsupportedQuestion, match='only scalar teacher answers'):
        instantiate(question, question['deployedseeds'][0])


def test_upstream_algmap_8_10_prt_rejects_a_correct_integral_answer():
    question = import_xml(ROOT/'questions/corpus/AlgMap-8-10.xml')[0]
    variant = instantiate(question, 1856951054)
    assert [int(variant['env'][name]) for name in ('a','b','c','d')] == [8,9,2,3]
    result = grade(question, {'ans':'7*(t+y)'}, variant=variant)
    assert answer_test('AlgEquiv', '7*(t+y)', variant['env']['fta'])['correct']
    assert not answer_test('SingleFrac', '7*(t+y)', variant['env']['fta'])['correct']
    assert result['score'] == 0
    assert result['prts']['prt1']['note'] == '1-0-F | 1-1-F'
    nodes = question['prts'][0]['nodes']
    assert nodes[0]['test'] == 'SingleFrac' and nodes[0]['true']['score'] == 1
    assert all(node['true']['score'] == node['false']['score'] == 0 for node in nodes[1:])


def test_algmap_15_1_requires_sets_not_xml_sanitization():
    question = import_xml(ROOT/'questions/corpus/AlgMap-15-1.xml')[0]
    assert question['inputs'][0]['teacher'] == '{ta1,ta2}'
    with pytest.raises(UnsupportedQuestion, match=r'input\[ans\]/tans: Set expressions'):
        instantiate(question, question['deployedseeds'][0])


@pytest.mark.parametrize('source,character,codepoint,position', [
    ('x  ≤ 2', '≤', '2264', 3), ('x\u00a0+1', '\u00a0', '00A0', 1),
])
def test_character_diagnostic_names_the_actual_character_after_whitespace(source, character, codepoint, position):
    with pytest.raises(InvalidAnswer) as error:
        parse(source)
    assert str(error.value) == f"Unexpected character {character!r} (U+{codepoint}) at position {position}"


def test_authoring_label_requires_the_reviewed_failure_pattern():
    import copy
    import json
    from scripts.generate_corpus_page import upstream_authoring_issue
    entry = next(e for e in json.loads((ROOT/'questions/corpus/manifest.json').read_text())['questions']
                 if e['file'] == 'AlgMap-8-10.xml')
    row = next(r for r in json.loads((ROOT/'questions/corpus/baseline.json').read_text())['questions']
               if r['file'] == entry['file'])
    assert 'Upstream authoring bug in the PRT' in upstream_authoring_issue(entry, row)
    changed = copy.deepcopy(row)
    changed['mismatches'][0]['seed'] = 17
    assert upstream_authoring_issue(entry, changed) is None
    assert upstream_authoring_issue(entry, {**row, 'status':'qtests_pass'}) is None
