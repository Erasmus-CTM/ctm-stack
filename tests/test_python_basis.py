"""The Python extension has its own evidence, outside native parity scope."""
import hashlib
import itertools
import json
from pathlib import Path

import pytest
import sympy as sp

from stack_sympy.assessment import answer_test
from stack_sympy.engine import grade, instantiate, run_question_tests, validate
from stack_sympy.expressions import Unsupported
from stack_sympy.expressions import evaluate, InvalidAnswer
from stack_sympy.importer import import_xml, UnsupportedQuestion

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "matrix([-2,-3],[1,0],[0,1])"
SOURCE = ROOT / "questions/course-c-nullspace.xml"


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
    result = answer_test("IsBasis", candidate, REFERENCE)
    assert result["valid"]
    assert result["correct"] is correct
    assert result["assessment"]["columns"] == statuses
    assert result["implementation"] == "python-extension"
    assert "score" not in result


def test_statuses_and_correctness_are_permutation_invariant():
    columns = [(-2, 1, 0), (-4, 2, 0), (1, 0, 0)]
    for permutation in itertools.permutations(range(3)):
        source = "matrix(" + ",".join(
            "[" + ",".join(str(columns[i][r]) for i in permutation) + "]" for r in range(3)) + ")"
        result = answer_test("IsBasis", source, REFERENCE)
        assert not result["correct"]
        assert result["assessment"]["columns"] == [
            "incorrect" if i == 2 else "dependent" for i in permutation]


def test_row_orientation_and_reference_basis_independence():
    result = answer_test("IsBasis", "matrix([-5,1,1],[-1,-1,1])",
                         "matrix([-2,1,0],[-3,0,1])", "rows")
    assert result["correct"]
    assert result["assessment"] == {"rows": ["correct", "correct"]}
    assert answer_test("IsBasis", REFERENCE, "matrix([-5,-1],[1,-1],[1,1])")["correct"]


@pytest.mark.parametrize("candidate", [
    "matrix([x],[0],[0])", "matrix([%i],[0],[0])", "matrix([sqrt(2)],[0],[0])",
    "matrix([-2.0],[1],[0])", "matrix([2^100*2^100*2^100],[0],[0])", "[1,2,3]",
])
def test_basis_rejects_values_outside_the_exact_bounded_domain(candidate):
    result = answer_test("IsBasis", candidate, REFERENCE)
    assert not result["valid"]


@pytest.mark.parametrize("reference,options", [
    ("matrix([-2,-4],[1,2],[0,0])", "columns"),
    ("matrix([0],[0],[0])", "columns"),
    ("matrix([x],[0],[0])", "columns"),
    ("matrix([1.0],[0],[0])", "columns"),
    (REFERENCE, "diagonal"), (REFERENCE, "__import__(os)"),
])
def test_author_errors_are_explicit(reference, options):
    with pytest.raises(Unsupported):
        answer_test("IsBasis", REFERENCE, reference, options)


def test_regular_passing_failing_and_quiet_prt_branches():
    question = import_xml(SOURCE)[0]
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


def test_validation_checks_domain_without_basis_information():
    question = import_xml(SOURCE)[0]
    result = validate(question, {"ans": "matrix([1],[0],[0])"})
    assert result["status"] == "valid"  # a wrong vector still parses
    assert "assessment" not in result["inputs"]["ans"]
    assert "score" not in result
    assert validate(question, {"ans": "matrix([x],[0],[0])"})["status"] == "invalid"
    assert validate(question, {"ans": "matrix([0.0],[0],[0])"})["status"] == "invalid"


def test_unreachable_or_wrong_model_answer_rejected_before_display():
    question = import_xml(SOURCE)[0]
    question["inputs"][0]["teacher"] = "matrix([1],[0],[0])"
    question["inputs"][0]["matrix"]["cols"] = {"auto": False, "initial": 1, "min": 1, "max": 1}
    question["qtests"] = []
    with pytest.raises(UnsupportedQuestion, match="input teacher must itself satisfy"):
        instantiate(question)


def test_invalid_reference_rejected_at_build_time():
    source = SOURCE.read_text().replace("<tans>A</tans><testoptions>nullspace</testoptions>",
                                      "<tans>matrix([-2,-4],[1,2],[0,0])</tans><testoptions>columns</testoptions>")
    with pytest.raises(UnsupportedQuestion, match="independent"):
        instantiate(import_xml(source)[0])


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
        result = answer_test("IsBasis", candidate, defining, "nullspace")
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
    result = answer_test("IsBasis", candidate, defining, option)
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
        assert answer_test("IsBasis", str(model), source, space)["correct"]
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
    question = import_xml(SOURCE)[0]
    question["variables"] = "A:matrix([1,0,0],[0,1,0]);"
    question["qtests"] = []
    assert grade(question, {"ans": "matrix([0],[0],[3])"})["score"] == 1
    assert grade(question, {"ans": REFERENCE})["score"] == 0
    assert "nullspace_basis(A)" == question["inputs"][0]["teacher"]


def test_python_test_requires_direct_matrix_input_and_rejects_arbitrary_names():
    source = SOURCE.read_text()
    for replacement in ("ans+1", "T"):
        with pytest.raises(UnsupportedQuestion, match="direct matrix input"):
            import_xml(source.replace("<sans>ans</sans>", "<sans>" + replacement + "</sans>"))
    with pytest.raises(UnsupportedQuestion, match="unsupported answer test"):
        import_xml(source.replace("IsBasis", "ImportPythonModule"))


def test_source_provenance_and_independent_nullspace_mathematics():
    manifest = json.loads((ROOT / "questions/course-examples-provenance.json").read_text())
    for record in manifest["questions"]:
        assert hashlib.sha256((ROOT / "questions" / record["file"]).read_bytes()).hexdigest() == record["sha256"]
        question = import_xml(ROOT / "questions" / record["file"])[0]
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


def test_nested_power_is_rejected_before_generic_evaluation(monkeypatch):
    import stack_sympy.assessment as assessment
    def forbidden(*args, **kwargs):
        raise AssertionError("generic evaluation must not be reached")
    monkeypatch.setattr(assessment, "evaluate", forbidden)
    result = assessment.answer_test("IsBasis", "matrix([((2^100)^100)^100],[0],[0])", REFERENCE)
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
    result = answer_test("MatrixProperty", candidate, teacher, property_name)
    assert result["valid"] and result["correct"] is correct
    assert "assessment" not in result  # no inferred cell grading


@pytest.mark.parametrize("teacher,option", [
    ("true", "determinant"), ("1.0", "determinant"),
    ("1", "integer_entries"), ("0", "identity"), ("1", "exec"),
])
def test_matrix_property_author_errors(teacher, option):
    with pytest.raises(Unsupported):
        answer_test("MatrixProperty", "matrix([1,1],[0,1])", teacher, option)


def test_determinant_example_retains_the_original_three_condition_grading():
    question = import_xml(ROOT / "questions/determinant-one.xml")[0]
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
