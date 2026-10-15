import random
import unittest

import sympy as sp

from stack_sympy import InvalidAnswer, Unsupported, assignments, canonical_form, evaluate, parse
from stack_sympy.expressions import MAX_TOKENS, form_latex


class ExpressionsTest(unittest.TestCase):
    def test_exact_arithmetic_and_precedence(self):
        self.assertEqual(evaluate(".25+1e-2*2"), sp.Rational(27, 100))
        self.assertEqual(evaluate("-2^2"), -4)
        self.assertEqual(evaluate("2^3^2"), 512)
        self.assertEqual(evaluate("sqrt(4)+sin(%pi/2)"), 3)

    def test_env_and_author_functions(self):
        env = assignments("a:rand(9)+2; b:rand([3,4,5]); c:rand_with_step(3,9,2); d:[a,b][1]", rng=random.Random(7))
        self.assertGreaterEqual(env["a"], 2)
        self.assertLess(env["a"], 11)
        self.assertIn(env["b"], (3, 4, 5))
        self.assertIn(env["c"], (3, 5, 7, 9))
        self.assertEqual(env["d"], env["a"])
        self.assertEqual(evaluate("diff(x^3,x)"), 3 * sp.Symbol("x")**2)
        self.assertEqual(evaluate("decimalplaces(1/8,2)"), sp.Rational(3, 25))
        self.assertEqual(evaluate("decimalplaces(2.125,2)"), sp.Rational(53, 25))
        self.assertEqual(evaluate("dispdp(-2.125,2)"), -sp.Rational(53, 25))
        self.assertEqual(evaluate("displaydp(2.135,2)"), sp.Rational(107, 50))
        self.assertEqual(evaluate("decimalplaces(0.5555,3)"), sp.Rational(139, 250))

    def test_random_upper_exclusive_and_step_inclusive(self):
        rng = random.Random(1)
        self.assertEqual({evaluate("rand(1)", rng=rng) for _ in range(10)}, {0})
        self.assertEqual(evaluate("rand_with_step(3,3,2)", rng=rng), 3)

    def test_ast_is_immutable_and_form_keeps_terms(self):
        node = parse("x+x")
        with self.assertRaises(AttributeError):
            node.kind = "other"
        self.assertNotEqual(canonical_form(node), canonical_form("2*x"))
        self.assertEqual(canonical_form("x+(z+y)"), canonical_form("y+x+z"))
        self.assertEqual(canonical_form("x-y"), canonical_form("-y+x"))
        self.assertEqual(canonical_form("x-2*y"), canonical_form("x+(-2)*y"))
        self.assertEqual(canonical_form("-(-x)"), canonical_form("x"))
        self.assertEqual(canonical_form("x/(y*z)"), canonical_form("x/y/z"))
        self.assertNotEqual(canonical_form("x*(y+z)"), canonical_form("x*y+x*z"))
        self.assertNotEqual(canonical_form("x^2+(5+3)*x+5*3"), canonical_form("x^2+8*x+15"))
        self.assertNotEqual(canonical_form("(8/15)*8"), canonical_form("64/15"))
        self.assertNotEqual(canonical_form("1/2"), canonical_form("3/6"))
        self.assertNotEqual(canonical_form("10*x-6*x"), canonical_form("4*x"))
        self.assertNotEqual(canonical_form("xy"), canonical_form("x*y"))
        self.assertEqual(canonical_form("sqrt(x)"), canonical_form("a", {"a": sp.sqrt(sp.Symbol("x"))}))
        self.assertEqual(canonical_form("abs(x)"), canonical_form("a", {"a": sp.Abs(sp.Symbol("x"))}))

    def test_assumptions_are_explicit(self):
        x = sp.Symbol("x")
        self.assertEqual(evaluate("sqrt(x^2)"), sp.sqrt(x**2))
        self.assertEqual(evaluate("sqrt(x^2)", assumptions={"positive": True}), sp.Symbol("x", positive=True))

    def test_insertstars_modes_and_ambiguous_names(self):
        x = sp.Symbol("x")
        for source, explicit in (("2x", "2*x"), ("2(x+1)", "2*(x+1)"),
                                 ("(x+1)(x-1)", "(x+1)*(x-1)"),
                                 ("(x+1)x", "(x+1)*x"), ("sin(x)2", "sin(x)*2")):
            with self.subTest(source=source):
                tree = parse(source, insertstars=1)
                self.assertEqual(evaluate(tree), evaluate(explicit))
                self.assertEqual(canonical_form(tree), canonical_form(explicit))
                with self.assertRaises(InvalidAnswer):
                    parse(source, insertstars=0)
        self.assertEqual(parse("xy", insertstars=1).value, "xy")
        self.assertEqual(parse("x2", insertstars=1).value, "x2")
        self.assertEqual(evaluate(parse("sin(x)", insertstars=1)), sp.sin(x))
        for source in ("x(y+1)", "x y", "sin x", "2 x"):
            with self.subTest(source=source), self.assertRaises(InvalidAnswer):
                parse(source, insertstars=1)
        with self.assertRaisesRegex(Unsupported, "insertstars mode"):
            parse("2x", insertstars=3)
        with self.assertRaisesRegex(InvalidAnswer, r"Missing \*"):
            parse("2x", insertstars=0)

    def test_form_latex_keeps_terms_and_precedence(self):
        examples = {
            "x**2+8x+15": r"x^{2} + 8x + 15",
            "x+x": "x + x",
            "x-(y-z)": r"x - \left(y - z\right)",
            "(x+y)*z": r"\left(x + y\right) \cdot z",
            "x/(y/z)": r"\frac{x}{\frac{y}{z}}",
            "(-x)^2": r"\left(-x\right)^{2}",
            "x^(y^z)": r"x^{y^{z}}",
            "1.50+x": "1.50 + x",
            "1.2e-3+x": r"1.2 \times 10^{-3} + x",
            "1e-3^2": r"\left(1 \times 10^{-3}\right)^{2}",
        }
        for source, expected in examples.items():
            with self.subTest(source=source):
                self.assertEqual(form_latex(parse(source, insertstars=1)), expected)
        self.assertNotEqual(form_latex(parse("xy", insertstars=1)), form_latex(parse("x*y")))
        self.assertEqual(form_latex(parse("a^2"), {"a": sp.Integer(-3)}),
                         r"\left(-3\right)^{2}")
        self.assertEqual(form_latex(parse("a*y"), {"a": sp.Symbol("x") + 1}),
                         r"\left(x + 1\right) \cdot y")
        self.assertEqual(form_latex(parse("-a"), {"a": sp.Integer(-3)}),
                         r"-\left(-3\right)")
        self.assertEqual(form_latex(parse("x-a"), {"a": sp.Integer(-3)}),
                         r"x - \left(-3\right)")
        self.assertEqual(form_latex(parse("2*a"), {"a": sp.Integer(3)}),
                         r"2 \cdot 3")
        self.assertEqual(form_latex(parse("2*a"), {"a": 3 * sp.Symbol("x")}),
                         r"2 \cdot 3 x")
        self.assertEqual(form_latex(parse("a*b"), {"a": sp.Integer(3), "b": sp.Integer(5)}),
                         r"3 \cdot 5")
        self.assertEqual(form_latex(parse("-(-x)")), r"-\left(-x\right)")
        # Insertion may add operation nodes, but cannot evade the original token bound.
        with self.assertRaisesRegex(InvalidAnswer, "Too many tokens"):
            parse("2x+" * (MAX_TOKENS // 3 + 1), insertstars=1)

    def test_invalid_and_unsupported_constructs(self):
        for source in ("__import__('os')", "x.__class__", "x; y", "lambda x:x", "x=2", "x**100000", "2^100000", "[1,2]", "rand(5)", "%foo"):
            with self.subTest(source=source), self.assertRaises((InvalidAnswer, Unsupported)):
                evaluate(source, student=True)
        with self.assertRaises(InvalidAnswer):
            parse("(" * 50 + "x" + ")" * 50)
        with self.assertRaises(InvalidAnswer):
            assignments("x:1; y:system(2)")


if __name__ == "__main__":
    unittest.main()
