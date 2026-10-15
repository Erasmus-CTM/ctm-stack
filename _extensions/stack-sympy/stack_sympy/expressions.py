"""Small, deliberately bounded STACK/Maxima expression subset.

The grammar is parsed directly; no Python evaluation or SymPy string parser is
ever used on author or student text. Unsupported CAS syntax fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import random
import re
from typing import Any, Mapping

import sympy as sp


class Unsupported(ValueError):
    """An expression or answer test is outside the supported subset."""


class InvalidAnswer(ValueError):
    """Malformed or unsafe student input."""


MAX_CHARS = 1200
MAX_TOKENS = 350
MAX_DEPTH = 40
MAX_POWER = 100
MAX_DIGITS = 100
_LEX = re.compile(r"\s*(?:(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|(?P<name>%?[A-Za-z_][A-Za-z_0-9]*)|(?P<op>\*\*|[+*/^(),\[\]-]))", re.ASCII)
_NAMES = {"pi": sp.pi, "%pi": sp.pi, "e": sp.E, "E": sp.E, "%e": sp.E,
          "i": sp.I, "I": sp.I, "%i": sp.I}
_STUDENT_FUNCTIONS = {"sqrt", "sin", "cos", "tan", "exp", "log", "abs"}
_AUTHOR_FUNCTIONS = _STUDENT_FUNCTIONS | {"diff", "expand", "factor", "ratsimp", "cancel", "ev", "float", "rand", "rand_with_step", "decimalplaces", "dispdp", "displaydp", "significantfigures", "dispsf"}


@dataclass(frozen=True)
class Node:
    kind: str
    value: str = ""
    children: tuple["Node", ...] = ()


def _tokens(source: str) -> list[tuple[str, str]]:
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_CHARS:
        raise InvalidAnswer("Empty or oversized expression")
    out = []
    pos = 0
    while pos < len(source):
        if source[pos:].isspace():
            break
        match = _LEX.match(source, pos)
        if match is None:
            raise InvalidAnswer(f"Unexpected character at position {pos}")
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "number" and len(value) > MAX_DIGITS:
            raise InvalidAnswer("Number too long")
        out.append((kind, value))
        pos = match.end()
        if len(out) > MAX_TOKENS:
            raise InvalidAnswer("Too many tokens")
    out.append(("end", ""))
    return out


class _Parser:
    def __init__(self, source: str):
        self.tokens = _tokens(source)
        self.pos = 0

    @property
    def current(self):
        return self.tokens[self.pos][1]

    def take(self, value: str):
        if self.current != value:
            raise InvalidAnswer(f"Expected {value!r}")
        self.pos += 1

    def expression(self, minimum: int = 0, depth: int = 0) -> Node:
        if depth > MAX_DEPTH:
            raise InvalidAnswer("Expression nested too deeply")
        kind, val = self.tokens[self.pos]
        self.pos += 1
        if kind == "number":
            lhs = Node("number", val)
        elif kind == "name":
            if self.current == "(":
                if val.lower() not in _AUTHOR_FUNCTIONS:
                    raise InvalidAnswer(f"Function {val} is not allowed")
                self.take("(")
                args = []
                if self.current != ")":
                    while True:
                        args.append(self.expression(depth=depth + 1))
                        if self.current != ",":
                            break
                        self.take(",")
                self.take(")")
                lhs = Node("call", val.lower(), tuple(args))
            else:
                lhs = Node("name", val)
        elif val in ("+", "-"):
            lhs = Node("unary", val, (self.expression(25, depth + 1),))
        elif val == "(":
            lhs = self.expression(depth=depth + 1)
            self.take(")")
        elif val == "[":
            items = []
            if self.current != "]":
                while True:
                    items.append(self.expression(depth=depth + 1))
                    if self.current != ",":
                        break
                    self.take(",")
            self.take("]")
            lhs = Node("list", children=tuple(items))
        else:
            raise InvalidAnswer("Expected an expression")
        while True:
            op = self.current
            if op == "[" and 40 >= minimum:
                self.take("[")
                idx = self.expression(depth=depth + 1)
                self.take("]")
                lhs = Node("index", children=(lhs, idx))
                continue
            bp = {"+": 10, "-": 10, "*": 20, "/": 20, "^": 30, "**": 30}.get(op, -1)
            if bp < minimum:
                break
            self.pos += 1
            rhs = self.expression(bp if op in ("^", "**") else bp + 1, depth + 1)
            lhs = Node("binary", op, (lhs, rhs))
        return lhs


def parse(text: str) -> Node:
    parser = _Parser(text)
    node = parser.expression()
    if parser.tokens[parser.pos][0] != "end":
        raise InvalidAnswer("Unexpected trailing text")
    return node


def _finite(value: Any):
    if isinstance(value, list):
        for item in value:
            _finite(item)
    elif isinstance(value, sp.Basic) and value.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
        raise InvalidAnswer("Non-finite value")
    return value


def _number(text: str):
    if "e" in text.lower():
        # Decimal's exponent is bounded before constructing an enormous Rational.
        coefficient, exponent = re.split("[eE]", text)
        if abs(int(exponent)) > MAX_POWER:
            raise InvalidAnswer("Scientific exponent too large")
        return sp.Rational(coefficient) * sp.Integer(10) ** int(exponent)
    return sp.Rational(text)


def _integer(value: Any, *, lower: int | None = None, upper: int = 100000) -> int:
    if not isinstance(value, sp.Basic) or value.is_Integer is not True:
        raise Unsupported("Expected an integer")
    result = int(value)
    if (lower is not None and result < lower) or abs(result) > upper:
        raise Unsupported("Integer outside supported range")
    return result


def _decimal_round(value: sp.Expr, digits: int, *, significant: bool = False):
    if value.is_number is not True or value.is_real is not True:
        raise Unsupported("Rounding requires a real numeric expression")
    digits = _integer(sp.Integer(digits), lower=1 if significant else 0, upper=100)
    with localcontext() as context:
        context.prec = 150
        decimal = Decimal(str(sp.N(value, 125)))
        if not decimal.is_finite():
            raise InvalidAnswer("Non-finite value")
        places = digits - 1 - decimal.adjusted() if significant and decimal else digits
        quantum = Decimal(1).scaleb(-places)
        rounded = decimal.quantize(quantum, rounding=ROUND_HALF_EVEN)
        return sp.Rational(str(rounded))


def evaluate(node_or_string: Node | str, env: Mapping[str, Any] | None = None, *, rng: random.Random | None = None,
             assumptions: Mapping[str, bool] | None = None, student: bool = False, simplify: bool = True):
    """Evaluate a parsed expression with a small explicit function whitelist.

    Student calls are limited to elementary scalar functions; random values,
    CAS transformations, lists, and indexing are author-only.
    """
    node = parse(node_or_string) if isinstance(node_or_string, str) else node_or_string
    if not isinstance(node, Node):
        raise Unsupported("Expected a parsed expression")
    env = {} if env is None else env
    assumptions = assumptions or {}
    rng = rng if rng is not None else random.Random()

    def visit(n: Node, depth=0):
        if depth > MAX_DEPTH:
            raise InvalidAnswer("Expression nested too deeply")
        if n.kind == "number":
            return _number(n.value)
        if n.kind == "name":
            if n.value in _NAMES:
                return _NAMES[n.value]
            if n.value.startswith("%"):
                raise InvalidAnswer("Unknown percent constant")
            if n.value in env:
                value = env[n.value]
                if not isinstance(value, (sp.Basic, list)):
                    raise Unsupported("Environment must hold SymPy values")
                return value
            if n.value in {"simp", "true", "false"}:
                raise InvalidAnswer("Boolean flags are not scalar expressions")
            return sp.Symbol(n.value, **{k: True for k in ("real", "positive") if assumptions.get(k)})
        if n.kind == "list":
            if student:
                raise InvalidAnswer("Only scalar student answers are supported")
            return [visit(c, depth + 1) for c in n.children]
        if n.kind == "index":
            if student:
                raise InvalidAnswer("Only scalar student answers are supported")
            seq = visit(n.children[0], depth + 1)
            idx = _integer(visit(n.children[1], depth + 1), lower=1)
            if not isinstance(seq, list) or idx > len(seq):
                raise Unsupported("Index outside list")
            return seq[idx - 1]
        if n.kind == "unary":
            value = visit(n.children[0], depth + 1)
            return value if n.value == "+" else -value
        if n.kind == "binary":
            a, b = (visit(c, depth + 1) for c in n.children)
            if not isinstance(a, sp.Basic) or not isinstance(b, sp.Basic):
                raise Unsupported("Arithmetic requires scalar expressions")
            if n.value == "+":
                result = sp.Add(a, b, evaluate=simplify)
            elif n.value == "-":
                result = sp.Add(a, sp.Mul(-1, b, evaluate=simplify), evaluate=simplify)
            elif n.value == "*":
                result = sp.Mul(a, b, evaluate=simplify)
            elif n.value == "/":
                if b == 0:
                    raise InvalidAnswer("Division by zero")
                result = sp.Mul(a, sp.Pow(b, -1, evaluate=simplify), evaluate=simplify)
            else:
                if b.is_number and b.is_real and abs(float(sp.N(b, 16))) > MAX_POWER:
                    raise InvalidAnswer("Exponent too large")
                result = sp.Pow(a, b, evaluate=simplify)
            return _finite(result)
        if n.kind == "call":
            name = n.value
            if student and name not in _STUDENT_FUNCTIONS:
                raise InvalidAnswer(f"Function {name} is not allowed in student input")
            if name == "ev":
                if len(n.children) != 2 or n.children[1] != Node("name", "simp"):
                    raise Unsupported("Only ev(expr,simp) is supported")
                return visit(n.children[0], depth + 1)
            args = [visit(c, depth + 1) for c in n.children]
            if name == "rand":
                if len(args) != 1:
                    raise Unsupported("rand takes one argument")
                if isinstance(args[0], list):
                    if not args[0]:
                        raise Unsupported("Empty random choice")
                    return rng.choice(args[0])
                return sp.Integer(rng.randrange(_integer(args[0], lower=1)))
            if name == "rand_with_step":
                if len(args) != 3:
                    raise Unsupported("rand_with_step takes three arguments")
                start, end, step = (_integer(x) for x in args)
                if start > end or step <= 0:
                    raise Unsupported("Invalid random range")
                return sp.Integer(rng.choice(range(start, end + 1, step)))
            if name in {"decimalplaces", "dispdp", "displaydp", "significantfigures", "dispsf"}:
                if len(args) != 2:
                    raise Unsupported(f"{name} takes two arguments")
                return _decimal_round(args[0], _integer(args[1], lower=0, upper=100), significant=name in {"significantfigures", "dispsf"})
            if name == "diff":
                if len(args) not in (2, 3) or not isinstance(args[1], sp.Symbol):
                    raise Unsupported("diff expects expression, variable, optional order")
                return sp.diff(args[0], args[1], *([_integer(args[2], lower=0, upper=10)] if len(args) == 3 else []))
            funcs = {"sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "exp": sp.exp,
                     "log": sp.log, "abs": sp.Abs, "expand": sp.expand, "factor": sp.factor,
                     "ratsimp": sp.cancel, "cancel": sp.cancel, "float": lambda x: sp.N(x, 17)}
            if name not in funcs or len(args) != 1 or isinstance(args[0], list):
                raise Unsupported(f"Unsupported call to {name}")
            return _finite(funcs[name](args[0]))
        raise Unsupported("Unknown expression node")

    return _finite(visit(node))


def assignments(source: str, env: Mapping[str, Any] | None = None, *, rng: random.Random | None = None,
                assumptions: Mapping[str, bool] | None = None) -> dict[str, Any]:
    """Evaluate semicolon/newline-separated name:expression author assignments."""
    result = dict(env or {})
    if not isinstance(source, str) or len(source) > 20000:
        raise Unsupported("Assignment source too long")
    for stmt in re.split(r"[;\n]+", source):
        stmt = stmt.strip()
        if not stmt:
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*)\s*:\s*(.+)", stmt, re.DOTALL)
        if match is None:
            raise Unsupported("Only name:expression assignments are supported")
        name, expression = match.groups()
        if name in _NAMES or name in {"simp", "true", "false"}:
            raise Unsupported("Cannot assign a reserved name")
        result[name] = evaluate(expression, result, rng=rng, assumptions=assumptions)
    return result


def canonical_form(node: Node | str, env: Mapping[str, Any] | None = None,
                   assumptions: Mapping[str, bool] | None = None):
    """Canonical commutative/associative *syntax*, without algebraic collection.

    Flatten and sort sums/products; rewrite subtraction and division as signed
    terms and reciprocal factors. Named author values are inserted structurally.
    """
    node = parse(node) if isinstance(node, str) else node
    env = env or {}

    def from_sympy(value):
        if value.is_Number:
            return ("number", str(sp.Rational(str(value))))
        if value.is_Symbol:
            return ("symbol", str(value))
        if value.is_Add:
            return combine("add", [from_sympy(x) for x in value.args])
        if value.is_Mul:
            return combine("mul", [from_sympy(x) for x in value.args])
        if value.is_Pow:
            return ("pow", from_sympy(value.base), from_sympy(value.exp))
        return ("call", value.func.__name__.lower(), tuple(from_sympy(x) for x in value.args))

    def combine(op, terms):
        flattened = []
        for term in terms:
            if term[0] == op:
                flattened.extend(term[1])
            else:
                flattened.append(term)
        numeric = [sp.Rational(x[1]) for x in flattened if x[0] == "number"]
        flattened = [x for x in flattened if x[0] != "number"]
        if numeric:
            aggregate = sum(numeric) if op == "add" else sp.prod(numeric)
            if (op == "add" and aggregate != 0) or (op == "mul" and aggregate != 1) or not flattened:
                flattened.append(("number", str(aggregate)))
        return (op, tuple(sorted(flattened, key=repr))) if len(flattened) > 1 else flattened[0]

    def negative(term):
        if term[0] == "number":
            return ("number", str(-sp.Rational(term[1])))
        if term[0] == "mul":
            factors = list(term[1])
            for i, factor in enumerate(factors):
                if factor[0] == "number":
                    factors[i] = negative(factor)
                    return combine("mul", factors)
        return combine("mul", [("number", "-1"), term])

    def reciprocal(term):
        if term[0] == "number":
            return ("number", str(1 / sp.Rational(term[1])))
        if term[0] == "mul":
            return combine("mul", [reciprocal(x) for x in term[1]])
        return ("pow", term, ("number", "-1"))

    def visit(n):
        if n.kind == "number":
            return ("number", str(_number(n.value)))
        if n.kind == "name":
            if n.value in env:
                value = env[n.value]
                if not isinstance(value, sp.Basic):
                    raise Unsupported("EqualComAss supports scalar values")
                return from_sympy(value)
            if n.value in _NAMES:
                return from_sympy(_NAMES[n.value])
            if n.value.startswith("%"):
                raise InvalidAnswer("Unknown percent constant")
            return ("symbol", n.value)
        if n.kind == "unary":
            a = visit(n.children[0])
            return a if n.value == "+" else negative(a)
        if n.kind == "binary":
            a, b = (visit(x) for x in n.children)
            return {"+": lambda: combine("add", [a, b]), "-": lambda: combine("add", [a, negative(b)]),
                    "*": lambda: combine("mul", [a, b]), "/": lambda: combine("mul", [a, reciprocal(b)]),
                    "^": lambda: ("pow", a, b), "**": lambda: ("pow", a, b)}[n.value]()
        if n.kind == "call":
            if n.value not in _STUDENT_FUNCTIONS:
                return from_sympy(evaluate(n, env, assumptions=assumptions))
            calculated = evaluate(n, env, assumptions=assumptions)
            if calculated.is_number:
                return from_sympy(calculated)
            if n.value == "sqrt" and len(n.children) == 1:
                return ("pow", visit(n.children[0]), ("number", "1/2"))
            return ("call", n.value, tuple(visit(x) for x in n.children))
        raise Unsupported("EqualComAss supports scalar expressions")

    return visit(node)
