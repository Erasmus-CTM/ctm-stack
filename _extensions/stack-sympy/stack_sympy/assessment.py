"""A conservative scalar and finite-collection subset of STACK answer tests.

No numerical sampling is used to declare symbolic equivalence. Unsupported
answer tests raise Unsupported, whereas malformed student answers return an
invalid result. Feedback strings are brief and are not localized STACK text.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import re
from typing import Any, Mapping

import sympy as sp

from .expressions import (InvalidAnswer, Node, Unsupported, canonical_form, evaluate,
                          parse, is_logical, is_collection, validate_collection,
                          AUTHOR_COLLECTION_FUNCTIONS)

from .checkers import invoke as invoke_checker

MAX_DECIMAL_PLACES = 50


def _result(valid: bool, correct: bool, note: str = "", feedback: str = "") -> dict:
    return {"valid": valid, "correct": correct, "note": note, "feedback": feedback}


def _number(value, label: str):
    if not isinstance(value, sp.Basic) or value.is_number is not True or value.is_real is not True:
        raise InvalidAnswer(f"{label} must be a real number")
    if value.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
        raise InvalidAnswer(f"{label} must be finite")
    return value


def _decimal(value) -> Decimal:
    with localcontext() as ctx:
        # Guard digits beyond the supported precision keep final-place
        # rounding independent of SymPy's display precision.
        ctx.prec = 200
        out = Decimal(str(sp.N(value, 180)))
    if not out.is_finite():
        raise InvalidAnswer("Non-finite numerical answer")
    return out


def _option(options: str, env, assumptions):
    try:
        return evaluate(options, env, assumptions=assumptions)
    except InvalidAnswer as exc:
        raise Unsupported(f"Invalid answer-test options: {exc}") from exc


def numeric_option_source(options: str) -> str:
    """Mirror the numeric controller's default for absent/malformed options.

    controller.class.php replaces a syntactically invalid NumAbsolute or
    NumRelative option with 0.05. Evaluation errors and syntax outside our
    bounded grammar must still be reported, rather than silently defaulted.
    """
    if not options.strip():
        return "0.05"
    try:
        parse(options)
    except InvalidAnswer as exc:
        if str(exc) in {"Expected ')'", "Expected ']'", "Expected an expression", "Unexpected trailing text"}:
            return "0.05"
        raise
    return options


def _equiv(student, teacher):
    from .logic import logical_equivalent
    from .equivalence import elementary_equivalent
    if is_logical(student) or is_logical(teacher):
        # A symbol can be a proposition in a Boolean comparison.
        if not all(is_logical(x) or isinstance(x, sp.Symbol) for x in (student, teacher)):
            return False
        return logical_equivalent(student, teacher)
    if not isinstance(student, sp.Expr) or not isinstance(teacher, sp.Expr):
        raise InvalidAnswer("Only scalar or logical answers are supported")
    return elementary_equivalent(student, teacher)


def _algebraic(student, teacher, student_ast=None, teacher_ast=None, *, collection_leaf=False):
    """Recursive AlgEquiv retaining literal precision and CAS applicability."""
    if any(is_collection(x) for x in (student, teacher)):
        from .collections import collection_test
        def compare(a, b, index):
            sa = student_ast.children[index] if student_ast is not None and (student_ast.kind == "list" or student_ast.kind == "call" and student_ast.value == "matrix") else None
            ta = teacher_ast.children[index] if teacher_ast is not None and (teacher_ast.kind == "list" or teacher_ast.kind == "call" and teacher_ast.value == "matrix") else None
            return _algebraic(a, b, sa, ta, collection_leaf=True)
        return collection_test("AlgEquiv", student, teacher, compare)
    from .logic import _has_equation
    if (is_logical(student) != is_logical(teacher)
            or _has_equation(student) and not _has_equation(teacher)):
        return {**_result(True, False), "cas_valid": False}
    if collection_leaf:
        # Frozen exact rational members have no written child AST. They still
        # supply the exact side of a comparison with a literal decimal answer.
        if isinstance(student, sp.Rational) and (student_ast is None or student_ast.kind == "name"):
            student_ast = parse(str(student))
        if isinstance(teacher, sp.Rational) and (teacher_ast is None or teacher_ast.kind == "name"):
            teacher_ast = parse(str(teacher))
    if student_ast is not None and teacher_ast is not None:
        from .equivalence import constant_float_equivalent
        floating = constant_float_equivalent(student_ast, teacher_ast)
        if floating is not None:
            return _result(True, floating)
    return _result(True, _equiv(student, teacher))


def _helper_call(node):
    return (node.kind == "call" and node.value in AUTHOR_COLLECTION_FUNCTIONS
            or any(_helper_call(c) for c in node.children))


def _decimal_places(raw: str) -> tuple[Decimal, int]:
    # Only a literal decimal records unambiguous written precision.
    match = re.fullmatch(r"\s*([+-]?(?:\d+\.\d+|\.\d+))(?:[eE]([+-]?\d+))?\s*", raw)
    if match is None:
        raise InvalidAnswer("Enter a decimal literal with its trailing zeros")
    try:
        value = Decimal(match.group(0).strip())
    except InvalidOperation as exc:
        raise InvalidAnswer("Invalid decimal literal") from exc
    if not value.is_finite():
        raise InvalidAnswer("Non-finite decimal")
    return value, -value.as_tuple().exponent


def _facform_polynomial(value, variable):
    """Keep FacForm within univariate polynomials over the rationals."""
    if not isinstance(value, sp.Basic) or value.free_symbols - {variable}:
        raise Unsupported("FacForm supports univariate rational polynomials")
    def degree_bound(expr):
        if expr == variable:
            return 1
        if expr.is_Number:
            if expr.is_Rational and max(int(expr.p).bit_length(), int(expr.q).bit_length()) > 256:
                raise Unsupported("FacForm coefficient exceeds supported bound")
            return 0
        if expr.is_Add:
            return max(degree_bound(a) for a in expr.args)
        if expr.is_Mul:
            return sum(degree_bound(a) for a in expr.args)
        if expr.is_Pow and expr.exp.is_Integer and 0 <= int(expr.exp) <= 10000:
            return int(expr.exp) * degree_bound(expr.base)
        raise Unsupported("FacForm supports univariate rational polynomials")
    if value.count_ops() > 500 or degree_bound(value) > 100:
        raise Unsupported("FacForm polynomial exceeds supported bounds")
    try:
        poly = sp.Poly(value, variable, domain=sp.QQ)
        if len(poly.terms()) > 101:
            raise Unsupported("FacForm polynomial exceeds supported bounds")
        if any(max(int(c.p).bit_length(), int(c.q).bit_length()) > 256 for c in poly.all_coeffs()):
            raise Unsupported("FacForm coefficient exceeds supported bound")
        return poly
    except (sp.PolynomialError, sp.CoercionFailed, TypeError, ValueError) as exc:
        raise Unsupported("FacForm supports univariate rational polynomials") from exc


def _facform_irreducible(value, variable):
    poly = _facform_polynomial(value, variable)
    if poly.degree() <= 0:
        return True
    coefficients = poly.all_coeffs()
    # STACK's irred_Q rejects a common integer content even in a linear
    # expression (2*x-2), while accepting a primitive 2*x-1.
    if (len(coefficients) > 1 and all(c.is_Integer for c in coefficients)
            and abs(int(sp.igcd(*[int(c) for c in coefficients]))) > 1):
        return False
    if poly.degree() == 1:
        return True
    factors = sp.factor_list(poly.as_expr(), variable)[1]
    return len(factors) == 1 and factors[0][1] == 1


def _facform_factored(node, env, assumptions, variable):
    """Test each written factor, without expanding the student's syntax."""
    if node.kind == "unary":
        return _facform_factored(node.children[0], env, assumptions, variable)
    if node.kind == "name" and node.value in env:
        value = env[node.value]
        _facform_polynomial(value, variable)
        # A frozen author variable retains the SymPy factor/multiplication
        # structure obtained when evaluating factor(...).
        if value.is_Mul:
            return all(_facform_value_factored(f, variable) for f in value.args)
        return _facform_value_factored(value, variable)
    if node.kind == "binary" and node.value == "*":
        return all(_facform_factored(c, env, assumptions, variable) for c in node.children)
    if node.kind == "binary" and node.value in {"^", "**"}:
        exponent = evaluate(node.children[1], env, assumptions=assumptions)
        if exponent.is_Integer is not True or not 0 <= int(exponent) <= 100:
            raise Unsupported("FacForm supports nonnegative integer powers")
        return _facform_factored(node.children[0], env, assumptions, variable)
    if node.kind == "binary" and node.value == "/":
        denominator = evaluate(node.children[1], env, assumptions=assumptions)
        if not denominator.is_Rational or denominator == 0:
            raise Unsupported("FacForm supports only numeric denominators")
        return _facform_factored(node.children[0], env, assumptions, variable)
    value = evaluate(node, env, assumptions=assumptions, student=True)
    return _facform_irreducible(value, variable)


def _facform_value_factored(value, variable):
    if value.is_Mul:
        return all(_facform_value_factored(factor, variable) for factor in value.args)
    if value.is_Pow:
        if value.exp.is_Integer is not True or not 0 <= int(value.exp) <= 100:
            raise Unsupported("FacForm supports nonnegative integer powers")
        return _facform_value_factored(value.base, variable)
    return _facform_irreducible(value, variable)


def _facform_preflight(node, env, assumptions):
    """Reject out-of-domain syntax even inside a cancelling or wrong term."""
    for child in node.children:
        _facform_preflight(child, env, assumptions)
    if node.kind != "binary":
        return
    if node.value == "/":
        denominator = evaluate(node.children[1], env, assumptions=assumptions, student=True)
        if not denominator.is_Rational or denominator == 0:
            raise Unsupported("FacForm supports only numeric denominators")
    if node.value in {"^", "**"}:
        exponent = evaluate(node.children[1], env, assumptions=assumptions, student=True)
        if exponent.is_Integer is not True or not 0 <= int(exponent) <= 100:
            raise Unsupported("FacForm supports nonnegative integer powers")


def _fraction_parts(node: Node):
    """Preserve the division operators STACK sees with simp:false."""
    while node.kind == "unary":
        node = node.children[0]
    return node.children if node.kind == "binary" and node.value == "/" else None


def _division_in_sum_or_product(node: Node) -> bool:
    """Mirror ATSingleFrac_helper: powers and function calls are opaque."""
    if _fraction_parts(node) is not None:
        return True
    if node.kind == "unary":
        return _division_in_sum_or_product(node.children[0])
    if node.kind == "binary" and node.value in {"+", "-", "*"}:
        return any(_division_in_sum_or_product(child) for child in node.children)
    return False


def _single_fraction(node: Node) -> bool:
    parts = _fraction_parts(node)
    return parts is not None and not any(_division_in_sum_or_product(part) for part in parts)


def _written_integer(node: Node, env, assumptions):
    """Only a literal, its sign, or a frozen integer author value is a numberp atom."""
    if node.kind == "unary":
        value = _written_integer(node.children[0], env, assumptions)
        return -value if value is not None and node.value == "-" else value
    if node.kind == "number" or node.kind == "name" and node.value in env:
        value = evaluate(node, env, assumptions=assumptions, student=True)
        if value.is_Integer is True:
            return int(value)
    return None


def _unrationalized_denominator(node: Node, env, assumptions) -> bool:
    """Inspect the unsimplified denominator before cancellations erase surds."""
    if node.kind == "call" and node.value == "sqrt":
        return True
    if node.kind == "name" and node.value in {"%i", "i", "I"}:
        return True
    if node.kind == "binary" and node.value in {"^", "**"}:
        exponent = node.children[1]
        written_fraction = _fraction_parts(exponent)
        if written_fraction is not None and all(_written_integer(part, env, assumptions) is not None
                                               for part in written_fraction):
            return True
    if node.kind == "name" and node.value in env:
        value = env[node.value]
        if isinstance(value, sp.Basic) and (value.has(sp.I) or any(
                power.exp.is_Rational and not power.exp.is_Integer for power in value.atoms(sp.Pow))):
            return True
    return any(_unrationalized_denominator(child, env, assumptions) for child in node.children)


def _lowest_terms(node: Node, env, assumptions, negative: bool = False) -> bool:
    """Check written numeric fractions, never cancel polynomial factors."""
    if node.kind == "unary":
        return _lowest_terms(node.children[0], env, assumptions, negative ^ (node.value == "-"))
    if node.kind == "binary" and node.value in {"+", "-"}:
        return (_lowest_terms(node.children[0], env, assumptions, negative)
                and _lowest_terms(node.children[1], env, assumptions, negative ^ (node.value == "-")))
    if node.kind == "binary" and node.value == "/":
        numerator = _written_integer(node.children[0], env, assumptions)
        denominator = _written_integer(node.children[1], env, assumptions)
        if numerator is not None and denominator is not None:
            if negative:
                numerator = -numerator
            if (numerator < 0 and denominator < 0) or sp.igcd(numerator, denominator) != 1:
                return False
            # list_expression_numbers stops at a written numerical fraction;
            # outer unary minus applies to its numerator, not its denominator.
            return True
        # STACK's rationalized predicate rejects imaginary units and
        # fractional powers (including sqrt) in denominators.
        denominator_value = evaluate(node.children[1], env, assumptions=assumptions, student=True)
        if (_unrationalized_denominator(node.children[1], env, assumptions)
                or denominator_value.has(sp.I) or any(
                    power.exp.is_Rational and not power.exp.is_Integer
                    for power in denominator_value.atoms(sp.Pow))):
            return False
    # STACK's list_expression_numbers propagates an outer minus through all
    # collected numeric entries, including entries inside a product/call.
    return all(_lowest_terms(child, env, assumptions, negative) for child in node.children)


def answer_test(name: str, student: Node | str, teacher: str, options: str = "", *,
                env: Mapping[str, Any] | None = None, raw: str | None = None,
                assumptions: Mapping[str, bool] | None = None,
                python_checkers: dict | None = None) -> dict:
    """Evaluate one supported STACK test; return valid/correct/note/feedback.

    Supported: AlgEquiv, EqualComAss, FacForm, SingleFrac, LowestTerms,
    NumAbsolute, NumRelative, NumDecPlaces
    (one to fifty decimal places).
    Nested scalar collections support AlgEquiv, Sets, SameType and EqualComAss.
    Matrices support AlgEquiv, SameType and EqualComAss. Additional checks
    run through the single PythonChecker extension.
    Units, general relations and feedback-tree CAS
    features are outside this intentionally limited implementation.
    """
    if name != "PythonChecker" and name not in {"AlgEquiv", "Sets", "SameType", "EqualComAss", "FacForm", "SingleFrac", "LowestTerms",
                    "NumAbsolute", "NumRelative", "NumDecPlaces"}:
        raise Unsupported(f"Answer test {name!r} is unsupported")
    env = {} if env is None else env
    try:
        student_ast = parse(student) if isinstance(student, str) else student
        student_value = evaluate(student_ast, env, assumptions=assumptions, student=True)
    except (InvalidAnswer, TypeError, ZeroDivisionError) as exc:
        return _result(False, False, "invalid", str(exc))
    try:
        teacher_ast = parse(teacher)
        if name not in {"AlgEquiv", "SameType"} and _helper_call(teacher_ast):
            raise Unsupported("Direct finite helper calls require AlgEquiv or SameType; use a frozen evaluated author value")
        teacher_value = evaluate(teacher_ast, env, assumptions=assumptions)
    except (InvalidAnswer, TypeError, ZeroDivisionError) as exc:
        raise Unsupported(f"Invalid teacher expression: {exc}") from exc

    if name == "PythonChecker":
        return invoke_checker(python_checkers, options, student_value, teacher_value)

    for value in (student_value, teacher_value):
        validate_collection(value)
    from .expressions import MatrixValue
    if any(isinstance(value, MatrixValue) for value in (student_value, teacher_value)) and name not in {"AlgEquiv", "SameType", "EqualComAss"}:
        raise Unsupported("Matrices require AlgEquiv, SameType or EqualComAss")
    if name == "SameType":
        if any(is_logical(x) for x in (student_value, teacher_value)):
            raise Unsupported("SameType supports scalar expressions and collections")
        from .collections import same_type
        return {**_result(True, same_type(student_value, teacher_value)), "cas_valid": True}
    if name == "Sets":
        from .collections import collection_test
        return collection_test(name, student_value, teacher_value, None)
    if any(is_collection(x) for x in (student_value, teacher_value)):
        if name not in {"AlgEquiv", "EqualComAss"}:
            raise Unsupported("Collections require AlgEquiv, Sets, SameType or EqualComAss")
        result = _algebraic(student_value, teacher_value, student_ast, teacher_ast)
        if name == "AlgEquiv":
            return result
        if not result["correct"]:
            return {**_result(True, False), "cas_valid": False}
        return {**_result(True, canonical_form(student_ast, env, assumptions) == canonical_form(teacher_ast, env, assumptions)), "cas_valid": True}

    from .logic import validate_logic
    for value in (student_value, teacher_value):
        if is_logical(value):
            validate_logic(value)
    if name != "AlgEquiv" and any(is_logical(x) for x in (student_value, teacher_value)):
        raise Unsupported("Logical answers require AlgEquiv")

    if name == "AlgEquiv":
        return _algebraic(student_value, teacher_value, student_ast, teacher_ast)

    if name == "SingleFrac":
        # STACK accepts equivalent atomic answers without requiring a '/'.
        # Otherwise the expression itself must be a single written fraction.
        if student_ast.kind in {"number", "name"}:
            return _result(True, _equiv(student_value, teacher_value))
        form = _single_fraction(student_ast)
        return _result(True, form and _equiv(student_value, teacher_value))

    if name == "LowestTerms":
        # The teacher is deliberately ignored by STACK's ATLowestTerms.
        return _result(True, _lowest_terms(student_ast, env, assumptions))

    if name == "EqualComAss":
        # STACK's CAS test marks unequal values as inapplicable (first
        # return flag false). The adapter's `valid` remains input syntax
        # validity so an ordinary wrong answer can follow its PRT branch.
        if not _equiv(student_value, teacher_value):
            return {**_result(True, False), "cas_valid": False}
        try:
            correct = canonical_form(student_ast, env, assumptions) == canonical_form(teacher, env, assumptions)
        except InvalidAnswer as exc:
            return _result(False, False, "invalid", str(exc))
        return {**_result(True, correct), "cas_valid": True}

    if name == "FacForm":
        if not options.strip():
            raise Unsupported("FacForm requires a polynomial variable option")
        variable = _option(options, env, assumptions)
        if not isinstance(variable, sp.Symbol):
            raise Unsupported("FacForm requires a single polynomial variable")
        _facform_preflight(student_ast, env, assumptions)
        _facform_polynomial(student_value, variable)
        _facform_polynomial(teacher_value, variable)
        factored = _facform_factored(student_ast, env, assumptions, variable)
        if student_value.is_Integer:
            return _result(True, student_value == teacher_value)
        equivalent = _equiv(student_value, teacher_value)
        return _result(True, equivalent and factored)

    if name in {"NumAbsolute", "NumRelative"}:
        tolerance = _number(_option(numeric_option_source(options), env, assumptions), "Tolerance")
        try:
            student_number = _number(student_value, "Student answer")
            teacher_number = _number(teacher_value, "Teacher answer")
        except InvalidAnswer as exc:
            return _result(False, False, "invalid", str(exc))
        if all(x.is_Rational for x in (student_number, teacher_number, tolerance)):
            difference = abs(student_number - teacher_number)
            if name == "NumAbsolute":
                correct = difference < abs(tolerance) + sp.Rational(1, 10**9)
            else:
                correct = difference <= abs(teacher_number * tolerance * (1 + sp.Rational(1, 10**9)))
            return _result(True, bool(correct))
        sa = _decimal(student_number)
        ta = _decimal(teacher_number)
        tol = _decimal(tolerance)
        with localcontext() as ctx:
            ctx.prec = 200
            difference = abs(sa - ta)
            if name == "NumAbsolute":
                # STACK numericaltest.mac: strict inequality, 10E-10 guard.
                correct = difference < abs(tol) + Decimal("1e-9")
            else:
                # Inclusive equality supports the 0/0 zero-tolerance case.
                correct = difference <= abs(ta * tol * (1 + Decimal("1e-9")))
        return _result(True, correct)

    if not options.strip():
        raise Unsupported("NumDecPlaces requires a decimal-place count")
    required = _option(options, env, assumptions)
    if required.is_Integer is not True or not 1 <= int(required) <= MAX_DECIMAL_PLACES:
        raise Unsupported(f"NumDecPlaces requires 1 to {MAX_DECIMAL_PLACES} places")
    try:
        _number(student_value, "Student answer")
        teacher_decimal = _decimal(_number(teacher_value, "Teacher answer"))
        written, places = _decimal_places(raw if raw is not None else student if isinstance(student, str) else "")
    except InvalidAnswer as exc:
        return _result(False, False, "invalid", str(exc))
    if places != int(required):
        return _result(True, False, "wrong_decimal_places", "Incorrect number of decimal places")
    with localcontext() as ctx:
        ctx.prec = 230
        quantum = Decimal(1).scaleb(-int(required))
        expected = teacher_decimal.quantize(quantum, rounding=ROUND_HALF_EVEN)
        correct = written == expected
    return _result(True, correct, "" if correct else "wrong_value")
