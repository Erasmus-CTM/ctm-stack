"""Portable case preflight and execution; importable in CPython and Pyodide.

Preflight identifies declared subset boundaries using raw ASTs.  Exceptions
from execution are observations, never an automatic excuse for a wrong mark.
"""

from __future__ import annotations

from stack_sympy import InvalidAnswer, Unsupported, answer_test, evaluate, parse
from stack_sympy.expressions import MAX_CHARS, _STUDENT_FUNCTIONS, is_logical
from stack_sympy.assessment import numeric_option_source
from stack_sympy.logic import validate_logic
import sympy as sp
import re

try:
    from .common import SUPPORTED_TESTS
except ImportError:  # Loaded as a standalone module into the Pyodide filesystem.
    from common import SUPPORTED_TESTS

_NUMERIC_TESTS = frozenset({"NumAbsolute", "NumRelative", "NumDecPlaces"})
_NONSCALAR_NAMES = frozenset({"true", "false", "all", "none", "and", "or", "not",
                              "xor", "xnor", "implies", "nounand", "inf", "infinity"})
_CONSTANT_NAMES = frozenset({"pi", "%pi", "e", "E", "%e", "i", "I", "%i"})


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _preflight_expression(source: str, role: str):
    """Return AST or a controlled classification of syntax outside the API."""
    if not isinstance(source, str):
        return None, ("unsupported", f"{role} must be an expression string")
    if not source.strip():
        return None, (f"invalid_{role}", "Empty expression")
    if len(source) > MAX_CHARS:
        return None, ("unsupported", f"{role} exceeds {MAX_CHARS} characters")
    try:
        node = parse(source)
    except Unsupported as exc:
        return None, ("unsupported", str(exc))
    except InvalidAnswer as exc:
        message = str(exc)
        # The parser recognizes a narrow scalar grammar. Lexical constructs
        # outside it are explicitly outside this adapter's contract.
        if any(term in message for term in (
            "Unexpected character", "Function ", "Missing *", "Too many tokens",
            "Number too long", "nested too deeply", "oversized expression",
        )):
            return None, ("unsupported", f"{role} syntax outside scalar grammar: {message}")
        return None, (f"invalid_{role}", message)
    for item in _walk(node):
        if item.kind in {"list", "index"}:
            return None, ("unsupported", f"{role} list or index expression outside scalar subset")
        if role == "student" and item.kind == "call" and item.value not in _STUDENT_FUNCTIONS:
            return None, ("unsupported", f"student function {item.value} outside scalar subset")
    return node, None


def classify_case(case: dict) -> dict:
    """Classify declared applicability before executing a supported answer test.

    This is deliberately syntactic. A supported case that raises at runtime
    stays an observable failure instead of being retroactively excluded.
    """
    name = case.get("test")
    if name not in SUPPORTED_TESTS:
        return {"kind": "unsupported", "reason": f"answer test {name!r} outside eight-family scalar subset"}
    # Upstream's optional eighth field is a display-table header, not an
    # answer-test argument. It remains in the inventory but does not affect
    # classification, including when its value is nonempty.
    parsed = {}
    for role in ("student", "teacher"):
        node, issue = _preflight_expression(case.get(role), role)
        if issue:
            return {"kind": issue[0], "reason": issue[1]}
        parsed[role] = node
        for item in _walk(node):
            if item.kind == "name" and item.value in _NONSCALAR_NAMES:
                return {"kind": "unsupported", "reason": f"{role} Boolean, infinity, or logic outside scalar subset"}
            if item.kind == "number" and "e" in item.value.lower():
                if abs(int(re.split("[eE]", item.value)[1])) > 100:
                    return {"kind": "unsupported", "reason": f"{role} scientific exponent exceeds supported bound"}
            if item.kind == "binary" and item.value in {"^", "**"}:
                exponent = item.children[1]
                if exponent.kind == "number" and exponent.value.isdigit() and int(exponent.value) > 100:
                    return {"kind": "unsupported", "reason": f"{role} exponent exceeds supported bound"}
    for role, node in parsed.items():
        if any(item.kind in {"logical", "boolean", "equation"} for item in _walk(node)):
            if name != "AlgEquiv":
                return {"kind": "unsupported", "reason": "Logical answers require AlgEquiv"}
            try:
                validate_logic(evaluate(node, student=role == "student"))
            except Unsupported as exc:
                return {"kind": "unsupported", "reason": str(exc)}
            except InvalidAnswer as exc:
                return {"kind": f"invalid_{role}", "reason": str(exc)}
    option = case.get("options", "")
    if not isinstance(option, str):
        return {"kind": "invalid_option", "reason": "option must be a string"}
    if name in {"NumAbsolute", "NumRelative"}:
        try:
            option = numeric_option_source(option)
        except (InvalidAnswer, Unsupported):
            pass  # Preserve the normal preflight classification below.
    if name == "FacForm" and not option.strip():
        return {"kind": "unsupported", "reason": "FacForm without explicit variable requires native variable inference"}
    if name == "NumDecPlaces" and not option.strip():
        return {"kind": "invalid_option", "reason": f"{name} requires an option"}
    if option.strip():
        option_ast, issue = _preflight_expression(option, "option")
        if issue:
            return {"kind": issue[0], "reason": issue[1]}
        if name == "FacForm" and option_ast.kind != "name":
            return {"kind": "unsupported", "reason": "FacForm polynomial variable option must be a symbol"}
    if name == "FacForm":
        variable = option.strip()
        if variable in _CONSTANT_NAMES or variable in _NONSCALAR_NAMES:
            return {"kind": "unsupported", "reason": "FacForm variable must be an ordinary symbol"}
        for role, node in parsed.items():
            for item in _walk(node):
                if item.kind == "call" or (item.kind == "name" and item.value != variable):
                    return {"kind": "unsupported", "reason": f"{role} outside univariate rational polynomial domain"}
                if item.kind == "binary" and item.value == "/" and any(
                        child.kind == "name" for child in _walk(item.children[1])):
                    return {"kind": "unsupported", "reason": f"{role} has variable denominator outside FacForm domain"}
    if name in _NUMERIC_TESTS:
        for role, node in parsed.items():
            if any(item.kind == "name" and item.value not in {"pi", "%pi", "e", "E", "%e"}
                   for item in _walk(node)):
                return {"kind": "unsupported", "reason": f"{role} symbolic or nonreal numeric expression outside numerical subset"}
        if name == "NumDecPlaces" and parsed["student"].kind == "name":
            return {"kind": "unsupported", "reason": "NumDecPlaces requires a written decimal literal"}
    # Extra options for tests that ignore them are part of the upstream API;
    # observe the implementation rather than silently erase those values.
    return {"kind": "supported"}


def evaluate_case(case: dict) -> dict:
    """Observe one answer-test call without host APIs or process isolation."""
    observation = {"case_id": case["id"], "test": case["test"]}
    scope = classify_case(case)
    if scope["kind"] != "supported":
        return {**observation, **scope, "message": scope["reason"]}
    try:
        # Isolate evaluation from the host, and attribute controlled source
        # errors to their actual field.  A teacher/option error must not be
        # mislabeled as a student failure or hidden as generic Unsupported.
        try:
            evaluate(case["student"], student=True)
        except InvalidAnswer as exc:
            return {**observation, "kind": "invalid_student", "message": str(exc)}
        except Unsupported:
            raise
        try:
            evaluate(case["teacher"])
        except InvalidAnswer as exc:
            return {**observation, "kind": "invalid_teacher", "message": str(exc)}
        except Unsupported:
            raise
        name, option = case["test"], case.get("options", "")
        if name in {"NumAbsolute", "NumRelative"}:
            option = numeric_option_source(option)
        if option.strip() or name in {"NumAbsolute", "NumRelative"}:
            try:
                value = evaluate(option or "0.05")
                if name == "FacForm" and not isinstance(value, sp.Symbol):
                    raise InvalidAnswer("FacForm option must be one polynomial variable")
                if name in {"NumAbsolute", "NumRelative"} and not (
                        isinstance(value, sp.Basic) and value.is_number is True
                        and value.is_real is True and not value.has(sp.nan, sp.zoo, sp.oo, -sp.oo)):
                    raise InvalidAnswer("Tolerance option must be a finite real number")
                if name == "NumDecPlaces" and not (
                        isinstance(value, sp.Basic) and value.is_Integer is True and 1 <= int(value) <= 50):
                    raise InvalidAnswer("Decimal-place option must be an integer from 1 to 50")
            except (InvalidAnswer, Unsupported, TypeError, ZeroDivisionError) as exc:
                return {**observation, "kind": "invalid_option", "message": str(exc)}
        result = answer_test(case["test"], case["student"], case["teacher"], case.get("options", ""),
                             raw=case["student"])
        if not isinstance(result, dict) or type(result.get("valid")) is not bool or type(result.get("correct")) is not bool:
            raise TypeError("answer_test returned an invalid result shape")
        kind = "result" if result["valid"] else "invalid_student"
        return {**observation, "kind": kind, **result}
    except Unsupported as exc:
        return {**observation, "kind": "unsupported", "exception_type": type(exc).__name__,
                "message": str(exc), "phase": "evaluation"}
    except InvalidAnswer as exc:
        return {**observation, "kind": "invalid_student", "exception_type": type(exc).__name__,
                "message": str(exc), "phase": "evaluation"}
    except Exception as exc:
        return {**observation, "kind": "unexpected_exception", "exception_type": type(exc).__name__,
                "message": str(exc)}


def evaluate_cases(cases: list[dict]) -> list[dict]:
    """In-process evaluator for Pyodide; the host runner adds process bounds."""
    return [evaluate_case(case) for case in cases]
