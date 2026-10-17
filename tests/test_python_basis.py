"""The Python extension has its own evidence, outside native parity scope."""
import hashlib
import itertools
import json
from pathlib import Path

import pytest
import sympy as sp

from stack_sympy.assessment import answer_test
from stack_sympy.checkers import preflight, source_descriptor
from stack_sympy.engine import grade, instantiate, run_question_tests, validate
from stack_sympy.expressions import Unsupported
from stack_sympy.expressions import evaluate, InvalidAnswer
from stack_sympy.importer import import_xml, UnsupportedQuestion

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "matrix([-2,-3],[1,0],[0,1])"
DEFINING = "matrix([1,2,3],[2,4,6])"
SOURCE = ROOT / "questions/course-c-nullspace.xml"
MODULE = ROOT / "questions/matrix-checkers.py"


def config(name, **options):
    value = {"checker": name}
    if options:
        value["options"] = options
    return json.dumps(value)


def basis_test(student, teacher, space="nullspace"):
    return answer_test("PythonChecker", student, teacher, config("basis", space=space),
                       python_checkers=source_descriptor(MODULE))


def property_test(student, teacher, name):
    return answer_test("PythonChecker", student, teacher, config("matrix_property", property=name),
                       python_checkers=source_descriptor(MODULE))


def matrix_questions(source):
    return import_xml(source, python_checkers=MODULE)


@pytest.mark.parametrize("candidate,correct,statuses", [
    (REFERENCE, True, ["correct", "correct"]),
    ("matrix([-3,-2],[0,1],[1,0])", True, ["correct", "correct"]),
    ("matrix([-5,-1],[1,-1],[1,1])", True, ["correct", "correct"]),
    ("matrix([-2],[1],[0])", False, ["correct"]),
    ("matrix([-2,-4],[1,2],[0,0])", False, ["dependent", "dependent"]),
    ("matrix([-2,-3,-5],[1,0,1],[0,1,1])", False, ["dependent"] * 3),
    ("matrix([-2,1],[1,0],[0,0])", False, ["correct", "incorrect"]),
    ("matrix([0,0],[0,0],[0,0])", False, ["incorrect", "incorrect"]),
    ("matrix([1,0],[0,1])", False, ["incorrect", "incorrect"]),
])
def test_basis_predicate_and_vector_diagnostics(candidate, correct, statuses):
    result = basis_test(candidate, DEFINING)
    assert result["valid"]
    assert result["correct"] is correct
    assert result["assessment"]["columns"] == statuses
    assert result["implementation"] == "python-checker-v1"
    assert "score" not in result


def test_statuses_and_correctness_are_permutation_invariant():
    columns = [(-2, 1, 0), (-4, 2, 0), (1, 0, 0)]
    for permutation in itertools.permutations(range(3)):
        source = "matrix(" + ",".join(
            "[" + ",".join(str(columns[i][r]) for i in permutation) + "]" for r in range(3)) + ")"
        result = basis_test(source, DEFINING)
        assert not result["correct"]
        assert result["assessment"]["columns"] == [
            "incorrect" if i == 2 else "dependent" for i in permutation]


@pytest.mark.parametrize("candidate", [
    "matrix([x],[0],[0])", "matrix([%i],[0],[0])", "matrix([sqrt(2)],[0],[0])",
    "matrix([2^100*2^100*2^100],[0],[0])", "[1,2,3]",
])
def test_basis_rejects_values_outside_the_exact_bounded_domain(candidate):
    result = basis_test(candidate, DEFINING)
    assert not result["valid"]


@pytest.mark.parametrize("reference,options", [
    ("matrix([1,0],[0,1])", "nullspace"),
    ("matrix([x],[0],[0])", "nullspace"),
    ("[1,2,3]", "nullspace"),
    (DEFINING, "diagonal"), (DEFINING, "__import__(os)"),
])
def test_author_errors_are_explicit(reference, options):
    with pytest.raises(Unsupported):
        basis_test(REFERENCE, reference, options)


def test_regular_passing_failing_and_quiet_prt_branches():
    question = matrix_questions(SOURCE)[0]
    prt = question["prts"][0]
    node = prt["nodes"][0]
    node["true"]["score"] = 0.8
    node["false"]["score"] = 0.2
    correct = grade(question, {"ans": "matrix([-5,-1],[1,-1],[1,1])"})
    incomplete = grade(question, {"ans": "matrix([-2],[1],[0])"})
    assert correct["score"] == 0.8
    assert incomplete["score"] == 0.2  # not the helper's diagnostic 0.5
    assert incomplete["prts"]["result"]["path"][0]["branch"] == "false"
    assert incomplete["inputs"]["ans"]["assessment"] == {"columns": ["correct"]}
    node["quiet"] = True
    quiet = grade(question, {"ans": "matrix([-2],[1],[0])"})
    assert quiet["score"] == 0.2
    assert not quiet["feedback"]
    assert "assessment" not in quiet["inputs"]["ans"]


def test_validation_checks_syntax_and_checker_reports_domain_during_grading():
    question = matrix_questions(SOURCE)[0]
    result = validate(question, {"ans": "matrix([1],[0],[0])"})
    assert result["status"] == "valid"  # a wrong vector still parses
    assert "assessment" not in result["inputs"]["ans"]
    assert "score" not in result
    assert validate(question, {"ans": "matrix([x],[0],[0])"})["status"] == "valid"
    assert grade(question, {"ans": "matrix([x],[0],[0])"})["status"] == "invalid"
    assert validate(question, {"ans": "matrix([0.0],[0],[0])"})["status"] == "invalid"


def test_common_model_preflight_allows_a_valid_false_branch():
    question = matrix_questions(SOURCE)[0]
    question["inputs"][0]["teacher"] = "matrix([1],[0],[0])"
    question["inputs"][0]["matrix"]["cols"] = {"auto": False, "initial": 1, "min": 1, "max": 1}
    question["qtests"] = []
    preflight(question, [instantiate(question)])
    assert grade(question, {"ans": "matrix([1],[0],[0])"})["score"] == 0


def test_empty_target_is_rejected_by_checker_preflight():
    source = SOURCE.read_text().replace("<tans>A</tans>", "<tans>matrix([1,0],[0,1])</tans>")
    q = matrix_questions(source)[0]
    with pytest.raises(UnsupportedQuestion, match="empty basis"):
        preflight(q, [instantiate(q)])


@pytest.mark.parametrize("candidate,correct,statuses", [
    (REFERENCE, True, ["correct", "correct"]),
    ("matrix([-5,-1],[1,-1],[1,1])", True, ["correct", "correct"]),
    ("matrix([-2],[1],[0])", False, ["correct"]),
    ("matrix([-2,-4],[1,2],[0,0])", False, ["dependent", "dependent"]),
    ("matrix([-2,1],[1,0],[0,0])", False, ["correct", "incorrect"]),
    ("matrix([0,0],[0,0],[0,0])", False, ["incorrect", "incorrect"]),
    ("matrix([1,0],[0,1])", False, ["incorrect", "incorrect"]),
])
def test_nullspace_is_defined_by_original_rectangular_matrix(candidate, correct, statuses):
    # No known basis is supplied to the checker. Row scaling and redundant
    # constraints describe the same null space.
    for defining in ("matrix([1,2,3],[2,4,6])", "matrix([-3,-6,-9])"):
        result = basis_test(candidate, defining, "nullspace")
        assert result["valid"] and result["correct"] is correct
        assert result["assessment"] == {"columns": statuses}


@pytest.mark.parametrize("defining,option,candidate,correct,statuses", [
    ("matrix([1,2,0],[0,1,1],[1,3,1])", "columnspace",
     "matrix([3,1],[1,1],[4,2])", True, ["correct", "correct"]),
    ("matrix([1,2,0],[0,1,1],[1,3,1])", "columnspace",
     "matrix([1],[0],[1])", False, ["correct"]),
    ("matrix([1,2,0],[0,1,1],[1,3,1])", "columnspace",
     "matrix([1,0],[0,0],[1,1])", False, ["correct", "incorrect"]),
    ("matrix([1,0,1,2],[0,1,1,1],[1,1,2,3])", "rowspace",
     "matrix([1,1,2,3],[1,-1,0,1])", True, ["correct", "correct"]),
    ("matrix([1,0,1,2],[0,1,1,1],[1,1,2,3])", "rowspace",
     "matrix([1,0,1,2],[2,0,2,4])", False, ["dependent", "dependent"]),
    ("matrix([1,0,1,2],[0,1,1,1],[1,1,2,3])", "rowspace",
     "matrix([1,0,0])", False, ["incorrect"]),
])
def test_column_and_row_space_membership(defining, option, candidate, correct, statuses):
    result = basis_test(candidate, defining, option)
    assert result["valid"] and result["correct"] is correct
    assert result["assessment"] == {"rows" if option == "rowspace" else "columns": statuses}


def test_basis_model_helpers_compute_answers_from_the_matrix_and_are_author_only():
    source = "matrix([1,2,3],[2,4,6])"
    null_model = evaluate("nullspace_basis(" + source + ")")
    matrix = sp.Matrix([list(row.args) for row in null_model.args])
    defining = sp.Matrix([[1, 2, 3], [2, 4, 6]])
    assert defining * matrix == sp.zeros(2, 2)
    assert matrix.rank() == 2
    for space in ("nullspace", "columnspace", "rowspace"):
        model = evaluate(space + "_basis(" + source + ")")
        assert basis_test(str(model), source, space)["correct"]
        with pytest.raises(InvalidAnswer, match="not allowed in student input"):
            evaluate(space + "_basis(" + source + ")", student=True)


@pytest.mark.parametrize("source", [
    "nullspace_basis(matrix([1,0],[0,1]))",  # zero-dimensional target
    "columnspace_basis(matrix([0,0]))",
    "rowspace_basis(matrix([0,0]))",
    "nullspace_basis(matrix([1.0,2]))",
    "nullspace_basis(matrix([x,2]))",
    "nullspace_basis(matrix([((2^100)^100)^100,2]))",
    "nullspace_basis(matrix([1,2]),1)",
])
def test_basis_model_helpers_reject_unrepresentable_or_invalid_targets(source):
    with pytest.raises((InvalidAnswer, Unsupported)):
        evaluate(source)


def test_defining_matrix_changes_the_target_and_generated_model():
    question = matrix_questions(SOURCE)[0]
    question["variables"] = "A:matrix([1,0,0],[0,1,0]);"
    question["qtests"] = []
    assert grade(question, {"ans": "matrix([0],[0],[3])"})["score"] == 1
    assert grade(question, {"ans": REFERENCE})["score"] == 0
    assert "nullspace_basis(A)" == question["inputs"][0]["teacher"]


def test_python_checker_requires_direct_input_and_rejects_arbitrary_names():
    source = SOURCE.read_text()
    for replacement in ("ans+1", "T"):
        with pytest.raises(UnsupportedQuestion, match="direct input"):
            import_xml(source.replace("<sans>ans</sans>", "<sans>" + replacement + "</sans>"))
    with pytest.raises(UnsupportedQuestion, match="unsupported answer test"):
        import_xml(source.replace("PythonChecker", "ImportPythonModule"))


def test_source_provenance_and_independent_nullspace_mathematics():
    manifest = json.loads((ROOT / "questions/course-examples-provenance.json").read_text())
    for record in manifest["questions"]:
        assert hashlib.sha256((ROOT / "questions" / record["file"]).read_bytes()).hexdigest() == record["sha256"]
        question = matrix_questions(ROOT / "questions" / record["file"])[0]
        assert run_question_tests(question, seeds=(1, 17, 47))["passed"]
    assert hashlib.sha256((ROOT / "questions" / manifest["excerpts"]).read_bytes()).hexdigest() == manifest["excerpts_sha256"]
    B = sp.Matrix([[1, 0, 1], [0, 1, 1], [1, 1, 2]])
    C = sp.Matrix([[1, 2, 3], [2, 4, 6]])
    TB = sp.Matrix([-1, -1, 1])
    TC = sp.Matrix([[-2, -3], [1, 0], [0, 1]])
    assert B.rank() == 2 and B.rref()[1] == (0, 1)
    for matrix, reference in ((B, TB), (C, TC)):
        assert matrix * reference == sp.zeros(matrix.rows, reference.cols)
        assert reference.rank() == reference.cols == matrix.cols - matrix.rank()
    vendor = ROOT / "_extensions/stack-sympy/vendor"
    record = json.loads((vendor / "basis-helper-provenance.json").read_text())
    module = (ROOT / "_extensions/stack-sympy/stack_sympy/basis_helper.py").read_bytes()
    assert hashlib.sha256(module).hexdigest() == record["module_sha256"]
    function = module[module.index(b"def assess_basis"):]
    assert hashlib.sha256(function).hexdigest() == record["function_sha256"]


def test_large_matrix_entries_fail_the_supplied_checker_domain():
    result = basis_test("matrix([((2^100)^100)^100],[0],[0])", DEFINING)
    assert not result["valid"]
    assert "256-bit" in result["feedback"]


@pytest.mark.parametrize("candidate,teacher,property_name,correct", [
    ("matrix([2,1],[1,1])", "1", "determinant", True),
    ("matrix([0,-1],[1,0])", "1", "determinant", True),
    ("matrix([2,0],[0,2])", "1", "determinant", False),
    ("matrix([1/2,1],[0,2])", "true", "integer_entries", False),
    ("matrix([1+1,1],[1,1])", "true", "integer_entries", True),
    ("matrix([1,0],[0,1])", "false", "identity", False),
    ("matrix([1,1],[0,1])", "false", "identity", True),
])
def test_exact_matrix_properties(candidate, teacher, property_name, correct):
    result = property_test(candidate, teacher, property_name)
    assert result["valid"] and result["correct"] is correct
    assert "assessment" not in result  # no inferred cell grading


@pytest.mark.parametrize("teacher,option", [
    ("true", "determinant"),
    ("1", "integer_entries"), ("0", "identity"), ("1", "exec"),
])
def test_matrix_property_author_errors(teacher, option):
    with pytest.raises(Unsupported):
        property_test("matrix([1,1],[0,1])", teacher, option)


def test_determinant_example_retains_the_original_three_condition_grading():
    question = matrix_questions(ROOT / "questions/determinant-one.xml")[0]
    assert run_question_tests(question, seeds=(1, 17, 47))["passed"]
    assert grade(question, {"ans": "matrix([2,1],[1,1])"})["score"] == 1
    for answer in ("matrix([1,0],[0,1])", "matrix([1/2,1],[0,2])", "matrix([2,0],[0,2])"):
        result = grade(question, {"ans": answer})
        assert result["score"] == pytest.approx(2 / 3)
        assert "assessment" not in result["inputs"]["ans"]
    manifest = json.loads((ROOT / "questions/determinant-example-provenance.json").read_text())
    for filename, expected in ((manifest["converted"], manifest["converted_sha256"]),
                               (manifest["original"], manifest["original_sha256"])):
        assert hashlib.sha256((ROOT / "questions" / filename).read_bytes()).hexdigest() == expected
