"""Explicit, trusted author checker modules shared by CPython and Pyodide.

This is not a code sandbox. Source is embedded publicly in the static card.
Only the CLI's explicit preflight and grading execute it; input validation and
variant construction never do. No registries or callable instances are cached.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, redirect_stderr
import inspect
import json
from pathlib import Path
import re
import sys
from types import ModuleType

import sympy as sp

from .checker_api import API_VERSION, Matrix, ListValue, SetValue
from .expressions import (MatrixValue, HeldList, HeldSet, Equation, Logical,
                          Unsupported, validate_collection, is_logical)

IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}", re.ASCII)
MAX_SOURCE_BYTES = 65536


class CheckerError(Unsupported):
    """Author configuration/execution failure, never a learner wrong answer."""


def checker_identifier(identifier):
    if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
        raise CheckerError("PythonChecker requires an ASCII checker identifier")
    return identifier


def _invalid_json_constant(value):
    raise ValueError(f"{value} is not a JSON value")


def checker_spec(spec):
    """Read a named function and JSON options without evaluating XML."""
    try:
        config = json.loads(spec, parse_constant=_invalid_json_constant)
    except (TypeError, ValueError) as exc:
        raise CheckerError("PythonChecker testoptions must be a JSON object") from exc
    if (type(config) is not dict or "checker" not in config
            or set(config) - {"checker", "options"}):
        raise CheckerError("PythonChecker testoptions requires checker and optional options")
    options = config.get("options", {})
    if type(options) is not dict:
        raise CheckerError("PythonChecker options must be a JSON object")
    return checker_identifier(config["checker"]), options


def source_descriptor(path):
    source = Path(path).read_bytes().decode("utf-8")
    descriptor = {"api_version": API_VERSION, "source": source}
    validate_descriptor(descriptor)
    return descriptor


def validate_descriptor(descriptor):
    if type(descriptor) is not dict or set(descriptor) != {"api_version", "source"}:
        raise CheckerError("PythonChecker requires an explicit python-checkers source descriptor")
    if type(descriptor["api_version"]) is not int or descriptor["api_version"] != API_VERSION:
        raise CheckerError("Unsupported PythonChecker API version")
    source = descriptor["source"]
    if not isinstance(source, str) or not 0 < len(source.encode("utf-8")) <= MAX_SOURCE_BYTES:
        raise CheckerError("PythonChecker source must be 1–65536 UTF-8 bytes")
    return source


class _Discard:
    """Do not retain arbitrary author output or corrupt CLI HTML/JSON."""
    def write(self, text):
        return len(text)

    def flush(self):
        pass


@contextmanager
def _registry(descriptor):
    source = validate_descriptor(descriptor)
    # The module is temporary (normal __name__/dataclass behavior), with no
    # callable/namespace reuse even for repeated grading of the same question.
    name = "_stack_python_checker"
    previous = sys.modules.get(name)
    module = ModuleType(name)
    module.__file__ = "<PythonChecker>"
    sys.modules[name] = module
    try:
        with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            exec(compile(source, "<PythonChecker>", "exec"), module.__dict__)
            registry = module.__dict__.get("CHECKERS")
            if type(registry) is not dict or not registry or len(registry) > 32:
                raise CheckerError("CHECKERS must be a nonempty dictionary with at most 32 entries")
            for key, fn in registry.items():
                checker_identifier(key)
                calls = (fn, getattr(fn, "__call__", fn))
                if (not callable(fn) or any(inspect.iscoroutinefunction(call)
                        or inspect.isasyncgenfunction(call) or inspect.isgeneratorfunction(call) for call in calls)):
                    raise CheckerError(f"Checker {key!r} must be a synchronous callable")
                try:
                    inspect.signature(fn).bind(None, None, {})
                except (ValueError, TypeError) as exc:
                    raise CheckerError(f"Checker {key!r} must accept three positional arguments") from exc
            yield registry
    except CheckerError:
        raise
    except (Exception, SystemExit) as exc:
        raise CheckerError(f"PythonChecker author code failed ({type(exc).__name__}): {exc}") from exc
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def check_references(descriptor, identifiers):
    with _registry(descriptor) as registry:
        for identifier in identifiers:
            identifier, _ = checker_spec(identifier)
            if identifier not in registry:
                raise CheckerError(f"Unknown PythonChecker identifier {identifier!r}")


def _value(value):
    validate_collection(value)
    if is_logical(value):
        from .logic import validate_logic
        validate_logic(value)
    if isinstance(value, MatrixValue):
        return Matrix([[_value(entry) for entry in row.args] for row in value.args])
    if isinstance(value, (list, HeldList)):
        return ListValue(*(_value(x) for x in (value if isinstance(value, list) else value.args)))
    if isinstance(value, HeldSet):
        return SetValue(*(_value(x) for x in value.args))
    if isinstance(value, (sp.Expr, Equation, Logical)) or value is sp.true or value is sp.false:
        if isinstance(value, sp.Basic) and value.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
            raise CheckerError("PythonChecker arguments must be finite")
        return value
    raise CheckerError("Unsupported PythonChecker argument type")


def _result(value, student):
    if type(value) is bool:
        value = {"valid": True, "correct": value}
    if (type(value) is not dict or not {"valid", "correct"} <= set(value)
            or set(value) - {"valid", "correct", "feedback", "assessment"}):
        raise CheckerError("Checker must return bool or valid/correct with optional feedback/assessment")
    if type(value["valid"]) is not bool or type(value["correct"]) is not bool:
        raise CheckerError("Checker valid/correct must be Python bool values")
    if not value["valid"] and value["correct"]:
        raise CheckerError("An invalid checker result cannot be correct")
    feedback = value.get("feedback", "")
    if not isinstance(feedback, str) or len(feedback) > 4096:
        raise CheckerError("Checker feedback must be plain text of at most 4096 characters")
    result = {"valid": value["valid"], "correct": value["correct"],
              "feedback": feedback, "note": "", "implementation": "python-checker-v1"}
    if "assessment" in value:
        assessment = value["assessment"]
        if (not value["valid"] or not isinstance(student, sp.ImmutableMatrix)
                or type(assessment) is not dict or len(assessment) != 1
                or not set(assessment) <= {"rows", "columns"}):
            raise CheckerError("Checker assessment requires a valid matrix and one rows/columns key")
        axis, statuses = next(iter(assessment.items()))
        size = student.rows if axis == "rows" else student.cols
        if (type(statuses) is not list or len(statuses) != size
                or any(type(x) is not str or x not in {"correct", "incorrect", "dependent"} for x in statuses)):
            raise CheckerError("Checker assessment statuses must match the submitted matrix dimension")
        result["assessment"] = {axis: list(statuses)}
    return result


def invoke(descriptor, identifier, student, teacher):
    identifier, options = checker_spec(identifier)
    student, teacher = _value(student), _value(teacher)
    try:
        with _registry(descriptor) as registry:
            if identifier not in registry:
                raise CheckerError(f"Unknown PythonChecker identifier {identifier!r}")
            value = registry[identifier](student, teacher, options)
            if inspect.isawaitable(value) or inspect.isgenerator(value) or inspect.isasyncgen(value):
                if inspect.iscoroutine(value) or inspect.isgenerator(value):
                    value.close()
                raise CheckerError("Checker must return a synchronous result")
            return _result(value, student)
    except CheckerError as exc:
        raise CheckerError(f"PythonChecker {identifier!r}: {exc}") from exc


def preflight(question, variants):
    """Explicit build/test execution; never called by instantiate or validate."""
    from .engine import grade, _environment, _qtest_answer, _input_uses_written_form
    from .importer import UnsupportedQuestion
    nodes = [(p, n) for p in question["prts"] for n in p["nodes"] if n["test"] == "PythonChecker"]
    if not nodes:
        return
    for prt, node in nodes:
        try:
            check_references(question.get("python_checkers"), [node["options"]])
        except CheckerError as exc:
            raise UnsupportedQuestion(question["name"], f"prt[{prt['name']}]/node[{node['name']}]/PythonChecker", str(exc)) from exc
    for variant in variants:
        env = _environment(question, variant)
        answers = {inp["name"]: _qtest_answer(question, inp["teacher"], env,
                                                  preserve_form=_input_uses_written_form(question, inp["name"]))
                   for inp in question["inputs"]}
        result = grade(question, answers, variant=variant)
        if result["status"] != "graded":
            raise UnsupportedQuestion(question["name"], "PythonChecker/model",
                                      "Model answers must produce valid grading; check the input feedback")
