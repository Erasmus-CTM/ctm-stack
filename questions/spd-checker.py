"""Check symmetric positive definiteness for exact rational matrices."""


def is_spd(ansm, expected):
    if any(entry.is_Rational is not True for entry in ansm):
        return {"valid": False, "correct": False,
                "feedback": "Use integers or exact fractions in every cell."}

    if ansm.rows != ansm.cols or ansm != ansm.T:
        positive = False
    else:
        # Sylvester's criterion for real symmetric matrices.
        positive = all(ansm[:k, :k].det() > 0 for k in range(1, ansm.rows + 1))

    correct = bool(positive) == bool(expected)
    return {"valid": True, "correct": correct,
            "feedback": "" if correct else
                "The matrix must be symmetric, with every leading principal determinant positive."}


CHECKERS = {"is_spd": is_spd}
