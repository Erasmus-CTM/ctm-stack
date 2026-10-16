"""Native form rules and explicitly scoped numerical/domain conventions."""
import json
from pathlib import Path

import pytest
import sympy as sp

from stack_sympy import answer_test, evaluate, parse
from stack_sympy.equivalence import constant_float_equivalent


@pytest.mark.parametrize("student,teacher,correct", [
    ("x/(-y)", "-(x/y)", False),
    ("1/2*1/x", "1/(2*x)", False),
    ("(1/2)*(a+b)", "(a+b)/2", False),
    ("1/3*i", "i/3", False),
    ("-1/4*x", "-x/4", False),
    ("1/x", "x^(-1)", False),
    ("(a*b)/c", "a*(b/c)", True),
    ("(-x)/y", "-(x/y)", True),
    ("x/(-y)", "x/(-y)", True),
    ("x/(y*z)", "x/(z*y)", True),
    ("x/(y*z)", "x/y/z", False),
    ("(1/2)*(a+b)", "(b+a)*(1/2)", True),
])
def test_held_reciprocals(student, teacher, correct):
    result = answer_test("EqualComAss", student, teacher)
    assert result["valid"] and result["cas_valid"]
    assert result["correct"] is correct


@pytest.mark.parametrize("source,correct", [
    ("x-1/-4", False), ("1/-3", True), ("-1/3", True),
    ("-1/-3", False), ("x+1/-4", True), ("x-1/4", True),
    ("-(1/-4)", False), ("-(-1/-4)", True),
    ("x/(x^2+x)", True), ("1/(1+%i)", False),
])
def test_lowest_terms_sign_context(source, correct):
    assert answer_test("LowestTerms", source, "unrelated_teacher")["correct"] is correct


@pytest.mark.parametrize("student,teacher,correct", [
    ("452", "4.52*10^2", False), ("100.4-80.0", "20.4", False),
    ("0.99999999", "99999998/99999999", True),
    ("99999999/10^8", "99999998/99999999", False),
    ("0.99999999", "1", False), ("0.5", "1/2", True),
    ("0.33", "1/3", False), ("0.333333333333333", "1/3", False),
    ("5.1e-2", "51/1000", True),
    ("0.1+0.2", "0.3", False),
])
def test_constant_binary64_compatibility(student, teacher, correct):
    assert answer_test("AlgEquiv", student, teacher)["correct"] is correct
    assert answer_test("AlgEquiv", teacher, student)["correct"] is correct


def test_float_compatibility_does_not_change_exact_evaluation_or_other_tests():
    assert evaluate("100.4-80.0") == sp.Rational("20.4")
    assert answer_test("NumAbsolute", "100.4-80.0", "20.4", "0")["correct"]
    for left, right in [("x+0.1", "x+1/10"), ("cos(0.0)", "1"),
                        ("(-1)^(1/2)+0.0", "%i"), ("2^100+1", "2^100")]:
        assert constant_float_equivalent(parse(left), parse(right)) is None
    assert not answer_test("AlgEquiv", "x+0.00000000000000000001", "x")["correct"]


def test_documented_reciprocal_sqrt_and_branch_controls():
    assert answer_test("AlgEquiv", "1/sqrt(x)", "sqrt(1/x)")["correct"]
    assert answer_test("AlgEquiv", "sqrt(1/y)", "1/sqrt(y)")["correct"]
    assert not answer_test("AlgEquiv", "1/sqrt(-1)", "sqrt(1/(-1))")["correct"]
    assert not answer_test("AlgEquiv", "log(sqrt(1/x))", "log(1/sqrt(x))")["correct"]
    assert not answer_test("AlgEquiv", "sqrt(1/(2*x))", "1/sqrt(2*x)")["correct"]
    assert not answer_test("AlgEquiv", "sqrt((x-3)*(x-5))", "sqrt(x-3)*sqrt(x-5)")["correct"]
    assert not answer_test("AlgEquiv", "(x^a)^b", "x^(a*b)")["correct"]
    assert not answer_test("AlgEquiv", "abs(x)", "sqrt(x^2)")["correct"]


def test_principal_log_power_symmetry_without_log_product_expansion():
    assert answer_test("AlgEquiv", "x^log(y)", "y^log(x)")["correct"]
    assert not answer_test("AlgEquiv", "x^log(y)", "y^(2*log(x))")["correct"]
    assert not answer_test("AlgEquiv", "log(a^2*b)", "2*log(a)+log(b)")["correct"]


def test_remaining_exceptions_have_case_specific_author_discussion():
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root / "tests/native_compliance/policy.json").read_text())
    for entry in policy["cases"].values():
        discussion = entry["discussion"]
        assert discussion["category"] in {"domain_review", "proof_limitation"}
        assert discussion["explanation"] and discussion["question"] and discussion["sources"]
        assert discussion["evidence"] in {"documented_context", "observed_behavior"}
