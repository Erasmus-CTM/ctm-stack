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
# A computation budget, separate from a checker's narrower mathematical domain.
MAX_RATIONAL_BITS = 16384
MAX_DIGITS = 100
MAX_COLLECTION_ITEMS = 32
MAX_COLLECTION_DEPTH = 6
MAX_COLLECTION_NODES = 128
MAX_MATRIX_ROWS = 16
MAX_MATRIX_COLS = 16
MAX_MATRIX_ENTRIES = 64
_LEX = re.compile(r"\s*(?:(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|(?P<name>%?[A-Za-z_][A-Za-z_0-9]*)|(?P<op>\*\*|\+\-|[=+*/^(),{}\[\]-]))", re.ASCII)
_NAMES = {"pi": sp.pi, "%pi": sp.pi, "Pi": sp.pi, "PI": sp.pi,
          "e": sp.E, "E": sp.E, "%e": sp.E,
          "i": sp.I, "I": sp.I, "%i": sp.I}
SCALAR_FUNCTIONS = {
    "sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "sec": sp.sec, "csc": sp.csc, "cot": sp.cot,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "sech": sp.sech, "csch": sp.csch, "coth": sp.coth,
    "exp": sp.exp, "log": sp.log, "abs": sp.Abs,
}
FUNCTION_ALIASES = {"cosec": "csc", "cosech": "csch", "ln": "log"}
_STUDENT_FUNCTIONS = frozenset(SCALAR_FUNCTIONS) | FUNCTION_ALIASES.keys() | {"gcd", "mod", "matrix"}
LOGIC_OPERATORS = {"and": "and", "or": "or", "not": "not",
                   "implies": "implies", "xor": "xor", "xnor": "xnor",
                   "nounand": "and", "nounor": "or", "nounnot": "not"}
LOGIC_PRECEDENCE = {"xor": 0, "xnor": 0, "implies": 1, "or": 2, "and": 4, "not": 5}
LOGIC_LATEX = {"and": r" \land ", "or": r" \lor ", "implies": r" \rightarrow ",
               "xor": r" \oplus ", "xnor": r" \leftrightarrow "}
AUTHOR_COLLECTION_FUNCTIONS = frozenset({"set", "setify", "listify", "union", "intersection", "setdifference", "member", "subsetp", "cardinality"})
AUTHOR_BASIS_FUNCTIONS = frozenset({"nullspace_basis", "columnspace_basis", "rowspace_basis"})
_AUTHOR_FUNCTIONS = _STUDENT_FUNCTIONS | AUTHOR_COLLECTION_FUNCTIONS | AUTHOR_BASIS_FUNCTIONS | {"diff", "expand", "factor", "ratsimp", "cancel", "ev", "float", "rand", "rand_with_step", "lcm", "num", "denom", "decimalplaces", "dispdp", "displaydp", "significantfigures", "dispsf"}


@dataclass(frozen=True)
class Node:
    kind: str
    value: str = ""
    children: tuple["Node", ...] = ()


def _immutable_member(value):
    return HeldList(*value) if isinstance(value, list) else value


class HeldList(sp.Basic):
    """Hashable list member inside a set; author Python lists remain available."""
    def __new__(cls, *items):
        validate_collection(list(items))
        return sp.Basic.__new__(cls, *(_immutable_member(x) for x in items))

    def _sympystr(self, printer):
        return "[" + ",".join(printer.doprint(x) for x in self.args) + "]"

    def _latex(self, printer):
        return r"\left[" + ", ".join(printer.doprint(x) for x in self.args) + r"\right]"


class HeldSet(sp.Basic):
    """Finite set syntax, retaining repetitions until answer-test dispatch.

    SymPy FiniteSet eagerly removes duplicates. STACK's Sets test needs the
    original entries to explain repetitions, even when the answer is correct.
    """
    def __new__(cls, *items):
        validate_collection(list(items))
        return sp.Basic.__new__(cls, *(_immutable_member(x) for x in items))

    def _sympystr(self, printer):
        return "{" + ",".join(printer.doprint(x) for x in self.args) + "}"

    def _latex(self, printer):
        return r"\left\{" + ", ".join(printer.doprint(x) for x in self.args) + r"\right\}"


class MatrixValue(sp.Basic):
    """A bounded rectangular matrix, deliberately distinct from nested lists.

    This is a value container, not SymPy's matrix arithmetic API. Each leaf is
    parsed and compared through the same scalar machinery as list entries.
    """
    def __new__(cls, *rows):
        if not rows or len(rows) > MAX_MATRIX_ROWS:
            raise InvalidAnswer(f"Matrices require 1-{MAX_MATRIX_ROWS} rows")
        if any(not isinstance(row, (list, HeldList)) for row in rows):
            raise InvalidAnswer("Matrix rows must be lists")
        rows = [tuple(collection_items(row)) for row in rows]
        columns = len(rows[0])
        if not 1 <= columns <= MAX_MATRIX_COLS:
            raise InvalidAnswer(f"Matrices require 1-{MAX_MATRIX_COLS} columns")
        if any(len(row) != columns for row in rows):
            raise InvalidAnswer("Matrix rows must have equal lengths")
        if len(rows) * columns > MAX_MATRIX_ENTRIES:
            raise InvalidAnswer(f"Matrices support at most {MAX_MATRIX_ENTRIES} entries")
        for row in rows:
            for entry in row:
                if not isinstance(entry, sp.Expr):
                    raise InvalidAnswer("Matrix entries must be scalar expressions")
                _finite(entry)
        return sp.Basic.__new__(cls, *(HeldList(*row) for row in rows))

    @property
    def shape(self):
        return len(self.args), len(self.args[0].args)

    def _sympystr(self, printer):
        return "matrix(" + ",".join(printer.doprint(row) for row in self.args) + ")"

    def _latex(self, printer):
        return r"\begin{pmatrix}" + r" \\ ".join(
            " & ".join(printer.doprint(x) for x in row.args) for row in self.args) + r"\end{pmatrix}"


def is_collection(value):
    return isinstance(value, (list, HeldList, HeldSet, MatrixValue))


def collection_kind(value):
    return "matrix" if isinstance(value, MatrixValue) else "set" if isinstance(value, HeldSet) else "list" if isinstance(value, (list, HeldList)) else "scalar"


def collection_items(value):
    return value.args if isinstance(value, (HeldList, HeldSet, MatrixValue)) else value


def validate_collection(value):
    """The public input/answer boundary: bounded finite scalar collection trees.

    Author lists used by rand/index remain available outside this boundary.
    """
    if not is_collection(value):
        return
    count = 0
    def visit(item, depth):
        nonlocal count
        count += 1
        if count > MAX_COLLECTION_NODES:
            raise Unsupported(f"Collection trees support at most {MAX_COLLECTION_NODES} nodes")
        if is_collection(item):
            if isinstance(item, MatrixValue) and depth != 1:
                raise Unsupported("Matrices nested in collections are unsupported")
            if depth > MAX_COLLECTION_DEPTH:
                raise Unsupported(f"Collections support at most {MAX_COLLECTION_DEPTH} levels")
            children = collection_items(item)
            if len(children) > MAX_COLLECTION_ITEMS:
                raise Unsupported(f"Collections support at most {MAX_COLLECTION_ITEMS} entries per container")
            for child in children:
                visit(child, depth + 1)
        elif not isinstance(item, sp.Expr):
            raise Unsupported("Collection leaves must be scalar expressions")
        else:
            _finite(item)
    visit(value, 1)


def symbolic_complex_log(node: Node) -> bool:
    """Declared boundary: symbolic complex logarithms need branch proofs."""
    if node.kind != "call" or node.value not in {"log", "ln"}:
        return False
    def names(tree):
        return ({tree.value} if tree.kind == "name" else set()).union(
            *(names(child) for child in tree.children))
    symbols = set().union(*(names(child) for child in node.children))
    return bool(symbols & {"i", "I", "%i"}) and bool(symbols - _NAMES.keys())


class Equation(sp.Basic):
    """An unevaluated equation; repeated roots and denominators remain visible."""
    def _sympystr(self, printer):
        return "(" + printer.doprint(self.args[0]) + ")=(" + printer.doprint(self.args[1]) + ")"

    def _latex(self, printer):
        return printer.doprint(self.args[0]) + " = " + printer.doprint(self.args[1])


class Logical(sp.Basic):
    """Held logic, analogous to STACK's nounand/nounor/nounnot.

    Do not use SymPy Or here: its constructor removes duplicates, which would
    erase equation-branch multiplicity before AlgEquiv can inspect it.
    """
    def __new__(cls, operator, *operands):
        return sp.Basic.__new__(cls, sp.Symbol(str(operator)), *operands)

    @property
    def operator(self):
        return str(self.args[0])

    @property
    def operands(self):
        return self.args[1:]

    @property
    def free_symbols(self):
        return set().union(*(x.free_symbols for x in self.operands))

    def _sympystr(self, printer):
        parts = ["(" + (str(x).lower() if x in (sp.true, sp.false) else printer.doprint(x)) + ")"
                 for x in self.operands]
        if self.operator == "not":
            return "nounnot " + parts[0]
        spelling = "noun" + self.operator if self.operator in {"and", "or"} else self.operator
        return (" " + spelling + " ").join(parts)

    def _latex(self, printer):
        parts = [r"\left(" + printer.doprint(x) + r"\right)" for x in self.operands]
        return r"\lnot " + parts[0] if self.operator == "not" else LOGIC_LATEX[self.operator].join(parts)


def is_logical(value):
    return isinstance(value, (Logical, Equation)) or value in (sp.true, sp.false)


def _tokens(source: str) -> list[tuple[str, str, int, int]]:
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_CHARS:
        raise InvalidAnswer("Empty or oversized expression")
    out = []
    pos = 0
    while pos < len(source):
        if source[pos:].isspace():
            break
        match = _LEX.match(source, pos)
        if match is None:
            position = pos + re.match(r"\s*", source[pos:], re.ASCII).end()
            character = source[position]
            raise InvalidAnswer(f"Unexpected character {character!r} (U+{ord(character):04X}) at position {position}")
        kind = match.lastgroup
        value = match.group(kind)
        if value == "+-":
            raise Unsupported("Plus/minus input requires explicit alternatives")
        if kind == "number" and len(value) > MAX_DIGITS:
            raise InvalidAnswer("Number too long")
        out.append((kind, value, match.start(kind), match.end(kind)))
        pos = match.end()
        if len(out) > MAX_TOKENS:
            raise InvalidAnswer("Too many tokens")
    out.append(("end", "", len(source), len(source)))
    return out


class _Parser:
    def __init__(self, source: str, insertstars: int = 0):
        if insertstars not in (0, 1):
            raise Unsupported(f"Unsupported insertstars mode {insertstars!r}")
        self.tokens = _tokens(source)
        self.pos = 0
        self.insertstars = insertstars

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
        kind, val = self.tokens[self.pos][:2]
        self.pos += 1
        if val in {"not", "nounnot"}:
            lhs = Node("logical", "not", (self.expression(5, depth + 1),))
        elif val in {"true", "false"}:
            lhs = Node("boolean", val)
        elif kind == "number":
            lhs = Node("number", val)
        elif kind == "name":
            if self.current == "(":
                if val.lower() not in _AUTHOR_FUNCTIONS:
                    raise InvalidAnswer(f"Function {val} is not allowed; use {val}*(...) for multiplication")
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
        elif val in {"[", "{"}:
            closing = "]" if val == "[" else "}"
            items = []
            if self.current != closing:
                while True:
                    items.append(self.expression(depth=depth + 1))
                    if self.current != ",":
                        break
                    self.take(",")
            self.take(closing)
            lhs = Node("list" if val == "[" else "set", children=tuple(items))
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
            # Mode 1 inserts stars only at unambiguous adjacent token
            # boundaries. Names remain whole (xy is one symbol), and an
            # unknown name followed by '(' is never guessed to be a product.
            previous = self.tokens[self.pos - 1]
            following = self.tokens[self.pos]
            implied = (following[1] not in LOGIC_OPERATORS and previous[3] == following[2]
                       and (previous[0] == "number" or previous[1] == ")")
                       and (following[0] == "name" or following[1] == "("
                            or (previous[1] == ")" and following[0] == "number")))
            bp = 20 if implied else {"xor": 0, "xnor": 0, "implies": 1,
                                     "or": 2, "nounor": 2, "and": 4, "nounand": 4,
                                     "=": 6, "+": 10, "-": 10, "*": 20, "/": 20, "^": 30, "**": 30}.get(op, -1)
            if bp < minimum:
                break
            if implied and not self.insertstars:
                raise InvalidAnswer("Missing * for multiplication (this input requires an explicit *)")
            if not implied:
                self.pos += 1
            rhs = self.expression(bp if op in ("^", "**") else bp + 1, depth + 1)
            if not implied and op in LOGIC_OPERATORS:
                lhs = Node("logical", LOGIC_OPERATORS[op], (lhs, rhs))
            elif not implied and op == "=":
                if lhs.kind == "equation" or rhs.kind == "equation":
                    raise Unsupported("Chained equations are unsupported")
                lhs = Node("equation", "=", (lhs, rhs))
            else:
                lhs = Node("binary", "*" if implied else op, (lhs, rhs))
        return lhs


def parse(text: str, *, insertstars: int = 0) -> Node:
    parser = _Parser(text, insertstars)
    node = parser.expression()
    if parser.tokens[parser.pos][0] != "end":
        raise InvalidAnswer("Unexpected trailing text")
    return node


def form_latex(node: Node, env: Mapping[str, Any] | None = None) -> str:
    """Print the submitted tree without SymPy's automatic term collection.

    The parser has no grouping node, so precedence and right-hand grouping
    determine the parentheses necessary to represent its exact operation tree.
    """
    env = env or {}

    def precedence(n):
        if n.kind == "logical":
            return LOGIC_PRECEDENCE[n.value]
        if n.kind == "equation":
            return 6
        if n.kind == "number" and "e" in n.value.lower():
            return 20  # Displayed as mantissa times ten to a power.
        if n.kind == "name" and n.value in env:
            value = env[n.value]
            if getattr(value, "is_Add", False):
                return 10
            if getattr(value, "could_extract_minus_sign", lambda: False)():
                return 25
            if getattr(value, "is_Mul", False):
                return 20
            if getattr(value, "is_Pow", False):
                return 30
        if n.kind == "unary":
            return 25
        if n.kind == "binary":
            return {"+": 10, "-": 10, "*": 20, "/": 20, "^": 30, "**": 30}[n.value]
        return 40

    def wrap(content):
        return r"\left(" + content + r"\right)"

    def show(n):
        if n.kind in {"list", "set"}:
            opening, closing = ((r"\left[", r"\right]") if n.kind == "list"
                                else (r"\left\{", r"\right\}"))
            return opening + ", ".join(show(c) for c in n.children) + closing
        if n.kind == "boolean":
            return r"\mathrm{" + n.value + "}"
        if n.kind == "equation":
            return show(n.children[0]) + " = " + show(n.children[1])
        if n.kind == "logical":
            if n.value == "not":
                return r"\lnot " + wrap(show(n.children[0]))
            parts = [wrap(show(c)) if precedence(c) < precedence(n)
                     or i > 0 and precedence(c) == precedence(n) else show(c)
                     for i, c in enumerate(n.children)]
            return LOGIC_LATEX[n.value].join(parts)
        if n.kind == "number":
            if "e" in n.value.lower():
                coefficient, exponent = re.split("[eE]", n.value)
                return coefficient + r" \times 10^{" + str(int(exponent)) + "}"
            return n.value
        if n.kind == "name":
            if n.value in env:
                return sp.latex(env[n.value])
            return sp.latex(_NAMES[n.value] if n.value in _NAMES else sp.Symbol(n.value))
        if n.kind == "unary":
            child = n.children[0]
            rendered = show(child)
            return n.value + (wrap(rendered) if precedence(child) <= 25 else rendered)
        if n.kind == "call":
            if n.value == "matrix":
                return r"\begin{pmatrix}" + r" \\ ".join(
                    " & ".join(show(c) for c in row.children) for row in n.children) + r"\end{pmatrix}"
            name = "\\" + n.value if n.value in {"sin", "cos", "tan", "exp", "log", "ln", "gcd"} else r"\operatorname{" + n.value + "}"
            if n.value == "sqrt" and len(n.children) == 1:
                return r"\sqrt{" + show(n.children[0]) + "}"
            return name + wrap(", ".join(show(c) for c in n.children))
        if n.kind != "binary":
            raise Unsupported("Preview supports scalar expressions")
        left, right = n.children
        op = n.value
        a, b = show(left), show(right)
        if op in {"^", "**"}:
            if precedence(left) <= 30:
                a = wrap(a)
            return a + "^{" + b + "}"
        if op == "/":
            return r"\frac{" + a + "}{" + b + "}"
        if precedence(left) < precedence(n):
            a = wrap(a)
        if (precedence(right) < precedence(n) or (op == "-" and precedence(right) == 10)
                or (op in {"+", "-", "*"} and precedence(right) == 25)
                or (op == "*" and right.kind == "binary" and right.value == "/")):
            b = wrap(b)
        if op == "*":
            # A numeric coefficient next to a symbol reads naturally as 8x.
            separator = ("" if left.kind == "number" and right.kind in {"name", "call"}
                         and not (right.kind == "name" and right.value in env)
                         else r" \cdot ")
            return a + separator + b
        return a + (" + " if op == "+" else " - ") + b

    if not isinstance(node, Node):
        raise Unsupported("Preview requires a parsed expression")
    return show(node)


def _finite(value: Any):
    if is_collection(value):
        for item in collection_items(value):
            _finite(item)
    elif isinstance(value, sp.Basic):
        if value.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
            raise InvalidAnswer("Non-finite value")
        if any(max(abs(int(number.p)).bit_length(), int(number.q).bit_length()) > MAX_RATIONAL_BITS
               for number in value.atoms(sp.Rational)):
            raise InvalidAnswer(f"Exact arithmetic exceeds the {MAX_RATIONAL_BITS}-bit computation bound")
        if (value.is_Add or value.is_Mul) and _rational_growth_bits(value) > MAX_RATIONAL_BITS:
            raise InvalidAnswer(f"Exact arithmetic exceeds the {MAX_RATIONAL_BITS}-bit computation bound")
    return value


def _rational_growth_bits(value):
    """Conservative size estimate, including arithmetic held for form checks.

    Equations release held nodes later; inspecting only already-evaluated
    Rational atoms would let nested powers bypass the early allocation guard.
    """
    if isinstance(value, sp.Rational):
        return max((abs(int(part)).bit_length() if abs(part) > 1 else 0)
                   for part in (value.p, value.q))
    if value.is_Pow:
        return _power_growth_bits(_rational_growth_bits(value.base), value.exp)
    sizes = [_rational_growth_bits(arg) for arg in value.args]
    return sum(sizes) if value.is_Add or value.is_Mul else max(sizes, default=0)


def _power_growth_bits(base_bits, exponent):
    if isinstance(exponent, sp.Rational):
        # Bound the numerator power before a possible root extraction.
        return base_bits * abs(int(exponent.p))
    if exponent.is_number and exponent.is_real:
        # Held arithmetic such as 10*10 is not a Rational instance yet.
        return base_bits * int(sp.ceiling(abs(sp.N(exponent, 16))))
    return base_bits


def _bounded_power(base, exponent):
    """Reject oversized exact powers before SymPy allocates their integers.

    Rational powers may compute the numerator power before extracting a root,
    so bound that intermediate too. Zero and unit bases never grow.
    """
    if _power_growth_bits(_rational_growth_bits(base), exponent) > MAX_RATIONAL_BITS:
        raise InvalidAnswer(f"Exact power exceeds the {MAX_RATIONAL_BITS}-bit computation bound")


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


def _polynomial_gcd(left, right):
    """Keep polynomial GCD bounded and retain numeric coefficient content."""
    from .logic import MAX_VARIABLES, _polynomial_shape
    if any(not isinstance(x, sp.Expr) for x in (left, right)):
        raise InvalidAnswer("gcd requires scalar arguments")
    symbols = sorted(left.free_symbols | right.free_symbols, key=str)
    if len(symbols) > MAX_VARIABLES:
        raise Unsupported("gcd exceeds the polynomial variable bound")
    for value in (left, right):
        _polynomial_shape(value)
        try:
            if symbols:
                sp.Poly(value, *symbols, domain=sp.QQ)
            elif value.is_Rational is not True:
                raise Unsupported("gcd requires rational polynomial coefficients")
        except (sp.PolynomialError, sp.CoercionFailed) as exc:
            raise Unsupported("gcd requires rational polynomial coefficients") from exc
    # Poly(..., domain=QQ).gcd would make the result monic and lose integer
    # content, e.g. gcd(2*x+2, 4*x+4) must be 2*x+2, as in Maxima.
    return sp.gcd(left, right)


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


def contains_decimal(node: Node):
    return (node.kind == "number" and ("." in node.value or "e" in node.value.lower())
            or any(contains_decimal(child) for child in node.children))


def decimal_set(node: Node):
    """Decimals below a set need native float provenance we do not hold."""
    return (node.kind == "set" and contains_decimal(node)
            or any(decimal_set(child) for child in node.children))


def transformed_decimal_collection(node: Node):
    """Only literal constant arithmetic carries per-leaf binary64 provenance."""
    if not contains_decimal(node):
        return False
    if node.kind in {"list", "set"} or node.kind == "call" and node.value == "matrix":
        from .equivalence import constant_float_equivalent
        return any(transformed_decimal_collection(child) if child.kind in {"list", "set"} or child.kind == "call" and child.value == "matrix"
                   else contains_decimal(child) and constant_float_equivalent(child, child) is None
                   for child in node.children)
    def collection(tree):
        return tree.kind in {"list", "set"} or tree.kind == "call" and tree.value == "matrix" or any(collection(child) for child in tree.children)
    return collection(node)


def evaluate(node_or_string: Node | str, env: Mapping[str, Any] | None = None, *, rng: random.Random | None = None,
             assumptions: Mapping[str, bool] | None = None, student: bool = False, simplify: bool = True):
    """Evaluate a parsed expression with a small explicit function whitelist.

    Student calls are limited to elementary scalar functions; random values,
    CAS transformations and indexing are author-only. Student collections
    have bounded depth, size, and scalar leaves.
    """
    node = parse(node_or_string) if isinstance(node_or_string, str) else node_or_string
    if not isinstance(node, Node):
        raise Unsupported("Expected a parsed expression")
    if decimal_set(node):
        error = InvalidAnswer if student else Unsupported
        raise error("Decimal literals inside sets are unsupported; use exact fractions")
    env = {} if env is None else env
    assumptions = assumptions or {}
    rng = rng if rng is not None else random.Random()

    def visit(n: Node, depth=0):
        if depth > MAX_DEPTH:
            raise InvalidAnswer("Expression nested too deeply")
        if n.kind == "boolean":
            return sp.true if n.value == "true" else sp.false
        if n.kind == "logical":
            operands = [visit(c, depth + 1) for c in n.children]
            if any(not (is_logical(x) or isinstance(x, sp.Symbol)) for x in operands):
                raise InvalidAnswer("Logical operators require propositions or equations")
            return Logical(n.value, *operands)
        if n.kind == "equation":
            operands = [evaluate(c, env, rng=rng, assumptions=assumptions,
                                 student=student, simplify=False) for c in n.children]
            if any(not isinstance(x, sp.Expr) for x in operands):
                raise InvalidAnswer("Equation sides must be scalar expressions")
            return Equation(*operands)
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
                return _finite(value)
            if n.value in {"simp", "true", "false"}:
                raise InvalidAnswer("Boolean flags are not scalar expressions")
            return sp.Symbol(n.value, **{k: True for k in ("real", "positive") if assumptions.get(k)})
        if n.kind in {"list", "set"}:
            items = [visit(c, depth + 1) for c in n.children]
            if any(isinstance(item, MatrixValue) for item in items):
                raise Unsupported("Matrices nested in collections are unsupported")
            if n.kind == "set" or student:
                validate_collection(items)
            return HeldSet(*items) if n.kind == "set" else items
        if n.kind == "index":
            if student:
                raise InvalidAnswer("Only scalar student answers are supported")
            seq = visit(n.children[0], depth + 1)
            idx = _integer(visit(n.children[1], depth + 1), lower=1)
            if not isinstance(seq, (list, HeldList)) or idx > len(collection_items(seq)):
                raise Unsupported("Index outside list")
            return collection_items(seq)[idx - 1]
        if n.kind == "unary":
            value = visit(n.children[0], depth + 1)
            if not isinstance(value, sp.Expr):
                raise InvalidAnswer("Arithmetic requires scalar expressions")
            return value if n.value == "+" else -value
        if n.kind == "binary":
            a, b = (visit(c, depth + 1) for c in n.children)
            if not isinstance(a, sp.Expr) or not isinstance(b, sp.Expr):
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
                _bounded_power(a, b)
                result = sp.Pow(a, b, evaluate=simplify)
            return _finite(result)
        if n.kind == "call":
            name = n.value
            if student and name not in _STUDENT_FUNCTIONS:
                raise InvalidAnswer(f"Function {name} is not allowed in student input")
            if symbolic_complex_log(n):
                raise Unsupported("Symbolic complex logarithms require branch-aware proof")
            if name == "matrix":
                try:
                    return MatrixValue(*(visit(c, depth + 1) for c in n.children))
                except Unsupported as exc:
                    raise InvalidAnswer(str(exc)) from exc
            if name in AUTHOR_BASIS_FUNCTIONS:
                if not simplify:
                    raise Unsupported("Basis model helpers require simplification")
                if len(n.children) != 1:
                    raise Unsupported(f"{name} requires one defining matrix")
                from .matrix_models import basis_model, preflight_matrix_source
                preflight_matrix_source(n.children[0], env)
                return basis_model(visit(n.children[0], depth + 1), name.removesuffix("_basis"))
            if name in AUTHOR_COLLECTION_FUNCTIONS:
                if not simplify:
                    raise Unsupported("Finite collection helpers require simplification")
                def decimal(tree):
                    return (tree.kind == "number" and ("." in tree.value or "e" in tree.value.lower())) or any(decimal(c) for c in tree.children)
                if decimal(n):
                    raise Unsupported("Finite collection helpers require exact fractions rather than decimal literals")
                from .collection_ops import collection_operation
                return collection_operation(name, [visit(c, depth + 1) for c in n.children])
            if name == "ev":
                if len(n.children) not in (1, 2) or (
                        len(n.children) == 2 and n.children[1] != Node("name", "simp")):
                    raise Unsupported("Only ev(expr) and ev(expr,simp) are supported")
                value = visit(n.children[0], depth + 1)
                if isinstance(value, MatrixValue):
                    raise Unsupported("Matrix transformations are outside the supported subset")
                return value
            args = [visit(c, depth + 1) for c in n.children]
            if any(isinstance(value, MatrixValue) for value in args):
                raise Unsupported("Matrix operations are outside the supported subset")
            if name in {"gcd", "mod"}:
                if len(args) != 2:
                    raise Unsupported(f"{name} requires two arguments")
                if name == "gcd":
                    return _polynomial_gcd(*args)
                if any(not isinstance(x, sp.Expr) or x.is_real is False for x in args):
                    raise InvalidAnswer("mod requires real scalar arguments")
                if sum(sp.count_ops(x) for x in args) > 100:
                    raise Unsupported("mod exceeds the expression bound")
                # Maxima explicitly defines mod(x,0)=x. SymPy Mod raises.
                return args[0] if args[1] == 0 else _finite(sp.Mod(*args))
            if name in {"num", "denom"}:
                if len(args) != 1 or not isinstance(args[0], sp.Expr):
                    raise Unsupported(f"{name} requires one scalar argument")
                # Extract the top-level written fraction, without combining
                # sums or cancelling factors before a gcd form check.
                return sp.fraction(args[0])[name == "denom"]
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
            if name == "lcm":
                if len(args) != 2 or any(not isinstance(x, sp.Basic) or x.is_Integer is not True for x in args):
                    raise Unsupported("lcm requires two integer arguments")
                return sp.Integer(sp.ilcm(*args))
            if name in {"decimalplaces", "dispdp", "displaydp", "significantfigures", "dispsf"}:
                if len(args) != 2:
                    raise Unsupported(f"{name} takes two arguments")
                return _decimal_round(args[0], _integer(args[1], lower=0, upper=100), significant=name in {"significantfigures", "dispsf"})
            if name == "diff":
                if len(args) not in (2, 3) or not isinstance(args[1], sp.Symbol):
                    raise Unsupported("diff expects expression, variable, optional order")
                return sp.diff(args[0], args[1], *([_integer(args[2], lower=0, upper=10)] if len(args) == 3 else []))
            name = FUNCTION_ALIASES.get(name, name)
            funcs = {**SCALAR_FUNCTIONS, "expand": sp.expand, "factor": sp.factor,
                     "ratsimp": lambda x: sp.together(sp.cancel(x)), "cancel": sp.cancel,
                     "float": lambda x: sp.N(x, 17)}
            if name not in funcs or len(args) != 1:
                raise Unsupported(f"Unsupported call to {name}")
            if not isinstance(args[0], sp.Expr):
                raise InvalidAnswer("Functions require scalar arguments")
            return _finite(funcs[name](args[0]))
        raise Unsupported("Unknown expression node")

    result = _finite(visit(node))
    if is_collection(result) and transformed_decimal_collection(node):
        error = InvalidAnswer if student else Unsupported
        raise error("Nonliteral decimal collections lose literal precision; use exact fractions")
    if student:
        validate_collection(result)
    return result


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

    Flatten and sort sums/products; preserve STACK's held UNARY_RECIP operand.
    In particular, neither reciprocals of products nor identity factors are
    simplified. Named author values are inserted structurally.
    """
    node = parse(node) if isinstance(node, str) else node
    env = env or {}

    def from_sympy(value):
        if is_collection(value):
            kind = collection_kind(value)
            terms = [from_sympy(x) for x in collection_items(value)]
            return (kind, tuple(sorted(terms, key=repr) if kind == "set" else terms))
        if value.is_Number:
            return ("number", str(sp.Rational(str(value))))
        if value.is_Symbol:
            return ("symbol", str(value))
        if value.is_Add:
            return combine("add", [from_sympy(x) for x in value.args])
        if value.is_Mul:
            return combine("mul", [from_sympy(x) for x in value.args])
        if value.is_Pow:
            if value.exp == sp.Rational(1, 2):
                return ("call", "sqrt", (from_sympy(value.base),))
            return ("pow", from_sympy(value.base), from_sympy(value.exp))
        if value.func == sp.exp:
            return ("pow", from_sympy(sp.E), from_sympy(value.args[0]))
        return ("call", value.func.__name__.lower(), tuple(from_sympy(x) for x in value.args))

    def combine(op, terms):
        flattened = []
        for term in terms:
            if term[0] == op:
                flattened.extend(term[1])
            else:
                flattened.append(term)
        # STACK's noun arithmetic compares written numeric operations too:
        # (8/15)*8 differs from its reduced rational, and 1/2 from 3/6.
        # Flatten commutative operations without collecting the numbers.
        return (op, tuple(sorted(flattened, key=repr))) if len(flattened) > 1 else flattened[0]

    def negative(term):
        if term[0] == "number":
            return ("number", str(-sp.Rational(term[1])))
        if term[0] == "mul":
            factors = list(term[1])
            for i, factor in enumerate(factors):
                if factor[0] == "number":
                    flipped = negative(factor)
                    if flipped == ("number", "1"):
                        factors.pop(i)
                        return combine("mul", factors)
                    factors[i] = flipped
                    return combine("mul", factors)
        return combine("mul", [("number", "-1"), term])

    def reciprocal(term):
        # noun_simp.mac noun_arith_full keeps UNARY_RECIP as a noun:
        # recip(a*b) is not recip(a)*recip(b), nor is recip(-a) -recip(a).
        return ("reciprocal", term)

    def visit(n):
        if n.kind in {"list", "set"}:
            terms = [visit(x) for x in n.children]
            return (n.kind, tuple(sorted(terms, key=repr) if n.kind == "set" else terms))
        if n.kind == "number":
            if "." in n.value or "e" in n.value.lower():
                return ("decimal", n.value)
            return ("number", str(_number(n.value)))
        if n.kind == "name":
            if n.value in env:
                value = env[n.value]
                if not isinstance(value, sp.Basic) and not is_collection(value):
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
            if n.value == "/":
                numerator, denominator = n.children
                a, b = visit(numerator), visit(denominator)
                # Maxima retains reduced integer fractions as rational atoms.
                # Thus (1/2)*x has an explicit rational coefficient while x/2
                # has UNARY_RECIP(2), without a written numerator 1.
                if (a[0] == b[0] == "number"
                        and sp.Rational(a[1]).is_Integer and sp.Rational(b[1]).is_Integer
                        and sp.igcd(int(sp.Rational(a[1])), int(sp.Rational(b[1]))) == 1):
                    return ("number", str(sp.Rational(a[1]) / sp.Rational(b[1])))
                # Chained quotients keep separate held reciprocal operands.
                # Combining them requires STACK's optional recipMul rule.
                return combine("mul", [a, reciprocal(b)])
            a, b = (visit(x) for x in n.children)
            return {"+": lambda: combine("add", [a, b]), "-": lambda: combine("add", [a, negative(b)]),
                    "*": lambda: combine("mul", [a, b]), "/": lambda: combine("mul", [a, reciprocal(b)]),
                    "^": lambda: ("pow", a, b), "**": lambda: ("pow", a, b)}[n.value]()
        if n.kind == "call":
            if n.value == "matrix":
                return ("matrix", tuple(visit(row) for row in n.children))
            if n.value not in _STUDENT_FUNCTIONS:
                return from_sympy(evaluate(n, env, assumptions=assumptions))
            if n.value == "sqrt" and len(n.children) == 1:
                return ("call", "sqrt", (visit(n.children[0]),))
            # Maxima rewrites exp(x) to %e^x before noun arithmetic.
            if n.value == "exp" and len(n.children) == 1:
                return ("pow", from_sympy(sp.E), visit(n.children[0]))
            return ("call", FUNCTION_ALIASES.get(n.value, n.value), tuple(visit(x) for x in n.children))
        raise Unsupported("EqualComAss supports scalar expressions")

    return visit(node)
