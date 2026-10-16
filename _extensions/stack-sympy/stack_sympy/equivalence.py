"""Conservative scalar rejection and bounded elementary-function proofs.

Like STACK assessment.mac, numerical evaluation can reject a candidate; it
cannot establish equivalence. Failed or singular probes are inconclusive.
"""
import sympy as sp
from fractions import Fraction
import math
from .expressions import Unsupported

ELEMENTARY = (sp.sin, sp.cos, sp.tan, sp.sec, sp.csc, sp.cot,
              sp.sinh, sp.cosh, sp.tanh, sp.sech, sp.csch, sp.coth)
NEW_FUNCTIONS = ELEMENTARY[3:]


def constant_float_equivalent(left, right):
    """STACK binary64 compatibility for literal rational arithmetic only.

    Keep exact fractions until an operation contains a decimal/scientific
    literal. Compare finite binary64 values exactly, with no tolerance. This
    deliberately does not change the parser, symbolic coefficients, functions,
    frozen author values, or the numerical answer tests.
    """
    has_float = False

    def visit(node):
        nonlocal has_float
        if node.kind == "number":
            if "." in node.value or "e" in node.value.lower():
                has_float = True
                return float(node.value)
            return Fraction(node.value)
        if node.kind == "unary":
            value = visit(node.children[0])
            return -value if node.value == "-" else value
        if node.kind != "binary":
            raise ValueError("Outside constant arithmetic")
        a, b = (visit(child) for child in node.children)
        if node.value == "+":
            return a + b
        if node.value == "-":
            return a - b
        if node.value == "*":
            return a * b
        if node.value == "/":
            return a / b
        # Transcendental and fractional powers retain the symbolic proof path.
        if not isinstance(b, Fraction) or b.denominator != 1 or abs(b) > 100:
            raise ValueError("Outside integer powers")
        return a ** int(b)

    try:
        a, b = visit(left), visit(right)
        if not has_float:
            return None
        a, b = float(a), float(b)
        return a == b if math.isfinite(a) and math.isfinite(b) else None
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def _stack_reciprocal_sqrt(expr):
    """The explicit STACK convention sqrt(1/x) = 1/sqrt(x).

    Installation docs require this symbolic equivalence despite the branch
    debate. Restrict the convention to reciprocal roots of a symbol; numeric
    negative/complex roots and other root/power rewrites keep principal branches.
    """
    if (expr.is_Pow and expr.exp == sp.S.Half and expr.base.is_Pow
            and expr.base.exp == -1 and expr.base.base.is_Symbol):
        return sp.Pow(expr.base.base, -sp.S.Half)
    return expr


def numerically_distinct(left, right):
    """A deterministic, rejection-only screen with two precision levels.

    Keep STACK's 1e-4 margin, scaled to both operands. Use independent
    high-precision evaluations, skip nonreal/nonfinite/ill-conditioned probes,
    and respect positive/real symbol assumptions. No random state is consumed.
    """
    symbols = sorted(left.free_symbols | right.free_symbols, key=str)
    if len(symbols) > 8 or sp.count_ops(left) + sp.count_ops(right) > 180:
        return False
    probes = ([sp.Integer(k + 2) for k in range(len(symbols))],
              [(sp.sqrt(2) ** (k + 1) + (k + 1) * sp.pi) / 4 for k in range(len(symbols))])
    for values in probes:
        substitution = dict(zip(symbols, values))
        try:
            a, b = left.xreplace(substitution), right.xreplace(substitution)
            results = []
            for digits in (40, 70):
                x, y = (v.evalf(digits, maxn=150, strict=True) for v in (a, b))
                if any(v.is_real is not True or v.is_finite is not True for v in (x, y)):
                    break
                # Bound magnitudes and require a very clear, stable separation.
                if max(abs(x), abs(y)) > sp.Integer(10) ** 100:
                    break
                results.append(abs(x-y) / max(sp.Integer(1), abs(x), abs(y)))
            if len(results) == 2 and all(r > sp.Rational(1, 10000) for r in results):
                if abs(results[0] - results[1]) < sp.Rational(1, 10**25):
                    return True
        except (ValueError, TypeError, ArithmeticError, NotImplementedError):
            continue
    return False


def _rewrite_budget(expr):
    """Bound distributive growth before cancel/trigsimp expands a candidate."""
    sizes = [_rewrite_budget(a) for a in expr.args]
    if expr.is_Add:
        size = sum(sizes)
    elif expr.is_Mul:
        size = 1
        for child in sizes:
            size *= child
            if size > 2048:
                break
    elif expr.is_Pow and expr.exp.is_Integer:
        size = sizes[0] ** min(abs(int(expr.exp)), 101)
    else:
        size = 1
    if size > 2048:
        raise Unsupported("Elementary equivalence exceeds expansion bound")
    return size


def elementary_equivalent(left, right):
    if left == right:
        return True
    if numerically_distinct(left, right):
        return False
    left, right = (_stack_reciprocal_sqrt(value) for value in (left, right))
    if left == right:
        return True
    difference = left - right
    if difference.has(*NEW_FUNCTIONS):
        _rewrite_budget(difference)
    try:
        for transform in (sp.cancel, sp.trigsimp, sp.simplify):
            if transform(difference) == 0:
                return True
        # For nonzero bases, principal powers are exp(exponent*log(base)).
        # This proves x^log(y) = y^log(x) without expanding a logarithm of a
        # product or denesting a power. STACK also exponentializes its residual.
        if (sp.count_ops(difference) <= 180 and any(
                p.exp.has(sp.log) for p in difference.atoms(sp.Pow))):
            rewritten = difference.rewrite(sp.exp)
            if sp.count_ops(rewritten) <= 700:
                _rewrite_budget(rewritten)
                if sp.cancel(rewritten) == 0:
                    return True
        # STACK assessment.mac calls rectform when a difference contains i.
        # Start with bounded numeric constants: expand_complex respects the
        # principal branches, without introducing re(x)/im(x) or assumptions
        # about symbolic roots. Never use force=True power denesting.
        if (difference.is_number is True and difference.has(sp.I)
                and not difference.has(sp.log) and sp.count_ops(difference) <= 120
                and all(p.exp.is_Rational and abs(p.exp.p) <= 100 and p.exp.q <= 30
                        for p in difference.atoms(sp.Pow))):
            try:
                _rewrite_budget(difference)
                rectangular = sp.expand_complex(difference)
                if sp.count_ops(rectangular) <= 300 and sp.simplify(rectangular) == 0:
                    return True
            except Unsupported:
                pass  # A skipped optional proof does not enlarge the contract.
        if difference.has(*ELEMENTARY):
            if sp.count_ops(difference) > 180:
                raise Unsupported("Elementary equivalence exceeds rewrite bound")
            # Explicit exponentialization mirrors STACK, without force=True
            # logarithm or power rewrites that can change complex branches.
            rewritten = difference.rewrite(sp.exp)
            if sp.count_ops(rewritten) > 700:
                raise Unsupported("Elementary equivalence exceeds rewrite bound")
            _rewrite_budget(rewritten)
            if sp.cancel(rewritten) == 0:
                return True
        if difference.has(*NEW_FUNCTIONS):
            raise Unsupported("Elementary equivalence is inconclusive")
        return False
    except (TypeError, ValueError, ZeroDivisionError, NotImplementedError) as exc:
        if isinstance(exc, Unsupported):
            raise
        return False
