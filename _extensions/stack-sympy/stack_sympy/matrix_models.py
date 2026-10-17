"""Author-only input models for matrix-defined basis questions."""
from __future__ import annotations

import sympy as sp

from .expressions import InvalidAnswer, MatrixValue, Unsupported, contains_decimal


def rational_matrix(value, tree=None):
    """Validate the exact rational input domain without assessing correctness."""
    if not isinstance(value, MatrixValue):
        raise InvalidAnswer("Basis models require a matrix")
    if tree is not None and contains_decimal(tree):
        raise InvalidAnswer("Basis models require exact fractions, not decimal literals")
    entries = [entry for row in value.args for entry in row.args]
    if any(not isinstance(entry, sp.Rational) for entry in entries):
        raise InvalidAnswer("Basis models support exact rational entries only")
    if any(max(abs(int(entry.p)).bit_length(), int(entry.q).bit_length()) > 256 for entry in entries):
        raise InvalidAnswer("Basis model entries exceed the 256-bit rational bound")
    return sp.Matrix(value.shape[0], value.shape[1], entries)


def preflight_matrix_source(tree, env):
    """Bound each arithmetic step before the general evaluator constructs it.

    Basis models intentionally accept integer/fraction arithmetic, not
    arbitrary scalar functions. Even nested powers cannot build huge integers
    before the final 256-bit check.
    """
    def checked(value):
        if not isinstance(value, sp.Rational):
            raise InvalidAnswer("Basis models require exact rational arithmetic")
        if max(abs(int(value.p)).bit_length(), int(value.q).bit_length()) > 256:
            raise InvalidAnswer("Basis model arithmetic exceeds the 256-bit bound")
        return value

    def scalar(node):
        if node.kind == "number":
            if not node.value.isdigit():
                raise InvalidAnswer("Basis models require exact fractions, not decimals")
            return checked(sp.Integer(node.value))
        if node.kind == "name":
            return checked(env.get(node.value))
        if node.kind == "unary":
            value = scalar(node.children[0])
            return checked(-value if node.value == "-" else value)
        if node.kind == "binary":
            left, right = (scalar(child) for child in node.children)
            if node.value == "+":
                value = left + right
            elif node.value == "-":
                value = left - right
            elif node.value == "*":
                value = left * right
            elif node.value == "/":
                if right == 0:
                    raise InvalidAnswer("Division by zero")
                value = left / right
            elif node.value in {"^", "**"}:
                if right.q != 1 or not -100 <= right <= 100:
                    raise InvalidAnswer("Basis model powers require integer exponents from -100 to 100")
                # Operands are already <=256 bits; this operation constructs
                # at most 25,600 bits, then rejects before any enclosing power.
                value = left ** int(right)
            else:
                raise InvalidAnswer("Unsupported Python matrix arithmetic")
            return checked(value)
        raise InvalidAnswer("Basis models accept integer/fraction arithmetic, not scalar functions")

    if tree.kind == "name":
        value = env.get(tree.value)
    elif tree.kind == "call" and tree.value == "matrix":
        if any(row.kind != "list" for row in tree.children):
            raise InvalidAnswer("Basis model rows must be literal lists")
        value = MatrixValue(*[[scalar(entry) for entry in row.children] for row in tree.children])
    else:
        raise InvalidAnswer("Basis models require a matrix constructor or exact author matrix")
    rational_matrix(value, tree)


def basis_model(value, space):
    """Compute a model answer for an input, never a grading reference."""
    matrix = rational_matrix(value)
    if space == "nullspace":
        vectors = matrix.nullspace()
    elif space == "columnspace":
        vectors = matrix.columnspace()
    else:
        vectors = matrix.rowspace()
    if not vectors:
        raise Unsupported("The target space has an empty basis; empty matrix inputs are not yet supported")
    model = (sp.Matrix.vstack(*vectors) if space == "rowspace"
             else sp.Matrix.hstack(*vectors))
    return MatrixValue(*model.tolist())
