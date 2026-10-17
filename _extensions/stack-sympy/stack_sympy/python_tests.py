"""Explicit Python-only answer tests, separate from native STACK semantics.

Only reviewed, registered functions run here. XML never supplies Python code,
module paths or imports. A defining matrix describes the target subspace.
"""
from __future__ import annotations

import sympy as sp

from .basis_helper import assess_basis
from .expressions import InvalidAnswer, MatrixValue, Unsupported, contains_decimal


def rational_matrix(value, tree=None):
    """Validate the exact rational input domain without assessing correctness."""
    if not isinstance(value, MatrixValue):
        raise InvalidAnswer("Python matrix tests require a matrix")
    if tree is not None and contains_decimal(tree):
        raise InvalidAnswer("Python matrix tests require exact fractions, not decimal literals")
    entries = [entry for row in value.args for entry in row.args]
    if any(not isinstance(entry, sp.Rational) for entry in entries):
        raise InvalidAnswer("Python matrix tests support exact rational entries only")
    if any(max(abs(int(entry.p)).bit_length(), int(entry.q).bit_length()) > 256 for entry in entries):
        raise InvalidAnswer("Python matrix test entries exceed the 256-bit rational bound")
    return sp.Matrix(value.shape[0], value.shape[1], entries)


def preflight_matrix_source(tree, env):
    """Bound each arithmetic step before the general evaluator constructs it.

    Python matrix tests intentionally accept integer/fraction arithmetic, not
    arbitrary scalar functions. Even nested powers cannot build huge integers
    before the final 256-bit check.
    """
    def checked(value):
        if not isinstance(value, sp.Rational):
            raise InvalidAnswer("Python matrix tests require exact rational arithmetic")
        if max(abs(int(value.p)).bit_length(), int(value.q).bit_length()) > 256:
            raise InvalidAnswer("Python matrix test arithmetic exceeds the 256-bit bound")
        return value

    def scalar(node):
        if node.kind == "number":
            if not node.value.isdigit():
                raise InvalidAnswer("Python matrix tests require exact fractions, not decimals")
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
                    raise InvalidAnswer("Python matrix powers require integer exponents from -100 to 100")
                # Operands are already <=256 bits; this operation constructs
                # at most 25,600 bits, then rejects before any enclosing power.
                value = left ** int(right)
            else:
                raise InvalidAnswer("Unsupported Python matrix arithmetic")
            return checked(value)
        raise InvalidAnswer("Python matrix tests accept integer/fraction arithmetic, not scalar functions")

    if tree.kind == "name":
        value = env.get(tree.value)
    elif tree.kind == "call" and tree.value == "matrix":
        if any(row.kind != "list" for row in tree.children):
            raise InvalidAnswer("Python matrix rows must be literal lists")
        value = MatrixValue(*[[scalar(entry) for entry in row.children] for row in tree.children])
    else:
        raise InvalidAnswer("Python matrix tests require a matrix constructor or exact author matrix")
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


def is_basis(student, teacher, options, student_ast=None, teacher_ast=None):
    space = options.strip() or "columns"
    if space not in {"nullspace", "columnspace", "rowspace", "columns", "rows"}:
        raise Unsupported("IsBasis options must be nullspace, columnspace, rowspace, columns or rows")
    try:
        reference = rational_matrix(teacher, teacher_ast)
    except InvalidAnswer as exc:
        raise Unsupported("Invalid IsBasis reference: " + str(exc)) from exc
    rank = reference.rank()
    axis = "rows" if space in {"rows", "rowspace"} else "columns"
    if space == "nullspace":
        dimension, ambient = reference.cols - rank, reference.cols
        belongs = lambda vector: reference * vector == sp.zeros(reference.rows, 1)
        space_name = "null space"
    elif space == "columnspace":
        dimension, ambient = rank, reference.rows
        belongs = lambda vector: reference.row_join(vector).rank() == rank
        space_name = "column space"
    elif space == "rowspace":
        dimension, ambient = rank, reference.cols
        belongs = lambda vector: reference.col_join(vector).rank() == rank
        space_name = "row space"
    else:
        # Backwards compatibility for questions which supplied a known basis.
        dimension = rank
        count = reference.cols if axis == "columns" else reference.rows
        if dimension != count:
            raise Unsupported("IsBasis reference vectors must be an independent, nonempty basis")
        ambient = reference.rows if axis == "columns" else reference.cols
        belongs = lambda vector: (reference.row_join(vector).rank() == dimension if axis == "columns"
                                  else reference.col_join(vector).rank() == dimension)
        space_name = "target space"
    if not dimension:
        raise Unsupported("The target space has an empty basis; empty matrix inputs are not yet supported")
    try:
        submitted = rational_matrix(student, student_ast)
    except InvalidAnswer as exc:
        return {"valid": False, "correct": False, "note": "IsBasis-invalid", "feedback": str(exc)}
    submitted_ambient = submitted.rows if axis == "columns" else submitted.cols
    result = assess_basis(
        submitted, axis=axis, target_dimension=int(dimension), name="answer",
        belongs=lambda vector: submitted_ambient == ambient and belongs(vector),
        space_name=space_name,
    )
    # IsBasis is a predicate. The normal true/false PRT branches award credit.
    # The helper's fractional diagnostic score does not become a PRT score.
    statuses = result["assessment"]["answer"][axis]
    submitted_count = submitted.cols if axis == "columns" else submitted.rows
    correct = submitted_count == dimension and all(status == "correct" for status in statuses)
    return {"valid": True, "correct": correct, "note": "IsBasis-T" if correct else "IsBasis-F",
            "feedback": result["feedback"], "assessment": result["assessment"]["answer"],
            "implementation": "python-extension"}


def matrix_property(student, teacher, options, student_ast=None, teacher_ast=None):
    """A small reviewed property vocabulary, not general matrix code in XML."""
    property_name = options.strip()
    if property_name not in {"integer_entries", "determinant", "identity"}:
        raise Unsupported("MatrixProperty options must be integer_entries, determinant or identity")
    if property_name == "determinant":
        if not isinstance(teacher, sp.Rational) or max(abs(int(teacher.p)).bit_length(), int(teacher.q).bit_length()) > 256:
            raise Unsupported("MatrixProperty determinant requires a bounded exact rational teacher")
        if teacher_ast is not None and contains_decimal(teacher_ast):
            raise Unsupported("MatrixProperty determinant teacher requires exact fraction syntax")
    elif teacher is not sp.true and teacher is not sp.false:
        raise Unsupported("MatrixProperty integer_entries/identity require true or false as teacher")
    try:
        matrix = rational_matrix(student, student_ast)
    except InvalidAnswer as exc:
        return {"valid": False, "correct": False, "note": "MatrixProperty-invalid", "feedback": str(exc)}
    if property_name == "determinant":
        if matrix.rows != matrix.cols:
            return {"valid": False, "correct": False, "note": "MatrixProperty-invalid",
                    "feedback": "A determinant requires a square matrix"}
        actual = matrix.det()
    elif property_name == "integer_entries":
        actual = sp.true if all(entry.q == 1 for entry in matrix) else sp.false
    else:
        actual = sp.true if matrix.rows == matrix.cols and matrix == sp.eye(matrix.rows) else sp.false
    correct = actual == teacher
    return {"valid": True, "correct": bool(correct), "note": "MatrixProperty-T" if correct else "MatrixProperty-F",
            "feedback": "", "implementation": "python-extension"}


PYTHON_TESTS = {"IsBasis": is_basis, "MatrixProperty": matrix_property}
