"""Check Hermitian symmetry and positivity for exact real or complex matrices."""


def hermitian(A):
    return A.rows == A.cols and A == A.H


def positive_definite(A):
    if A.rows != A.cols:
        return False
    # Re(z.H*A*z) equals z.H*H*z for real or complex matrices.
    H = (A + A.H) / 2
    return all(H[:k, :k].det() > 0 for k in range(1, H.rows + 1))


def check_property(ansm, expected, property_test, explanation):
    if any(part.is_Rational is not True
           for entry in ansm for part in entry.as_real_imag()):
        return {"valid": False, "correct": False,
                "feedback": "Use integers or exact fractions for the real and imaginary parts."}
    correct = bool(property_test(ansm)) == bool(expected)
    return {"valid": True, "correct": correct,
            "feedback": "" if correct else explanation}


def is_hermitian(ansm, expected):
    return check_property(ansm, expected, hermitian,
                          "The Hermitian-symmetry condition does not match the expected result.")


def is_positive_definite(ansm, expected):
    return check_property(ansm, expected, positive_definite,
                          "The positive-definiteness condition does not match the expected result.")


def is_hpd(ansm, expected):
    return check_property(ansm, expected,
                          lambda A: hermitian(A) and positive_definite(A),
                          "The Hermitian-positive-definiteness condition does not match the expected result.")


CHECKERS = {"is_hermitian": is_hermitian,
            "is_positive_definite": is_positive_definite,
            "is_hpd": is_hpd}
