"""Vendored assess_basis from Erasmus-CTM/math-exercise; AGPL-3.0-or-later.

See ../vendor/basis-helper-provenance.json. The function body is unchanged.
"""
from sympy import Matrix, zeros


def assess_basis(matrix, *, axis, target_dimension, belongs, name, space_name="space"):
    """Assess a row- or column-basis submission without privileging vector order.

    ``belongs(vector)`` decides only whether a nonzero vector belongs to the
    target space.  This helper owns rank, dependence, scoring, assessment
    colors, and standard feedback so individual checkers do not duplicate them.
    """
    if axis not in ("rows", "columns"):
        raise ValueError("Basis assessment axis must be rows or columns")
    target_dimension = int(target_dimension)
    if target_dimension < 0:
        raise ValueError("Basis target dimension cannot be negative")
    if not callable(belongs):
        raise TypeError("Basis membership test must be callable")

    count = matrix.rows if axis == "rows" else matrix.cols
    singular = "row" if axis == "rows" else "column"
    vectors = [matrix[i, :] for i in range(count)] if axis == "rows" else [matrix[:, i] for i in range(count)]

    if target_dimension == 0:
        statuses = ["incorrect"] * count
        return {
            "score": 1.0 if count == 0 else 0.0,
            "show_score": False,
            "feedback": "" if count == 0 else f"The {space_name} is trivial, so its basis is empty. Remove every {singular}.",
            "assessment": {name: {axis: statuses}},
        }

    locally_valid = []
    valid_vectors = []
    for vector in vectors:
        zero = vector == zeros(*vector.shape)
        valid = (not zero) and bool(belongs(vector))
        locally_valid.append(valid)
        if valid:
            valid_vectors.append(vector)

    if valid_vectors:
        family = Matrix.vstack(*valid_vectors) if axis == "rows" else Matrix.hstack(*valid_vectors)
        rank = int(family.rank())
    else:
        rank = 0
    valid_count = len(valid_vectors)
    dependent = rank < valid_count
    statuses = [
        ("dependent" if dependent else "correct") if valid else "incorrect"
        for valid in locally_valid
    ]

    if count == 0:
        score = 0.0
    else:
        coverage = min(rank, target_dimension) / target_dimension
        validity = valid_count / count
        independence = rank / valid_count if valid_count else 0.0
        score = float(coverage * validity * independence)

    invalid_count = count - valid_count
    plural = singular + "s"
    if score >= 1.0 - 1e-9:
        feedback = ""
    elif count == 0:
        feedback = f"Add one or more basis {plural} for the {space_name}."
    elif invalid_count and dependent:
        feedback = (f"The red {plural} are zero or outside the {space_name}. "
                    f"The yellow {plural} belong to the {space_name}, but together they are linearly dependent. "
                    f"Remove or replace the red {plural}, choose an independent subset of the yellow {plural}, "
                    f"and check that the result spans the whole {space_name}.")
    elif invalid_count:
        feedback = f"Remove or replace the red {plural}; each is zero or outside the {space_name}."
        if rank < target_dimension:
            feedback += f" Then add independent {plural} until the family spans the whole {space_name}."
    elif dependent and rank == target_dimension:
        feedback = (f"Every yellow {singular} belongs to the {space_name}, but the family is linearly dependent. "
                    f"Remove one or more yellow {plural} until an independent basis remains.")
    elif dependent:
        feedback = (f"Every yellow {singular} belongs to the {space_name}, but the family is linearly dependent. "
                    f"Choose an independent subset, then add independent {plural} until it spans the whole {space_name}.")
    else:
        feedback = (f"The green {plural} are valid and independent. "
                    f"Add more independent {plural} until they span the whole {space_name}.")

    return {"score": score, "show_score": False, "feedback": feedback, "assessment": {name: {axis: statuses}}}
