"""Conservative scalar rejection and bounded elementary-function proofs.

Like STACK assessment.mac, numerical evaluation can reject a candidate; it
cannot establish equivalence. Failed or singular probes are inconclusive.
"""
import sympy as sp
from .expressions import Unsupported

ELEMENTARY = (sp.sin, sp.cos, sp.tan, sp.sec, sp.csc, sp.cot,
              sp.sinh, sp.cosh, sp.tanh, sp.sech, sp.csch, sp.coth)
NEW_FUNCTIONS = ELEMENTARY[3:]


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
    difference = left - right
    if difference.has(*NEW_FUNCTIONS):
        _rewrite_budget(difference)
    try:
        for transform in (sp.cancel, sp.trigsimp, sp.simplify):
            if transform(difference) == 0:
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
