"""Public custom checker contract, independent of native compatibility claims."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
import sympy as sp

from stack_sympy.assessment import answer_test
from stack_sympy.checkers import CheckerError, invoke, preflight, source_descriptor
from stack_sympy.cli import main, render
from stack_sympy.engine import grade, instantiate, run_question_tests, validate
from stack_sympy.importer import import_xml, UnsupportedQuestion

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "questions/python-checker.xml"
MODULE = ROOT / "questions/checkers.py"


def descriptor(body):
    return {"api_version": 1, "source": body}


def module(expression):
    return descriptor("def check(student, teacher):\n    return " + expression + "\nCHECKERS={'check':check}\n")


def question(source=None):
    q = import_xml(XML, python_checkers=MODULE)[0]
    if source is not None:
        q["python_checkers"] = source
        q["prts"][0]["nodes"][0]["options"] = "check"
        q["qtests"] = []
    return q


@pytest.mark.parametrize("source,expression", [
    ("x+sqrt(2)", "isinstance(student, sp.Expr) and student == teacher"),
    ("matrix([x,sqrt(2)],[1/2,%i])", "isinstance(student, Matrix) and student == teacher"),
    ("[1,[2,3]]", "isinstance(student, ListValue) and isinstance(student.args[1], ListValue)"),
    ("{1,1,2}", "isinstance(student, SetValue) and len(student.args)==3"),
    ("x=2", "isinstance(student, Equation) and student.args[0] == sp.Symbol('x')"),
    ("x=2 or x=2", "isinstance(student, Logical) and len(student.operands)==2"),
    ("true", "student is sp.true"),
])
def test_immutable_typed_arguments_preserve_held_structure(source, expression):
    body = "import sympy as sp\nfrom stack_sympy.checker_api import *\n" + module(expression)["source"]
    result = answer_test("PythonChecker", source, source, "check", python_checkers=descriptor(body))
    assert result["valid"] and result["correct"]


@pytest.mark.parametrize("result", ["1", "None", "sp.true", "{'valid':1,'correct':False}",
    "{'valid':False,'correct':True}", "{'valid':True,'correct':True,'score':1}",
    "{'valid':True,'correct':True,'note':'x'}", "{'correct':True}",
    "{'valid':True,'correct':True,'feedback':[]}",
    "{'valid':True,'correct':True,'assessment':{'columns':['correct']}}"])
def test_malformed_results_fail_as_author_errors(result):
    source = descriptor("import sympy as sp\n" + module(result)["source"])
    with pytest.raises(CheckerError):
        invoke(source, "check", sp.Integer(1), sp.Integer(1))


def test_validation_and_instantiation_do_not_execute_module_or_callback():
    q = question(descriptor("raise RuntimeError('must never execute')"))
    frozen = instantiate(q)
    assert validate(q, {"ans": "3"})["status"] == "valid"
    assert validate(q, {"ans": "3"}, variant=frozen)["status"] == "valid"
    with pytest.raises(UnsupportedQuestion, match="must never execute"):
        preflight(q, [frozen])


def test_false_model_branch_and_unreachable_guarded_expression():
    q = question(module("False"))
    first = q["prts"][0]["nodes"][0]
    first["false"]["score"] = 0.7
    second = deepcopy(first)
    second.update(name="1", teacher="1/0", options="explode")
    first["true"]["next"] = "1"
    q["prts"][0]["nodes"].append(second)
    body = module("False")["source"] + "def explode(a,b):\n    raise AssertionError('unreachable')\nCHECKERS['explode']=explode\n"
    q["python_checkers"] = descriptor(body)
    frozen = instantiate(q)
    preflight(q, [frozen])
    assert grade(q, {"ans": "3"}, variant=frozen)["score"] == 0.7
    second["options"] = "missing"
    with pytest.raises(UnsupportedQuestion, match="Unknown.*missing"):
        preflight(q, [frozen])


def test_registry_state_does_not_leak_between_invocations_or_cards():
    body = "count=0\ndef check(a,b):\n    global count\n    count+=1\n    return count==1\nCHECKERS={'check':check}\n"
    q = question(descriptor(body))
    other = question(module("False"))
    for seed in (1, 2, 1):
        assert grade(q, {"ans": "3"}, seed)["score"] == 1
        assert grade(other, {"ans": "3"}, seed)["score"] == 0
        assert grade(q, {"ans": "3"}, seed)["score"] == 1


def test_invalid_feedback_and_escaped_grading_feedback_and_quiet():
    text = "<img src=x onerror=alert(1)>"
    q = question(module(repr({"valid": False, "correct": False, "feedback": text})))
    result = grade(q, {"ans": "3"})
    assert result["status"] == "invalid"
    assert result["inputs"]["ans"]["feedback"] == text
    assert result["inputs"]["ans"]["valid"] is False
    q["python_checkers"] = module(repr({"valid": True, "correct": False, "feedback": text}))
    result = grade(q, {"ans": "3"})
    assert "&lt;img" in result["feedback"] and "<img" not in result["feedback"]
    q["prts"][0]["nodes"][0]["quiet"] = True
    assert not grade(q, {"ans": "3"})["feedback"]


@pytest.mark.parametrize("mutation", [lambda d: d.update(api_version=2),
    lambda d: d.update(extra=1), lambda d: d.update(source='x'*65537)])
def test_descriptor_version_and_bounds(mutation):
    d = module("True")
    mutation(d)
    with pytest.raises(CheckerError):
        invoke(d, "check", sp.Integer(1), sp.Integer(1))


@pytest.mark.parametrize("body", ["CHECKERS={'check':lambda a: True}",
    "async def check(a,b): return True\nCHECKERS={'check':check}",
    "def check(a,b): yield True\nCHECKERS={'check':check}",
    "from functools import partial\nasync def check(a,b): return True\nCHECKERS={'check':partial(check)}",
    "from functools import partial\ndef check(a,b): yield True\nCHECKERS={'check':partial(check)}",
    "CHECKERS={'check': 3}", "CHECKERS={'a.b': lambda a,b: True}",
    "def check(a,b): raise ValueError('author failure')\nCHECKERS={'check':check}"])
def test_bad_registry_signature_async_generator_and_callback_exception(body):
    q = question(descriptor(body))
    with pytest.raises(UnsupportedQuestion, match="PythonChecker"):
        grade(q, {"ans": "3"})


def test_matrix_assessment_contract():
    from stack_sympy.expressions import evaluate
    student = evaluate("matrix([x,sqrt(2)],[0,1])")
    for statuses in (["correct", "dependent"], ["incorrect", "correct"]):
        d = module(repr({"valid": True, "correct": True, "assessment": {"columns": statuses}}))
        assert invoke(d, "check", student, student)["assessment"]["columns"] == statuses
    for assessment in ({"columns": ["correct"]}, {"rows": ["correct", "bogus"]},
                       {"rows": ["correct", "correct"], "columns": ["correct", "correct"]}):
        with pytest.raises(CheckerError):
            invoke(module(repr({"valid": True, "correct": False, "assessment": assessment})), "check", student, student)


def test_source_attachment_and_cli_print_isolation(tmp_path, capsys):
    source = tmp_path / 'checker.py'
    source.write_text("print('AUTHOR OUTPUT')\n" + source_descriptor(MODULE)["source"].replace(
        '    correct =', "    print('CALLBACK OUTPUT')\n    correct ="), encoding='utf-8')
    output = render(str(XML), "A positive integer multiple (PythonChecker)", "custom", 2, 17, True,
                    python_checkers=str(source))
    assert 'AUTHOR OUTPUT' not in output.split('<script')[0]
    payload = json.loads(output.split('class="stack-sympy-data">')[1].split('</script>')[0])
    assert set(payload['question']['python_checkers']) == {'api_version','source'}
    assert str(tmp_path) not in output
    assert main(['test', '--file', str(XML), '--python-checkers', str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['passed']
    assert run_question_tests(question(), seeds=(1,17,47))['passed']


def test_checker_filename_is_read_at_build_and_updates_on_the_next_build(tmp_path):
    source = tmp_path / 'checker.py'
    source.write_text("def positive_multiple(a,b): return True\nCHECKERS={'positive_multiple':positive_multiple}\n")
    first = import_xml(XML, python_checkers=source)[0]
    source.write_text("def positive_multiple(a,b): return False\nCHECKERS={'positive_multiple':positive_multiple}\n")
    second = import_xml(XML, python_checkers=source)[0]
    # A built page carries its selected file contents; rendering again reads
    # the current file. Authors provide neither a manifest nor a checksum.
    assert grade(first, {'ans':'3'})['score'] == 1
    assert grade(second, {'ans':'3'})['score'] == 0
    assert set(first['python_checkers']) == {'api_version', 'source'}


@pytest.mark.parametrize('answer,correct', [
    ('matrix([1,0],[0,1])', True),
    ('matrix([2,1],[1,2])', True),
    ('matrix([1/2,1/4],[1/4,1])', True),
    ('matrix([-1,0],[0,-1])', False),  # positive determinant is insufficient
    ('matrix([1,1],[1,1])', False),  # positive semidefinite is insufficient
    ('matrix([2,1],[0,2])', False),  # nonsymmetric, even with positive quadratic form
    ('matrix([1,2],[2,1])', False),
    ('matrix([1,0,0],[0,-1,0],[0,0,-1])', False),  # middle principal minor
    ('matrix([2,1,0],[1,2,1],[0,1,2])', True),
    ('matrix([1,0,0],[0,1,0])', False),
])
def test_spd_example_checks_symmetry_and_all_leading_principal_minors(answer, correct):
    source = source_descriptor(ROOT / 'questions/spd-checker.py')
    result = answer_test('PythonChecker', answer, 'true', 'is_spd', python_checkers=source)
    assert result['valid'] and result['correct'] is correct
    opposite = answer_test('PythonChecker', answer, 'false', 'is_spd', python_checkers=source)
    assert opposite['valid'] and opposite['correct'] is not correct


@pytest.mark.parametrize('answer', [
    'matrix([x,0],[0,1])', 'matrix([sqrt(2),0],[0,1])',
    'matrix([%i,0],[0,1])',
])
def test_spd_example_explains_its_exact_rational_domain(answer):
    result = answer_test('PythonChecker', answer, 'true', 'is_spd',
                         python_checkers=source_descriptor(ROOT / 'questions/spd-checker.py'))
    assert not result['valid'] and not result['correct']
    assert 'integers or exact fractions' in result['feedback']


def test_spd_xml_and_filename_work_through_build_tests_and_grading():
    q = import_xml(ROOT / 'questions/symmetric-positive-definite.xml',
                   python_checkers=ROOT / 'questions/spd-checker.py')[0]
    preflight(q, [instantiate(q)])
    assert run_question_tests(q, seeds=(1,17,47))['passed']
    assert grade(q, {'ansm':'matrix([2,1],[1,2])'})['score'] == 1
    assert grade(q, {'ansm':'matrix([-1,0],[0,-1])'})['score'] == 0
    assert grade(q, {'ansm':'matrix([x,0],[0,1])'})['status'] == 'invalid'
    assert grade(q, {'ansm':'matrix([0.5,0],[0,1])'})['status'] == 'invalid'


def test_import_rejects_expressions_and_paths_as_checker_identifiers():
    for value in ('a.b', '../x.py', '__import__(x)', ''):
        with pytest.raises(UnsupportedQuestion, match='identifier'):
            import_xml(XML.read_text().replace('positive_multiple</testoptions>', value+'</testoptions>'))
    with pytest.raises(UnsupportedQuestion, match='direct input'):
        import_xml(XML.read_text().replace('<sans>ans</sans>', '<sans>ans+1</sans>'))
    with pytest.raises(UnsupportedQuestion, match='source descriptor'):
        instantiate(import_xml(XML)[0])


def test_callback_receives_the_validated_value_without_input_name_rebinding():
    q = question(module("{'valid':True,'correct':True,'feedback':str(student)}"))
    assert grade(q, {'ans': 'ans+1'})['feedback'] == 'ans + 1'


def test_model_preflight_uses_author_expression_conversion():
    q = question(module('True'))
    q['inputs'][0]['teacher'] = 'diff(x^2,x)'
    preflight(q, [instantiate(q)])


def test_custom_node_keeps_static_branch_feedback_validation():
    q = question(module('True'))
    q['prts'][0]['nodes'][0]['false']['feedback'] = '<script>bad()</script>'
    with pytest.raises(UnsupportedQuestion, match='unsupported HTML'):
        instantiate(q)


@pytest.mark.parametrize('body', [
    "raise SystemExit(0)",
    "def check(a,b): raise SystemExit(0)\nCHECKERS={'check':check}",
    "class C:\n    async def __call__(self,a,b): return True\nCHECKERS={'check':C()}",
    "class C:\n    def __call__(self,a,b): yield True\nCHECKERS={'check':C()}",
])
def test_exit_and_async_callable_objects_are_author_errors(body):
    q = question(descriptor(body))
    with pytest.raises(UnsupportedQuestion, match='PythonChecker'):
        preflight(q, [instantiate(q)])


def test_matrix_assessment_attachment_and_quiet_prt_scoring():
    q = import_xml(ROOT / 'questions/course-c-nullspace.xml')[0]
    node = q['prts'][0]['nodes'][0]
    node.update(test='PythonChecker', options='check')
    q['python_checkers'] = module("{'valid':True,'correct':True,'assessment':{'columns':['correct']*student.cols}}")
    result = grade(q, {'ans':'matrix([-2],[1],[0])'})
    assert result['inputs']['ans']['assessment'] == {'columns':['correct']}
    node['true']['score'] = 0.25
    node['quiet'] = True
    result = grade(q, {'ans':'matrix([-2],[1],[0])'})
    assert result['score'] == 0.25
    assert 'assessment' not in result['inputs']['ans']


def test_finite_values_and_qtest_order():
    with pytest.raises(CheckerError, match='finite'):
        invoke(module('True'), 'check', sp.oo, sp.Integer(1))
    q = question()
    assert run_question_tests(q, seeds=(47,17,1))['passed']
    q['qtests'].reverse()
    assert run_question_tests(q, seeds=(1,17,47))['passed']


def test_model_preflight_matches_qtest_lowest_terms_conversion():
    q = question(module("True"))
    q["inputs"][0]["teacher"] = "2/4"
    q["inputs"][0]["requirelowestterms"] = True
    preflight(q, [instantiate(q)])


def test_quiet_invalid_result_suppresses_diagnostic_in_python_result():
    q = question(module("{'valid':False,'correct':False,'feedback':'hidden diagnostic'}"))
    q["prts"][0]["nodes"][0]["quiet"] = True
    result = grade(q, {"ans":"3"})
    assert result["status"] == "invalid"
    assert result["feedback"] == result["inputs"]["ans"]["feedback"] == "Invalid answer"
    assert "hidden diagnostic" not in json.dumps(result)
