"""Instantiate, grade and self-test the supported STACK XML question subset."""

from __future__ import annotations

import math
import random
import re
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Mapping

import sympy as sp

from .assessment import answer_test
from .expressions import InvalidAnswer, Unsupported, assignments, canonical_form, evaluate, parse
from .importer import UnsupportedQuestion
from .rendering import render_castext


def _assumptions(question):
    return {"positive": bool(question.get("assumepositive")), "real": bool(question.get("assumereal"))}


def _environment(question, variant):
    if not variant:
        raise ValueError("A frozen question variant is required")
    return {name: evaluate(value, assumptions=_assumptions(question))
            for name, value in variant["env"].items()}


def _source(s):
    if isinstance(s, list):
        return "[" + ",".join(_source(x) for x in s) + "]"
    return str(s)


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


def _render(question, field, env, inputs, prts):
    return render_castext(question.get(field, ""), env, question["name"], field, inputs=inputs, feedback=prts,
                           assumptions=_assumptions(question))


def instantiate(question: dict, seed: int = 1) -> dict:
    """Freeze author random values and build a deterministic browser variant."""
    name = question["name"]
    assumptions = _assumptions(question)
    try:
        definitions = _definitions(question)
        _validate_references(question, definitions)
        env = assignments(question.get("variables", ""), rng=random.Random(int(seed)), assumptions=assumptions)
        if any(isinstance(value, sp.Float) for value in env.values()):
            raise UnsupportedQuestion(name, "questionvariables", "floating-point variables are unsupported in frozen variants")
        if not question.get("simplify", True):
            for prt in question["prts"]:
                for node in prt["nodes"]:
                    if node["test"] != "EqualComAss":
                        continue
                    where = f"prt[{prt['name']}]/node[{node['name']}]/tans"
                    if prt["feedbackvariables"].strip():
                        raise UnsupportedQuestion(name, where, "EqualComAss with unsimplified feedback variables is unsupported")
                    for key in set(re.findall(r"\b[A-Za-z_]\w*\b", node["teacher"])) & definitions.keys():
                        original = definitions[key]
                        value = env[key]
                        if "rand(" in original or "rand_with_step(" in original:
                            if not value.is_number:
                                raise UnsupportedQuestion(name, where, "random symbolic answer form cannot be frozen")
                            continue
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
            teacher = evaluate(inp["teacher"], env, assumptions=assumptions)
            if not isinstance(teacher, sp.Basic):
                raise UnsupportedQuestion(name, where + "/tans", "only scalar teacher answers are supported")
            if inp["type"] == "numerical" and teacher.is_number is not True:
                raise UnsupportedQuestion(name, where + "/tans", "numerical answer requires a number")
            if inp["syntaxhint"]:
                evaluate(inp["syntaxhint"], env, assumptions=assumptions)
        for prt in question["prts"]:
            if prt["feedbackvariables"].strip():
                # Names can depend on student inputs. Syntax is checked at grade time.
                assignments(prt["feedbackvariables"], env={**env, **{n: sp.Symbol(n) for n in inputmap}}, assumptions=assumptions)
            for node in prt["nodes"]:
                where = f"prt[{prt['name']}]/node[{node['name']}]"
                evaluate(node["student"], {**env, **{n: sp.Symbol(n) for n in inputmap}}, assumptions=assumptions)
                evaluate(node["teacher"], env, assumptions=assumptions)
                if node["test"] in {"NumAbsolute", "NumRelative", "NumDecPlaces"}:
                    if node["test"] == "NumDecPlaces" and not node["options"]:
                        raise UnsupportedQuestion(name, where + "/testoptions", "NumDecPlaces requires options")
                    if node["options"]:
                        option_value = evaluate(node["options"], env, assumptions=assumptions)
                        if node["test"] == "NumDecPlaces" and (not isinstance(option_value, sp.Basic) or option_value.is_Integer is not True or not 1 <= int(option_value) <= 50):
                            raise UnsupportedQuestion(name, where + "/testoptions", "NumDecPlaces requires 1–50 places")
                for branch in ("true", "false"):
                    render_castext(node[branch]["feedback"], env, name, where + "/" + branch + "feedback",
                                   inputs=inputmap, feedback=prtmap, assumptions=assumptions)
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


def _input_validation(inp, raw, env, assumptions):
    raw = str(raw or "").strip()
    if not raw:
        return {"valid": False, "latex": "", "feedback": "Enter an answer"}, None
    try:
        tree = parse(raw)
        if any(n.value.lower() in {w.lower() for w in inp["forbidwords"]} for n in _walk(tree) if n.kind in {"name", "call"}):
            raise InvalidAnswer("Contains a forbidden word")
        if inp["forbidfloat"] and any(n.kind == "number" and ("." in n.value or "e" in n.value.lower()) for n in _walk(tree)):
            raise InvalidAnswer("Decimal numbers are forbidden")
        if inp["requirelowestterms"]:
            for node in _walk(tree):
                if node.kind == "binary" and node.value == "/":
                    num = evaluate(node.children[0], env, assumptions=assumptions, student=True, simplify=False)
                    den = evaluate(node.children[1], env, assumptions=assumptions, student=True, simplify=False)
                    if num.is_Integer and den.is_Integer and math.gcd(int(num), int(den)) > 1:
                        raise InvalidAnswer("Write fractions in lowest terms")
                    if num.is_polynomial() and den.is_polynomial() and den.free_symbols and sp.degree(sp.gcd(num, den)) > 0:
                        raise InvalidAnswer("Write fractions in lowest terms")
        preview = evaluate(tree, env, assumptions=assumptions, student=True, simplify=False)
        value = evaluate(tree, env, assumptions=assumptions, student=True)
        if not isinstance(value, sp.Basic):
            raise InvalidAnswer("Only scalar answers are supported")
        if inp["type"] == "numerical" and value.is_number is not True:
            raise InvalidAnswer("Enter a numerical answer")
        return {"valid": True, "latex": sp.latex(preview), "feedback": ""}, value
    except (InvalidAnswer, TypeError, ValueError, ZeroDivisionError) as exc:
        return {"valid": False, "latex": "", "feedback": str(exc)}, None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


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
    if preserve_form:
        if expression in env:
            plain = not re.search(r"\b(?:rand|rand_with_step|expand|factor|ratsimp|cancel|ev|diff|float|dispdp|displaydp|decimalplaces|dispsf|significantfigures)\s*\(", source)
            text = source if not question.get("simplify", True) and plain else _source(env[expression])
        else:
            text = expression
        for key in sorted(env, key=len, reverse=True):
            if key == expression:
                continue
            text = re.sub(rf"\b{re.escape(key)}\b", lambda _m: f"({_source(env[key])})", text)
        return text
    return _source(evaluate(expression, env, assumptions=_assumptions(question)))


def validate(question: dict, answers: Mapping[str, str], seed: int = 1, *, variant: dict | None = None) -> dict:
    """Preview each parsed answer; no PRT, score or correctness is evaluated."""
    variant = instantiate(question, seed) if variant is None else variant
    env = _environment(question, variant)
    inputs = {inp["name"]: _input_validation(inp, answers.get(inp["name"], ""), env, _assumptions(question))[0]
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
    for inp in question["inputs"]:
        key = inp["name"]
        result, value = _input_validation(inp, answers.get(key, ""), env, assumptions)
        input_results[key] = result
        if result["valid"]:
            student_values[key] = value
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
                if raw_student:
                    tested_student = raw_student
                else:
                    tested_student = _source(evaluate(node["student"], penv, assumptions=assumptions))
                result = answer_test(node["test"], tested_student, node["teacher"], node["options"],
                                     env=penv, raw=raw_student or tested_student, assumptions=assumptions)
            except (InvalidAnswer, Unsupported, TypeError, ZeroDivisionError) as exc:
                raise UnsupportedQuestion(question["name"], f"prt[{prt['name']}]/node[{current}]", str(exc)) from exc
            if not result["valid"]:
                return {"status": "invalid", "score": 0.0, "inputs": input_results, "prts": prt_results,
                        "feedback": result["feedback"]}
            branch_name = "true" if result["correct"] else "false"
            branch = node[branch_name]
            score = _branch_score(score, branch)
            notes.append(branch["note"])
            if not node["quiet"]:
                rendered = render_castext(branch["feedback"], penv, question["name"],
                                          f"prt[{prt['name']}]/node[{current}]/{branch_name}feedback",
                                          inputs={i["name"]: i for i in question["inputs"]},
                                          feedback={p["name"]: p for p in question["prts"]}, assumptions=assumptions)
                if rendered:
                    feedback.append(rendered)
                if result["feedback"]:
                    feedback.append(result["feedback"])
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
                    form = any(n["test"] == "EqualComAss" and re.search(rf"\b{re.escape(key)}\b", n["student"])
                               for p in question["prts"] for n in p["nodes"])
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
                      and observed_note == expected["note"])
                checks.append({"prt": name, "passed": ok, "expected": expected,
                               "actual": {"score": observed_score, "penalty": observed_penalty, "note": observed_note}})
            results.append({"testcase": test["testcase"], "seed": variant["seed"],
                            "passed": bool(checks) and all(c["passed"] for c in checks),
                            "inputs": raw, "checks": checks, "expected": test["expected"], "actual": actual})
    return {"passed": all(r["passed"] for r in results), "results": results}
