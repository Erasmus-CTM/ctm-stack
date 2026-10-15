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
        self.assertEqual(answer_test("AlgEquiv", "[1,2]", "1")["valid"], False)
        with self.assertRaises(Unsupported):
            answer_test("StringMatch", "a", "a")


if __name__ == "__main__":
    unittest.main()
