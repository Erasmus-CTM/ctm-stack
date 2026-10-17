import unittest
import sympy as sp

from stack_sympy import Unsupported, answer_test


class AssessmentTest(unittest.TestCase):
    def test_symbolic_exact_and_non_equiv(self):
        self.assertTrue(answer_test("AlgEquiv", "(x+1)^2", "x^2+2*x+1")["correct"])
        self.assertTrue(answer_test("AlgEquiv", "(x^2-1)/(x-1)", "x+1")["correct"])
        self.assertTrue(answer_test("AlgEquiv", "sin(x)^2+cos(x)^2", "1")["correct"])
        self.assertFalse(answer_test("AlgEquiv", "sin(x)", "x")["correct"])
        self.assertFalse(answer_test("AlgEquiv", "x^2+1", "x^2+2")["correct"])
        self.assertFalse(answer_test("AlgEquiv", "sqrt(x^2)", "x")["correct"])
        self.assertTrue(answer_test("AlgEquiv", "sqrt(x^2)", "x", assumptions={"positive": True})["correct"])

    def test_equalcomass_does_not_simplify(self):
        self.assertTrue(answer_test("EqualComAss", "y+(x+z)", "(z+y)+x")["correct"])
        self.assertFalse(answer_test("EqualComAss", "x+x", "2*x")["correct"])
        self.assertFalse(answer_test("EqualComAss", "(x+1)^2", "x^2+2*x+1")["correct"])
        self.assertTrue(answer_test("EqualComAss", "x-z", "x+(-z)")["correct"])
        self.assertTrue(answer_test("EqualComAss", "-2*x", "ta", env={"ta": -2*sp.Symbol("x")})["correct"])
        self.assertTrue(answer_test("EqualComAss", "3/4", "ta", env={"ta": sp.Rational(3, 4)})["correct"])
        self.assertFalse(answer_test("EqualComAss", "2/4", "ta", env={"ta": sp.Rational(1, 2)})["correct"])
        self.assertFalse(answer_test("EqualComAss", "0.75", "3/4")["correct"])
        for written, computed in (("cos(0)", "1"), ("sqrt(3)", "3^(1/2)"),
                                  ("2*sqrt(2)", "sqrt(8)"), ("4^(1/2)", "2")):
            with self.subTest(written=written):
                result = answer_test("EqualComAss", written, computed)
                self.assertTrue(result["valid"])
                self.assertTrue(result["cas_valid"])
                self.assertFalse(result["correct"])
        self.assertTrue(answer_test("EqualComAss", "sqrt(x)+sin(x)", "sin(x)+sqrt(x)")["correct"])
        self.assertTrue(answer_test("EqualComAss", "exp(x)", "%e^x")["correct"])
        wrong = answer_test("EqualComAss", "1+x", "1+2*x")
        self.assertEqual((wrong["valid"], wrong["cas_valid"], wrong["correct"]), (True, False, False))
        self.assertEqual(answer_test("EqualComAss", "x+x", "2*x")["cas_valid"], True)

    def test_facform_polynomial_factorisation(self):
        accepted = (("(x-1)*(x+1)", "x^2-1"), ("(x+1)^2", "x^2+2*x+1"),
                    ("4*(1-x/2)^2", "(x-2)^2"), ("2*(x+0.5)", "2*x+1"),
                    ("(x^2+1)*(x-3)", "(x^2+1)*(x-3)"),
                    ("(x+1)*(x-1)", "x^2-1"), ("(x-1)*(x+1)", "x^2-1"))
        for student, teacher in accepted:
            with self.subTest(student=student):
                self.assertTrue(answer_test("FacForm", student, teacher, "x")["correct"])
        rejected = (("x^2-1", "x^2-1"), ("2*x-2", "2*x-2"),
                    ("(x+1)*(x+2)", "x^2-1"), ("(x-1)*(x-1)", "x^2-1"))
        for student, teacher in rejected:
            with self.subTest(student=student):
                self.assertFalse(answer_test("FacForm", student, teacher, "x")["correct"])
        self.assertTrue(answer_test("FacForm", "(y-1)*(y+1)", "y^2-1", "v", env={"v": sp.Symbol("y")})["correct"])
        with self.assertRaisesRegex(Unsupported, "univariate rational"):
            answer_test("FacForm", "(x+y)*(x-y)", "x^2-y^2", "x")
        with self.assertRaisesRegex(Unsupported, "polynomial variable"):
            answer_test("FacForm", "x^2-1", "x^2-1", "")
        with self.assertRaisesRegex(Unsupported, "supported bounds"):
            answer_test("FacForm", "(x+1)^100*(x+1)^100", "1", "x")
        for cancelled in ("x/x", "(x-1)/(x-1)", "0/x", "x*(1/x)",
                          "(x^2-1)*(x/x)", "x^2-1+0/x", "(x/x)+(x^2-1)"):
            with self.subTest(cancelled=cancelled), self.assertRaisesRegex(Unsupported, "numeric denominators"):
                answer_test("FacForm", cancelled, "1", "x")
        with self.assertRaisesRegex(Unsupported, "nonnegative integer powers"):
            answer_test("FacForm", "x^2-1+0*x^(-1)", "x^2-1", "x")

    def test_singlefrac_equivalence_and_written_shape(self):
        accepted = (("2/n", "2/n"), ("-((x+1)/(x-1))", "-(x+1)/(x-1)"),
                    ("(x-1)/(x^2-1)", "1/(x+1)"), ("2/4", "1/2"),
                    ("x/(y/2)^2", "4*x/y^2"), ("2", "4/2"), ("x", "x"))
        for student, teacher in accepted:
            with self.subTest(student=student):
                self.assertTrue(answer_test("SingleFrac", student, teacher)["correct"])
        rejected = (("2*(1/n)", "2/n"), ("1/n+1/(n+1)", "(2*n+1)/(n*(n+1))"),
                    ("x/(2*(y/2))", "x/y"), ("x/(1/2)", "2*x"),
                    ("x/y", "y/x"), ("x+1/2", "(2*x+1)/2"))
        for student, teacher in rejected:
            with self.subTest(student=student):
                self.assertFalse(answer_test("SingleFrac", student, teacher)["correct"])

    def test_lowestterms_numeric_fractions_not_polynomial_cancellation(self):
        for student in ("1/2", "-1/2", "1/2+1/3", "1/(1/2)", "x/(x^2+x)",
                        "(x^2-1)/(x-1)", "0.5", "-3/5"):
            with self.subTest(student=student):
                self.assertTrue(answer_test("LowestTerms", student, "0")["correct"])
        for student in ("2/4", "-1/-2", "1/(2/4)", "x+3/6", "x*(6/9)",
                        "1/sqrt(2)", "1/(1+%i)", "1/(1+sqrt(2)-sqrt(2))"):
            with self.subTest(student=student):
                self.assertFalse(answer_test("LowestTerms", student, "not_the_answer")["correct"])

    def test_numeric_threshold_and_zero(self):
        self.assertTrue(answer_test("NumAbsolute", "1.0000000009", "1", "0")["correct"])
        self.assertFalse(answer_test("NumAbsolute", "1.000000001", "1", "0")["correct"])
        self.assertTrue(answer_test("NumRelative", "0", "0", "0")["correct"])
        self.assertFalse(answer_test("NumRelative", "0.000000001", "0", "1")["correct"])
        self.assertTrue(answer_test("NumRelative", "11", "10", "0.1")["correct"])
        self.assertFalse(answer_test("NumRelative", "11.000001", "10", "0.1")["correct"])
        self.assertFalse(answer_test("NumRelative", "1/(10^100+1)", "1/10^100", "0")["correct"])
        self.assertTrue(answer_test("NumAbsolute", "1.049", "1")["correct"])
        self.assertFalse(answer_test("NumAbsolute", "1.051", "1")["correct"])

    def test_decimal_places_and_rounding(self):
        self.assertTrue(answer_test("NumDecPlaces", "1.20", "1.2", "2")["correct"])
        self.assertFalse(answer_test("NumDecPlaces", "1.2", "1.2", "2")["correct"])
        self.assertTrue(answer_test("NumDecPlaces", "-1.24", "-1.245", "2")["correct"])
        self.assertFalse(answer_test("NumDecPlaces", "-1.25", "-1.245", "2")["correct"])
        self.assertTrue(answer_test("NumDecPlaces", "2.12", "2.125", "2")["correct"])
        self.assertFalse(answer_test("NumDecPlaces", "2.13", "2.125", "2")["correct"])
        self.assertTrue(answer_test("NumDecPlaces", "2.36", "2.355", "2")["correct"])
        self.assertTrue(answer_test("NumDecPlaces", "0.556", "0.5555", "3")["correct"])
        self.assertFalse(answer_test("NumDecPlaces", "1/2", "0.5", "2")["valid"])

    def test_decimal_places_supported_precision_boundary(self):
        self.assertTrue(answer_test("NumDecPlaces", "0." + "3" * 50, "1/3", "50")["correct"])
        self.assertFalse(answer_test("NumDecPlaces", "0." + "3" * 49 + "4", "1/3", "50")["correct"])
        with self.assertRaises(Unsupported):
            answer_test("NumDecPlaces", "0." + "3" * 51, "1/3", "51")

    def test_invalid_distinct_from_wrong_and_unsupported(self):
        self.assertEqual(answer_test("AlgEquiv", "x+2", "x+1")["valid"], True)
        self.assertEqual(answer_test("AlgEquiv", "x+", "x+1")["valid"], False)
        self.assertEqual(answer_test("AlgEquiv", "1/0", "x+1")["valid"], False)
        self.assertEqual(answer_test("AlgEquiv", "[1,2]", "1")["cas_valid"], False)
        with self.assertRaises(Unsupported):
            answer_test("StringMatch", "a", "a")


if __name__ == "__main__":
    unittest.main()
