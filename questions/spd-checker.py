"""Check symmetry and positive definiteness for exact rational matrices."""


def symmetric(A):
    return A.rows == A.cols and A == A.T


def positive_definite(A):
    if A.rows != A.cols:
        return False
    # x.T*A*x equals x.T*S*x, including when A is not symmetric.
    S = (A + A.T) / 2
    return all(S[:k, :k].det() > 0 for k in range(1, S.rows + 1))


def check_property(ansm, expected, property_test, explanation):
    if any(entry.is_Rational is not True for entry in ansm):
        return {"valid": False, "correct": False,
                "feedback": "Use integers or exact fractions in every cell."}
    correct = bool(property_test(ansm)) == bool(expected)
    return {"valid": True, "correct": correct,
            "feedback": "" if correct else explanation}


def is_symmetric(ansm, expected):
    return check_property(ansm, expected, symmetric,
                          "The symmetry condition does not match the expected result.")


def is_positive_definite(ansm, expected):
    return check_property(ansm, expected, positive_definite,
                          "The positive-definiteness condition does not match the expected result.")


def is_spd(ansm, expected):
    return check_property(ansm, expected,
                          lambda A: symmetric(A) and positive_definite(A),
                          "The symmetric-positive-definiteness condition does not match the expected result.")


CHECKERS = {"is_symmetric": is_symmetric,
            "is_positive_definite": is_positive_definite,
            "is_spd": is_spd}
