"""A conservative scalar subset of STACK answer tests.

No numerical sampling is used to declare symbolic equivalence. Unsupported
answer tests raise Unsupported, whereas malformed student answers return an
invalid result. Feedback strings are brief and are not localized STACK text.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import re
from typing import Any, Mapping

import sympy as sp

from .expressions import InvalidAnswer, Unsupported, canonical_form, evaluate, parse

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


def _equiv(student, teacher):
    if not isinstance(student, sp.Basic) or not isinstance(teacher, sp.Basic):
        raise InvalidAnswer("Only scalar answers are supported")
    if student == teacher:
        return True
    difference = student - teacher
    try:
        for transform in (sp.cancel, sp.trigsimp, sp.simplify):
            if transform(difference) == 0:
                return True
        return False
    except (TypeError, ValueError, ZeroDivisionError, NotImplementedError):
        return False


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


def answer_test(name: str, student: str, teacher: str, options: str = "", *,
                env: Mapping[str, Any] | None = None, raw: str | None = None,
                assumptions: Mapping[str, bool] | None = None) -> dict:
    """Evaluate one supported STACK test; return valid/correct/note/feedback.

    Supported: AlgEquiv, EqualComAss, NumAbsolute, NumRelative, NumDecPlaces
    (one to fifty decimal places).
    Student lists and sets, units, equations, matrices, and feedback-tree CAS
    features are outside this intentionally limited implementation.
    """
    if name not in {"AlgEquiv", "EqualComAss", "NumAbsolute", "NumRelative", "NumDecPlaces"}:
        raise Unsupported(f"Answer test {name!r} is unsupported")
    env = {} if env is None else env
    try:
        student_ast = parse(student)
        student_value = evaluate(student_ast, env, assumptions=assumptions, student=True)
        if not isinstance(student_value, sp.Basic):
            raise InvalidAnswer("Only scalar student answers are supported")
    except (InvalidAnswer, TypeError, ZeroDivisionError) as exc:
        return _result(False, False, "invalid", str(exc))
    try:
        teacher_value = evaluate(teacher, env, assumptions=assumptions)
    except (InvalidAnswer, TypeError, ZeroDivisionError) as exc:
        raise Unsupported(f"Invalid teacher expression: {exc}") from exc

    if name == "AlgEquiv":
        return _result(True, _equiv(student_value, teacher_value))

    if name == "EqualComAss":
        try:
            correct = canonical_form(student_ast, env, assumptions) == canonical_form(teacher, env, assumptions)
        except InvalidAnswer as exc:
            return _result(False, False, "invalid", str(exc))
        return _result(True, correct)

    if name in {"NumAbsolute", "NumRelative"}:
        tolerance = _number(_option(options or "0.05", env, assumptions), "Tolerance")
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
        written, places = _decimal_places(raw if raw is not None else student)
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
