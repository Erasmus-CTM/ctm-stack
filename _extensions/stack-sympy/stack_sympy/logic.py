"""Bounded propositional logic and STACK's multiplicity-preserving equations."""
from itertools import product
import sympy as sp
from .expressions import Equation, Logical, Unsupported, is_logical

MAX_VARIABLES = 8
MAX_TERMS = 2048
MAX_DEGREE = 100


def _polynomial_shape(expr):
    """Bound expansion before Poly; never cancel a variable denominator."""
    if expr.is_Rational or expr == sp.I:
        return 0, 1
    if expr.is_Symbol:
        return 1, 1
    if expr.is_Add or expr.is_Mul:
        shapes = [_polynomial_shape(a) for a in expr.args]
        degree = max(d for d, _ in shapes) if expr.is_Add else sum(d for d, _ in shapes)
        terms = sum(t for _, t in shapes) if expr.is_Add else 1
        if expr.is_Mul:
            for _, size in shapes:
                terms *= size
                if terms > MAX_TERMS:
                    break
    elif expr.is_Pow and expr.exp.is_Integer and 0 <= expr.exp <= MAX_DEGREE:
        degree, terms = _polynomial_shape(expr.base)
        degree *= int(expr.exp)
        # Numeric reciprocal powers are legitimate rational coefficients.
        terms = min(MAX_TERMS + 1, terms ** int(expr.exp))
    elif expr.is_Pow and expr.base.is_Rational and expr.exp.is_Integer:
        return 0, 1
    else:
        raise Unsupported("Equations require polynomials with rational complex coefficients and numeric denominators")
    if degree > MAX_DEGREE or terms > MAX_TERMS:
        raise Unsupported("Polynomial equation exceeds degree or expansion bound")
    return degree, terms


def _residual(value):
    if isinstance(value, Equation):
        for side in value.args:
            _polynomial_shape(side)
        return sp.Add(value.args[0], sp.Mul(-1, value.args[1], evaluate=False), evaluate=False)
    if isinstance(value, Logical) and value.operator == "or":
        return sp.Mul(*[_residual(x) for x in value.operands], evaluate=False)
    raise Unsupported("Equation logic supports equations and disjunctions of equations")


def _has_equation(value):
    return isinstance(value, Equation) or isinstance(value, Logical) and any(_has_equation(x) for x in value.operands)


def _proposition(value):
    if value in (sp.true, sp.false) or isinstance(value, sp.Symbol):
        return value
    if isinstance(value, Logical):
        args = [_proposition(x) for x in value.operands]
        # STACK's xnor is associative parity equivalence, rather than
        # SymPy Equivalent's all-operands-equal interpretation for n > 2.
        return {"and": sp.And, "or": sp.Or, "not": sp.Not, "implies": sp.Implies,
                "xor": sp.Xor, "xnor": lambda a, b: sp.Not(sp.Xor(a, b))}[value.operator](*args)
    raise Unsupported("Boolean logic requires propositions, not arithmetic expressions")


def _release(expr):
    # SymPy expand does not always flatten nested evaluate=False Add nodes.
    return expr.func(*[_release(a) for a in expr.args]) if expr.args else expr


def validate_logic(value):
    """Validate each typed value independently before comparing candidates."""
    if len(value.free_symbols) > MAX_VARIABLES or sp.count_ops(value) > 350:
        raise Unsupported("Logical answer exceeds supported bounds")
    if _has_equation(value):
        residual = _residual(value)
        _polynomial_shape(residual)
        residual = _release(residual)
        symbols = sorted(residual.free_symbols, key=str)
        try:
            if symbols:
                poly = sp.Poly(residual, *symbols, domain=sp.QQ_I)
                if poly.total_degree() == 0:
                    return "boolean", sp.true if poly.is_zero else sp.false
            else:
                return "boolean", sp.true if residual == 0 else sp.false
        except (sp.PolynomialError, sp.CoercionFailed) as exc:
            raise Unsupported("Equation coefficients outside rational complex domain") from exc
        return "equation", residual
    return "boolean", _proposition(value)


def logical_equivalent(student, teacher):
    left_kind, left = validate_logic(student)
    right_kind, right = validate_logic(teacher)
    if left_kind != right_kind:
        return False
    symbols = sorted(left.free_symbols | right.free_symbols, key=str)
    if len(symbols) > MAX_VARIABLES:
        raise Unsupported("Logical comparison exceeds variable bound")
    if left_kind == "boolean":
        return all(left.xreplace(dict(zip(symbols, values))) == right.xreplace(dict(zip(symbols, values)))
                   for values in product((sp.false, sp.true), repeat=len(symbols)))
    if not symbols:
        return (sp.expand(left) == 0) == (sp.expand(right) == 0)
    try:
        a, b = (sp.Poly(x, *symbols, domain=sp.QQ_I) for x in (left, right))
    except (sp.PolynomialError, sp.CoercionFailed) as exc:
        raise Unsupported("Equation coefficients outside rational complex domain") from exc
    # Normalizing numeric content preserves symbolic factors and multiplicity.
    return a.monic() == b.monic()
