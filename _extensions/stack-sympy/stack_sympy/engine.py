"""Instantiate, grade and self-test the supported STACK XML question subset."""

from __future__ import annotations

import html
import math
import random
import re
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Mapping

import sympy as sp

from .assessment import answer_test
from .expressions import InvalidAnswer, Node, Unsupported, assignments, canonical_form, evaluate, form_latex, parse
from .importer import UnsupportedQuestion
from .expressions import (MatrixValue, is_logical, is_collection, validate_collection, collection_items,
                          AUTHOR_COLLECTION_FUNCTIONS, SCALAR_FUNCTIONS, FUNCTION_ALIASES,
                          decimal_set, contains_decimal, transformed_decimal_collection)
from .collections import normalized_value, same_type
from .logic import validate_logic
from .rendering import render_castext


def _assumptions(question):
    return {"positive": bool(question.get("assumepositive")), "real": bool(question.get("assumereal"))}


def _environment(question, variant):
    if not variant:
        raise ValueError("A frozen question variant is required")
    definitions = _definitions(question)
    return {name: evaluate(value, assumptions=_assumptions(question),
                           simplify=not bool(re.search(r"\bfactor\s*\(", definitions.get(name, ""))))
            for name, value in variant["env"].items()}


def _source(s):
    if isinstance(s, list):
        return "[" + ",".join(_source(x) for x in s) + "]"
    return str(s).lower() if s in (sp.true, sp.false) else str(s)


def _definitions(question):
    """Mirror the deliberately narrow assignment statement separator."""
    definitions = {}
    for statement in re.split(r"[;\n]+", question.get("variables", "")):
        statement = statement.strip()
        if not statement:
            continue
        match = re.fullmatch(r"([A-Za-z_]\w*)\s*:\s*(.+)", statement, re.S)
        if not match:
            raise UnsupportedQuestion(question["name"], "questionvariables", "only name:expression assignments are supported")
        if match.group(1) in definitions:
            raise UnsupportedQuestion(question["name"], f"questionvariables[{match.group(1)}]", "reassigned variable is unsupported")
        definitions[match.group(1)] = match.group(2)
    return definitions


def _validate_references(question, definitions):
    future = set(definitions)
    for key, rhs in definitions.items():
        try:
            names = {n.value for n in _walk(parse(rhs)) if n.kind == "name"}
        except InvalidAnswer as exc:
            raise UnsupportedQuestion(question["name"], f"questionvariables[{key}]", str(exc)) from exc
        overlapping = names & future
        if overlapping:
            raise UnsupportedQuestion(question["name"], f"questionvariables[{key}]",
                                      f"forward or cyclic assignment reference: {', '.join(sorted(overlapping))}")
        future.remove(key)


def _decimal_source(source, definitions):
    pending, seen = [source], set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        tree = parse(current)
        if contains_decimal(tree):
            return True
        pending.extend(definitions[n.value] for n in _walk(tree)
                       if n.kind == "name" and n.value in definitions)
    return False


def _render(question, field, env, inputs, prts):
    return render_castext(question.get(field, ""), env, question["name"], field, inputs=inputs, feedback=prts,
                           assumptions=_assumptions(question),
                           form_expression=(lambda expr: _qtest_answer(question, expr, env, preserve_form=True))
                           if not question.get("simplify", True) else None)


def _matrix_input_shape(inp, value, teacher):
    """Apply the same configured shape boundary to learners and author qtests."""
    if not isinstance(value, MatrixValue):
        raise InvalidAnswer("Enter a matrix")
    if not isinstance(teacher, MatrixValue):
        raise InvalidAnswer("Matrix input requires a matrix teacher answer")
    spec = inp.get("matrix")
    for index, axis in enumerate(("rows", "cols")):
        config = spec[axis] if spec else {"auto": False, "initial": teacher.shape[index], "min": teacher.shape[index], "max": teacher.shape[index]}
        size = value.shape[index]
        if not config["min"] <= size <= config["max"] or not config["auto"] and size != config["initial"]:
            raise InvalidAnswer(f"Matrix {axis} are outside the configured dimensions")


def instantiate(question: dict, seed: int = 1) -> dict:
    """Freeze author random values and build a deterministic browser variant."""
    name = question["name"]
    assumptions = _assumptions(question)
    try:
        definitions = _definitions(question)
        _validate_references(question, definitions)
        env = assignments(question.get("variables", ""), rng=random.Random(int(seed)), assumptions=assumptions)
        if question.get("simplify", True):
            # Author values were already simplified in native questionvariables.
            # Keep repetitions only for held author forms and submitted answers.
            env = {key: normalized_value(value) if is_collection(value) else value for key, value in env.items()}
        elif any(_collection_helper(parse(source)) for source in definitions.values()):
            raise UnsupportedQuestion(name, "questionvariables", "Finite collection helpers require questionsimplify=1")
        def has_float(value):
            return (any(has_float(x) for x in collection_items(value)) if is_collection(value)
                    else isinstance(value, sp.Basic) and value.has(sp.Float))
        if any(has_float(value) for value in env.values()):
            raise UnsupportedQuestion(name, "questionvariables", "floating-point variables are unsupported in frozen variants")
        def decimal_source(source):
            return _decimal_source(source, definitions)
        for key, value in env.items():
            if (is_collection(value) or _collection_helper(parse(definitions[key]))) and decimal_source(definitions[key]):
                raise UnsupportedQuestion(name, f"questionvariables[{key}]",
                                          "decimal collection variables cannot preserve literal precision when frozen; use exact fractions")
        def precision_guard(source, where, dynamic=()):
            tree = parse(source)
            if transformed_decimal_collection(tree):
                raise UnsupportedQuestion(name, where, "Nonliteral decimal collections lose literal precision; use exact fractions")
            if decimal_set(tree) or _collection_helper(tree) and contains_decimal(tree):
                raise UnsupportedQuestion(name, where, "Decimal literals in sets/helpers are unsupported; use exact fractions")
            nodes = list(_walk(tree))
            constructed = any(n.kind in {"list", "set"} or n.kind == "call" and n.value in AUTHOR_COLLECTION_FUNCTIONS for n in nodes)
            collection = constructed or any(n.kind == "name" and is_collection(env.get(n.value)) for n in nodes)
            if collection and any(n.kind == "name" and n.value in definitions and decimal_source(definitions[n.value]) for n in nodes):
                raise UnsupportedQuestion(name, where, "Decimal aliases in collections/helpers cannot preserve literal precision; use exact fractions")
            if constructed and any(n.kind == "name" and n.value in dynamic for n in nodes):
                raise UnsupportedQuestion(name, where, "Collections/helpers derived from learner inputs must be frozen in simplified questionvariables")
        for inp in question["inputs"]:
            for field in ("teacher", "syntaxhint"):
                if inp[field]:
                    precision_guard(inp[field], f"input[{inp['name']}]/{field}")
        for test in question.get("qtests", []):
            for source in test["inputs"].values():
                precision_guard(source, f"qtest[{test['testcase']}]")
        for prt in question["prts"]:
            dynamic = {inp["name"] for inp in question["inputs"]}
            for statement in re.split(r"[;\n]+", prt["feedbackvariables"]):
                if ":" in statement:
                    key, source = statement.split(":", 1)
                    precision_guard(source, f"prt[{prt['name']}]/feedbackvariables", dynamic)
                    dynamic.add(key.strip())
            for node in prt["nodes"]:
                for field in ("student", "teacher"):
                    precision_guard(node[field], f"prt[{prt['name']}]/node[{node['name']}]/{field}", dynamic)
                for branch in ("true", "false"):
                    for source in re.findall(r"\{@(.*?)@\}", node[branch]["feedback"], re.S):
                        precision_guard(source, f"prt[{prt['name']}]/feedback", dynamic)
        for field in ("questiontext", "generalfeedback", "specificfeedback", "questionnote"):
            for source in re.findall(r"\{@(.*?)@\}", question.get(field, ""), re.S):
                precision_guard(source, field)
        if not question.get("simplify", True):
            for prt in question["prts"]:
                for node in prt["nodes"]:
                    if node["test"] != "EqualComAss":
                        continue
                    where = f"prt[{prt['name']}]/node[{node['name']}]/tans"
                    if prt["feedbackvariables"].strip():
                        raise UnsupportedQuestion(name, where, "EqualComAss with unsimplified feedback variables is unsupported")
                    # A direct qtest alias is reconstructed from its definition
                    # by _qtest_answer. Its dependencies must still retain form.
                    qtest_sources = [test["inputs"][node["student"]].strip()
                                     for test in question.get("qtests", []) if node["student"] in test["inputs"]]
                    sources = [node["teacher"]] + [definitions.get(source, source) for source in qtest_sources]
                    transformations = {"factor", "ev", "expand", "ratsimp", "cancel"}
                    collection_form = is_collection(evaluate(node["teacher"], env, assumptions=assumptions))
                    pending, seen = [], set()
                    for source in sources:
                        tree = parse(source)
                        if tree.kind == "call" and tree.value in transformations:
                            continue
                        pending.extend(n.value for n in _walk(tree) if n.kind == "name" and n.value in definitions)
                    while pending:
                        key = pending.pop()
                        if key in seen:
                            continue
                        seen.add(key)
                        original = definitions[key]
                        value = env[key]
                        tree = parse(original)
                        if (tree.kind == "call" and tree.value in transformations
                                or not collection_form and re.search(r"\b(?:factor|ev|expand|ratsimp|cancel)\s*\(", original)):
                            # Explicit CAS transformations produce the frozen
                            # value; the assignment's input syntax is not its
                            # answer syntax under simp:false.
                            continue
                        if "rand(" in original or "rand_with_step(" in original:
                            if getattr(value, "is_number", False) is not True:
                                raise UnsupportedQuestion(name, where, "random symbolic answer form cannot be frozen")
                            continue
                        pending.extend(n.value for n in _walk(tree) if n.kind == "name" and n.value in definitions)
                        try:
                            original_form = canonical_form(original, env, assumptions)
                            frozen_form = canonical_form(_source(value), assumptions=assumptions)
                        except (Unsupported, InvalidAnswer) as exc:
                            raise UnsupportedQuestion(name, where, f"cannot verify unsimplified answer form: {exc}") from exc
                        if original_form != frozen_form:
                            raise UnsupportedQuestion(name, where, f"assignment {key} loses unsimplified answer form")
        inputmap = {i["name"]: i for i in question["inputs"]}
        prtmap = {p["name"]: p for p in question["prts"]}
        for inp in question["inputs"]:
            where = f"input[{inp['name']}]"
            try:
                teacher = evaluate(inp["teacher"], env, assumptions=assumptions)
                validate_collection(teacher)
                if not question.get("simplify", True) and _collection_helper(parse(inp["teacher"])):
                    raise Unsupported("Finite collection helpers require questionsimplify=1")
            except (InvalidAnswer, Unsupported) as exc:
                raise UnsupportedQuestion(name, where + "/tans", str(exc)) from exc
            if is_logical(teacher):
                validate_logic(teacher)
            if inp["type"] == "numerical" and getattr(teacher, "is_number", None) is not True:
                raise UnsupportedQuestion(name, where + "/tans", "numerical answer requires a number")
            if inp["type"] == "matrix" and not isinstance(teacher, MatrixValue):
                raise UnsupportedQuestion(name, where + "/tans", "matrix input requires a matrix teacher answer")
            if inp["type"] == "matrix":
                try:
                    _matrix_input_shape(inp, teacher, teacher)
                except InvalidAnswer as exc:
                    raise UnsupportedQuestion(name, where + "/tans", "teacher matrix must fit the configured dimensions: " + str(exc)) from exc
            if inp["syntaxhint"]:
                if not question.get("simplify", True) and _collection_helper(parse(inp["syntaxhint"])):
                    raise UnsupportedQuestion(name, where + "/syntaxhint", "Finite collection helpers require questionsimplify=1")
                evaluate(inp["syntaxhint"], env, assumptions=assumptions)
        for test in question.get("qtests", []):
            for key, source in test["inputs"].items():
                inp = inputmap.get(key)
                if inp is None or inp["type"] != "matrix":
                    continue
                try:
                    value = evaluate(_qtest_answer(question, source, env, preserve_form=True), env, assumptions=assumptions, student=True)
                    _matrix_input_shape(inp, value, evaluate(inp["teacher"], env, assumptions=assumptions))
                except (InvalidAnswer, Unsupported, ValueError, TypeError) as exc:
                    raise UnsupportedQuestion(name, f"qtest[{test['testcase']}]/testinput[{key}]", str(exc)) from exc
        if not question.get("simplify", True):
            for test in question.get("qtests", []):
                if any(_collection_helper(parse(source)) for source in test["inputs"].values()):
                    raise UnsupportedQuestion(name, f"qtest[{test['testcase']}]", "Finite collection helpers require questionsimplify=1")
        for prt in question["prts"]:
            placeholders = {n: evaluate(i["teacher"], env, assumptions=assumptions) for n, i in inputmap.items()}
            preview_env = {**env, **placeholders}
            dynamic = set(inputmap) | {statement.split(":", 1)[0].strip()
                                       for statement in re.split(r"[;\n]+", prt["feedbackvariables"]) if ":" in statement}
            if prt["feedbackvariables"].strip():
                if any(_collection_helper(parse(source)) for source in _feedback_definitions(prt["feedbackvariables"])):
                    raise UnsupportedQuestion(name, f"prt[{prt['name']}]/feedbackvariables", "Finite collection helpers must be frozen in simplified questionvariables")
                # Names can depend on student inputs. Syntax is checked at grade time.
                preview_env = assignments(prt["feedbackvariables"], preview_env, assumptions=assumptions)
            for node in prt["nodes"]:
                where = f"prt[{prt['name']}]/node[{node['name']}]"
                if (not question.get("simplify", True)
                        and any(_collection_helper(parse(node[field])) for field in ("student", "teacher"))):
                    raise UnsupportedQuestion(name, where, "Finite collection helpers require questionsimplify=1")
                if (node["test"] not in {"AlgEquiv", "SameType"}
                        and any(_collection_helper(parse(node[field])) for field in ("student", "teacher"))):
                    raise UnsupportedQuestion(name, where, "Direct finite helper calls require AlgEquiv or SameType; use a frozen evaluated author value")
                if node["test"] == "PythonChecker":
                    # A later node may be guarded by an earlier predicate.
                    # Check syntax, not its potentially unsafe teacher value.
                    from .checkers import checker_spec, validate_descriptor
                    checker_spec(node["options"])
                    validate_descriptor(question.get("python_checkers"))
                    parse(node["student"])
                    parse(node["teacher"])
                    for branch in ("true", "false"):
                        render_castext(node[branch]["feedback"], env, name, where + "/" + branch + "feedback",
                                       inputs=inputmap, feedback=prtmap, assumptions=assumptions,
                                       form_expression=(lambda expr: _qtest_answer(question, expr, env, preserve_form=True))
                                       if not question.get("simplify", True) else None)
                    continue
                # Use actual typed teacher placeholders so collection arithmetic
                # and unsupported tests are rejected while building the question.
                student_value = evaluate(node["student"], preview_env, assumptions=assumptions)
                teacher_value = evaluate(node["teacher"], preview_env, assumptions=assumptions)
                for field, value in (("student", student_value), ("teacher", teacher_value)):
                    if (is_collection(value) and any(n.kind == "name" and n.value in dynamic for n in _walk(parse(node[field])))
                            and not (field == "student" and node[field].strip() in inputmap)):
                        raise UnsupportedQuestion(name, where, "Collection checks require a direct learner input name to preserve literal precision; teacher collections must use frozen author values")
                for value in (student_value, teacher_value):
                    validate_collection(value)
                if any(isinstance(value, MatrixValue) for value in (student_value, teacher_value)) and node["test"] not in {"AlgEquiv", "SameType", "EqualComAss"}:
                    raise UnsupportedQuestion(name, where, "Matrices require AlgEquiv, SameType or EqualComAss")
                if (any(is_collection(x) for x in (student_value, teacher_value))
                        and node["test"] not in {"AlgEquiv", "Sets", "SameType", "EqualComAss"}):
                    raise UnsupportedQuestion(name, where, "Collections require AlgEquiv, Sets, SameType or EqualComAss")
                if is_logical(teacher_value):
                    validate_logic(teacher_value)
                    if node["test"] != "AlgEquiv":
                        raise UnsupportedQuestion(name, where, "Logical answers require AlgEquiv")
                if node["test"] == "FacForm":
                    if not node["options"]:
                        raise UnsupportedQuestion(name, where + "/testoptions", "FacForm requires a polynomial variable option")
                    try:
                        option_value = evaluate(node["options"], env, assumptions=assumptions)
                    except (InvalidAnswer, Unsupported, TypeError, ValueError, ZeroDivisionError) as exc:
                        raise UnsupportedQuestion(name, where + "/testoptions", f"invalid FacForm variable option: {exc}") from exc
                    if not isinstance(option_value, sp.Symbol):
                        raise UnsupportedQuestion(name, where + "/testoptions", "FacForm requires a single polynomial variable")
                if node["test"] in {"NumAbsolute", "NumRelative", "NumDecPlaces"}:
                    if node["test"] == "NumDecPlaces" and not node["options"]:
                        raise UnsupportedQuestion(name, where + "/testoptions", "NumDecPlaces requires options")
                    if node["options"]:
                        option_value = evaluate(node["options"], env, assumptions=assumptions)
                        if node["test"] == "NumDecPlaces" and (not isinstance(option_value, sp.Basic) or option_value.is_Integer is not True or not 1 <= int(option_value) <= 50):
                            raise UnsupportedQuestion(name, where + "/testoptions", "NumDecPlaces requires 1–50 places")
                for branch in ("true", "false"):
                    render_castext(node[branch]["feedback"], env, name, where + "/" + branch + "feedback",
                                   inputs=inputmap, feedback=prtmap, assumptions=assumptions,
                                   form_expression=(lambda expr: _qtest_answer(question, expr, env, preserve_form=True))
                                   if not question.get("simplify", True) else None)
        for field in ("questiontext", "generalfeedback", "specificfeedback", "questionnote"):
            _render(question, field, env, inputmap, prtmap)
        frozen = {key: _source(value) for key, value in env.items()}
        return {"seed": int(seed), "env": frozen,
                "question_html": _render(question, "questiontext", env, inputmap, prtmap),
                "generalfeedback_html": _render(question, "generalfeedback", env, inputmap, prtmap),
                "specificfeedback_html": _render(question, "specificfeedback", env, inputmap, prtmap),
                "questionnote_html": _render(question, "questionnote", env, inputmap, prtmap)}
    except UnsupportedQuestion:
        raise
    except (Unsupported, InvalidAnswer, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise UnsupportedQuestion(name, "instantiation", str(exc)) from exc


def _input_validation(inp, raw, env, assumptions, question=None):
    raw = str(raw or "").strip()
    if not raw:
        return {"valid": False, "latex": "", "feedback": "Enter an answer"}, None, None
    try:
        tree = parse(raw, insertstars=inp.get("insertstars", 0))
        if any(n.value.lower() in {w.lower() for w in inp["forbidwords"]} for n in _walk(tree) if n.kind in {"name", "call"}):
            raise InvalidAnswer("Contains a forbidden word")
        if inp["forbidfloat"] and any(n.kind == "number" and ("." in n.value or "e" in n.value.lower()) for n in _walk(tree)):
            raise InvalidAnswer("Decimal numbers are forbidden")
        if inp["requirelowestterms"]:
            for node in _walk(tree):
                if node.kind == "binary" and node.value == "/":
                    num = evaluate(node.children[0], env, assumptions=assumptions, student=True, simplify=False)
                    den = evaluate(node.children[1], env, assumptions=assumptions, student=True, simplify=False)
                    if not isinstance(num, sp.Expr) or not isinstance(den, sp.Expr):
                        raise InvalidAnswer("Arithmetic requires scalar expressions")
                    if num.is_Integer and den.is_Integer and (math.gcd(int(num), int(den)) > 1
                                                              or num < 0 and den < 0):
                        raise InvalidAnswer("Write fractions in lowest terms")
                    # STACK's all_lowest_termsex examines written numeric
                    # fractions; polynomial cancellation is a separate test.
        evaluate(tree, env, assumptions=assumptions, student=True, simplify=False)
        value = evaluate(tree, env, assumptions=assumptions, student=True)
        validate_collection(value)
        if inp["type"] == "matrix":
            teacher = evaluate(inp["teacher"], env, assumptions=assumptions)
            _matrix_input_shape(inp, value, teacher)
        if question is not None and is_collection(value):
            definitions = _definitions(question)
            if any(n.kind == "name" and n.value in definitions and _decimal_source(definitions[n.value], definitions)
                   for n in _walk(tree)):
                raise InvalidAnswer("Decimal author aliases in collection answers lose literal precision; use exact fractions")
        if inp.get("checkanswertype"):
            teacher = evaluate(inp["teacher"], env, assumptions=assumptions)
            if (is_collection(value) or is_collection(teacher)) and not same_type(value, teacher):
                raise InvalidAnswer("Use the same collection type as the teacher answer")
        if is_logical(value):
            validate_logic(value)
        if inp["type"] == "numerical" and getattr(value, "is_number", None) is not True:
            raise InvalidAnswer("Enter a numerical answer")
        return {"valid": True, "latex": form_latex(tree, env), "feedback": ""}, value, tree
    except (InvalidAnswer, TypeError, ValueError, ZeroDivisionError) as exc:
        return {"valid": False, "latex": "", "feedback": str(exc)}, None, None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _collection_helper(tree):
    return any(n.kind == "call" and n.value in AUTHOR_COLLECTION_FUNCTIONS for n in _walk(tree))


def _feedback_definitions(source):
    # Syntax remains validated by assignments; this only screens helper calls.
    return [statement.split(":", 1)[1] for statement in re.split(r"[;\n]+", source)
            if ":" in statement]


def _branch_score(current, branch):
    score = branch["score"]
    if branch["mode"] == "=":
        return score
    if branch["mode"] == "+":
        return current + score
    return current - score


def _qtest_answer(question, expression, env, *, preserve_form=False):
    """Evaluate trusted author test input without discarding written precision.

    STACK's ``dispdp`` carries a display width that a SymPy Rational cannot
    encode. This applies to direct calls and question variables assigned by a
    display function. For EqualComAss the written algebraic form is material,
    so substitute values into the original expression without expanding it.
    """
    expression = expression.strip()
    definitions = _definitions(question)
    source = definitions.get(expression, expression)
    if not question.get("simplify", True) and _collection_helper(parse(source)):
        raise Unsupported("Finite collection helpers require questionsimplify=1")
    display = re.fullmatch(r"(?:dispdp|displaydp|decimalplaces)\s*\((.*),\s*(\d+)\s*\)", source.strip(), re.S)
    if display:
        digits = int(display.group(2))
        if digits > 50:
            raise Unsupported("Display precision exceeds supported limit")
        value = evaluate(expression, env, assumptions=_assumptions(question))
        with localcontext() as ctx:
            ctx.prec = 130
            decimal = Decimal(str(sp.N(value, 110)))
            return format(decimal.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_EVEN), f".{digits}f")
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", source.strip()):
        return source.strip()
    tree = parse(source)
    if (tree.kind == "list" or tree.kind == "call" and tree.value == "matrix") and contains_decimal(tree):
        return _author_form(source, env, _assumptions(question))
    if preserve_form:
        if expression in env:
            text = (_source(env[expression]) if ((question.get("simplify", True)
                                                  and not re.search(r"\bfactor\s*\(", source))
                                                 or re.search(r"\b(?:rand|rand_with_step)\s*\(", source))
                    else _author_form(source, env, _assumptions(question)))
        else:
            text = _author_form(expression, env, _assumptions(question))
        return text
    return _source(evaluate(expression, env, assumptions=_assumptions(question)))


def _author_form(source, env, assumptions):
    """Resolve trusted qtest aliases but preserve operations outside CAS calls."""
    def render(n: Node):
        if n.kind == "name":
            return f"({_source(env[n.value])})" if n.value in env else n.value
        if n.kind == "number":
            return n.value
        if n.kind in {"list", "set"}:
            opening, closing = ("[", "]") if n.kind == "list" else ("{", "}")
            return opening + ",".join(render(c) for c in n.children) + closing
        if n.kind == "unary":
            return f"({n.value}{render(n.children[0])})"
        if n.kind == "binary":
            return f"({render(n.children[0])}{'^' if n.value == '**' else n.value}{render(n.children[1])})"
        if n.kind == "call":
            if n.value in SCALAR_FUNCTIONS or n.value in FUNCTION_ALIASES or n.value == "matrix":
                return n.value + "(" + ",".join(render(c) for c in n.children) + ")"
            if n.value == "factor" and len(n.children) == 1:
                value = evaluate(n.children[0], env, assumptions=assumptions)
                if value.is_Integer and value > 1:
                    if int(value).bit_length() > 40:
                        raise Unsupported("Integer factorization exceeds supported bound")
                    coefficients = sp.factorint(int(value))
                    return "*".join(f"{p}^{power}" if power != 1 else str(p)
                                    for p, power in coefficients.items())
            return f"({_source(evaluate(n, env, assumptions=assumptions))})"
        raise Unsupported("Unsupported form-sensitive qtest expression")
    tree = parse(source)
    result = render(tree)
    return result[1:-1] if tree.kind in {"binary", "unary"} else result


def _answer_note_matches(expected: str, actual: list[str]) -> bool:
    """STACK questiontestresult::test_answer_note ordered-subsequence rules."""
    expected = expected.strip()
    if not expected:
        return False
    if expected == "()":
        return True
    if not actual:
        return expected == "NULL"
    if expected == "NULL":
        return False
    start = expected.startswith("[")
    if expected[:1] in "[(":
        expected = expected[1:]
    end = not expected.endswith(")")
    if expected.endswith(("]", ")")):
        expected = expected[:-1]
    wanted = [note.strip() for note in expected.split("|")]
    if start and wanted[0] != actual[0].strip():
        return False
    if end and wanted[-1] != actual[-1].strip():
        return False
    position = 0
    for note in wanted:
        while position < len(actual) and actual[position].strip() != note:
            position += 1
        if position == len(actual):
            return False
        position += 1
    return True


def validate(question: dict, answers: Mapping[str, str], seed: int = 1, *, variant: dict | None = None) -> dict:
    """Preview each parsed answer; no PRT, score or correctness is evaluated."""
    variant = instantiate(question, seed) if variant is None else variant
    env = _environment(question, variant)
    inputs = {inp["name"]: _input_validation(inp, answers.get(inp["name"], ""), env, _assumptions(question), question)[0]
              for inp in question["inputs"]}
    valid = all(result["valid"] for result in inputs.values())
    return {"status": "valid" if valid else "invalid", "inputs": inputs,
            "feedback": "Review the parsed answers" if valid else "Correct invalid answers before grading"}


def grade(question: dict, answers: Mapping[str, str], seed: int = 1, *, variant: dict | None = None) -> dict:
    """Grade raw student strings against a frozen variant, returning JSON values."""
    variant = instantiate(question, seed) if variant is None else variant
    env = _environment(question, variant)
    assumptions = _assumptions(question)
    input_results = {}
    student_values = {}
    student_trees = {}
    for inp in question["inputs"]:
        key = inp["name"]
        result, value, tree = _input_validation(inp, answers.get(key, ""), env, assumptions, question)
        input_results[key] = result
        if result["valid"]:
            student_values[key] = value
            student_trees[key] = tree
    if any(not item["valid"] for item in input_results.values()):
        return {"status": "invalid", "score": 0.0, "inputs": input_results, "prts": {},
                "feedback": "Check your answers before grading"}
    prt_results = {}
    for prt in question["prts"]:
        penv = {**env, **student_values}
        if prt["feedbackvariables"].strip():
            try:
                penv = assignments(prt["feedbackvariables"], penv, assumptions=assumptions)
            except (InvalidAnswer, Unsupported) as exc:
                raise UnsupportedQuestion(question["name"], f"prt[{prt['name']}]/feedbackvariables", str(exc)) from exc
        nodes = {n["name"]: n for n in prt["nodes"]}
        current = "0"
        score, notes, feedback, branches = 0.0, [], [], []
        while current != "-1":
            node = nodes[current]
            # The student expression may be an input name or an author expression
            # using one or more inputs. The answer-test parser sees a safe string.
            try:
                raw_student = answers.get(node["student"], "")
                if node["student"] in student_trees:
                    tested_student = student_trees[node["student"]]
                else:
                    tested_student = _source(evaluate(node["student"], penv, assumptions=assumptions))
                teacher = node["teacher"]
                if node["test"] == "EqualComAss" and not question.get("simplify", True):
                    teacher = _qtest_answer(question, teacher, env, preserve_form=True)
                if node["test"] == "PythonChecker":
                    from .checkers import invoke
                    result = invoke(question.get("python_checkers"), node["options"],
                                    student_values[node["student"]],
                                    evaluate(teacher, penv, assumptions=assumptions))
                else:
                    result = answer_test(node["test"], tested_student, teacher, node["options"],
                                         env=penv, raw=raw_student or (tested_student if isinstance(tested_student, str) else ""), assumptions=assumptions)
            except (InvalidAnswer, Unsupported, TypeError, ZeroDivisionError) as exc:
                raise UnsupportedQuestion(question["name"], f"prt[{prt['name']}]/node[{current}]", str(exc)) from exc
            if not result["valid"]:
                if node["test"] == "PythonChecker":
                    detail = input_results[node["student"]]
                    detail.update(valid=False, feedback=result["feedback"] if not node["quiet"] else "Invalid answer")
                # No vector verdict remains authoritative on an invalid grade,
                # including assessments from earlier inputs or response trees.
                for detail in input_results.values():
                    detail.pop("assessment", None)
                return {"status": "invalid", "score": 0.0, "inputs": input_results, "prts": prt_results,
                        "feedback": input_results[node["student"]]["feedback"] if node["test"] == "PythonChecker" else result["feedback"]}
            if node["test"] == "PythonChecker" and "assessment" in result and not node["quiet"]:
                input_results[node["student"]]["assessment"] = result["assessment"]
            branch_name = "true" if result["correct"] else "false"
            branch = node[branch_name]
            score = _branch_score(score, branch)
            notes.append(branch["note"])
            if not node["quiet"]:
                rendered = render_castext(branch["feedback"], penv, question["name"],
                                          f"prt[{prt['name']}]/node[{current}]/{branch_name}feedback",
                                          inputs={i["name"]: i for i in question["inputs"]},
                                          feedback={p["name"]: p for p in question["prts"]}, assumptions=assumptions,
                                          form_expression=(lambda expr: _qtest_answer(question, expr, penv, preserve_form=True))
                                          if not question.get("simplify", True) else None)
                if rendered:
                    feedback.append(rendered)
                if result["feedback"]:
                    feedback.append(html.escape(result["feedback"]) if node["test"] == "PythonChecker" else result["feedback"])
            branches.append({"node": current, "branch": branch_name, "note": branch["note"]})
            current = str(branch["next"])
        prt_results[prt["name"]] = {"score": round(max(0.0, min(1.0, score)), 10),
                                     "feedback": " ".join(feedback), "notes": notes,
                                     "note": " | ".join(x for x in notes if x), "path": branches}
    total_weight = sum(p["value"] for p in question["prts"])
    if total_weight <= 0:
        raise UnsupportedQuestion(question["name"], "prts", "total PRT value must be positive")
    score = sum(p["value"] * prt_results[p["name"]]["score"] for p in question["prts"]) / total_weight
    return {"status": "graded", "score": round(score, 10), "inputs": input_results, "prts": prt_results,
            "feedback": " ".join(p["feedback"] for p in prt_results.values() if p["feedback"])}


def _input_uses_written_form(question, key):
    return any(n["test"] in {"EqualComAss", "FacForm", "SingleFrac", "LowestTerms"}
               and re.search(rf"\b{re.escape(key)}\b", n["student"])
               for p in question["prts"] for n in p["nodes"])


def run_question_tests(question: dict, seeds=(1,), variants=None) -> dict:
    """Run native qtests. Each author input is evaluated in the variant env."""
    variants = list(variants) if variants is not None else [instantiate(question, s) for s in seeds]
    results = []
    for variant in variants:
        env = _environment(question, variant)
        for test in question.get("qtests", []):
            raw = {}
            for key, expression in test["inputs"].items():
                try:
                    form = _input_uses_written_form(question, key)
                    raw[key] = _qtest_answer(question, expression, env, preserve_form=form)
                except (Unsupported, InvalidAnswer, ValueError) as exc:
                    raise UnsupportedQuestion(question["name"], f"qtest[{test['testcase']}]/testinput[{key}]", str(exc)) from exc
            actual = grade(question, raw, variant=variant)
            checks = []
            for name, expected in test["expected"].items():
                result = actual["prts"].get(name, {})
                observed_score = result.get("score")
                observed_note = result.get("note", "")
                # STACK default penalty is charged on a wrong attempt; this
                # runner compares only the initial attempt represented by XML.
                observed_penalty = question["penalty"] if observed_score is not None and observed_score < 1 else 0.0
                ok = (observed_score is not None and abs(observed_score - expected["score"]) < 1e-8
                      and abs(observed_penalty - expected["penalty"]) < 1e-8
                      and _answer_note_matches(expected["note"], [n for n in result.get("notes", []) if n]))
                checks.append({"prt": name, "passed": ok, "expected": expected,
                               "actual": {"score": observed_score, "penalty": observed_penalty, "note": observed_note}})
            results.append({"testcase": test["testcase"], "seed": variant["seed"],
                            "passed": bool(checks) and all(c["passed"] for c in checks),
                            "inputs": raw, "checks": checks, "expected": test["expected"], "actual": actual})
    return {"passed": all(r["passed"] for r in results), "results": results}
