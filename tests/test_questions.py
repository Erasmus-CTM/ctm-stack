"""Native XML examples are executable STACK exports, not JSON reconstructions."""

from pathlib import Path
import unittest
from xml.etree import ElementTree

from stack_sympy.engine import grade, instantiate, run_question_tests
from stack_sympy.importer import import_xml


QUESTION_DIR = Path(__file__).resolve().parents[1] / "questions"


class AuthoredQuestionsTest(unittest.TestCase):
    def test_moodle_export_shape_and_authored_tests(self):
        for filename in ("polynomial-expansion.xml", "rational-equivalence.xml", "numerical-measurement.xml"):
            with self.subTest(filename=filename):
                path = QUESTION_DIR / filename
                xml = ElementTree.parse(path).getroot()
                self.assertEqual(xml.tag, "quiz")
                question = xml.find("question")
                self.assertEqual(question.get("type"), "stack")
                self.assertTrue(question.findall("input"))
                self.assertTrue(question.findall("prt/node"))
                self.assertGreaterEqual(len(question.findall("qtest")), 3)
                imported = import_xml(path)
                self.assertEqual(len(imported), 1)
                result = run_question_tests(imported[0], seeds=(17, 29, 47))
                failures = [(case["testcase"], case["seed"], case["checks"])
                            for case in result["results"] if not case["passed"]]
                self.assertTrue(result["passed"], failures)

    def test_form_sensitive_partial_credit_and_misconception(self):
        expansion = import_xml(QUESTION_DIR / "polynomial-expansion.xml")[0]
        variant = instantiate(expansion, 17)
        env = variant["env"]
        factored = grade(expansion, {"ans": f"(x+{env['a']})*(x+{env['b']})"}, variant=variant)
        self.assertEqual(factored["score"], 0.5)
        self.assertEqual(factored["prts"]["prt1"]["note"], "prt1-0-F | prt1-1-T")
        self.assertIn("expand", factored["prts"]["prt1"]["feedback"].lower())

        rational = import_xml(QUESTION_DIR / "rational-equivalence.xml")[0]
        variant = instantiate(rational, 17)
        env = variant["env"]
        reciprocal = grade(rational, {"ans": f"(x+{env['n']})/(x+{env['m']})"}, variant=variant)
        self.assertEqual(reciprocal["score"], 0)
        self.assertIn("inverted", reciprocal["prts"]["prt1"]["feedback"])

    def test_decimal_precision_preserves_written_zero(self):
        question = import_xml(QUESTION_DIR / "numerical-measurement.xml")[0]
        answers = {"perimeter": "24", "area": "17.5", "reported": "17.50"}
        self.assertEqual(grade(question, answers, seed=17)["score"], 1)
        answers["reported"] = "17.5"
        result = grade(question, answers, seed=17)
        self.assertAlmostEqual(result["score"], 0.7)
        self.assertEqual(result["prts"]["prt3"]["score"], 0)


if __name__ == "__main__":
    unittest.main()
