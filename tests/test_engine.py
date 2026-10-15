import json
import unittest
from pathlib import Path

from stack_sympy.cli import render
from stack_sympy.engine import _answer_note_matches, _qtest_answer, grade, instantiate, run_question_tests, validate
from stack_sympy.expressions import assignments
from stack_sympy.importer import UnsupportedQuestion, import_xml


ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def question(self, filename):
        return import_xml(ROOT / "questions" / filename)[0]

    def test_random_variant_reproducibility_and_frozen_grade(self):
        q = self.question("polynomial-expansion.xml")
        variant = instantiate(q, 29)
        self.assertEqual(variant, instantiate(q, 29))
        self.assertNotEqual(variant["env"], instantiate(q, 17)["env"])
        correct = grade(q, {"ans": variant["env"]["ta"]}, variant=variant)
        self.assertEqual(correct["score"], 1)
        self.assertEqual(correct["status"], "graded")
        invalid = grade(q, {"ans": "__import__('os')"}, variant=variant)
        self.assertEqual(invalid["status"], "invalid")

    def test_native_author_tests_multiple_seeds(self):
        for filename in ("polynomial-expansion.xml", "rational-equivalence.xml",
                         "numerical-measurement.xml", "upstream/algmap-6-1.xml",
                         "upstream/bodmas.xml", "upstream/rounding-three-dp.xml"):
            with self.subTest(filename=filename):
                result = run_question_tests(self.question(filename), seeds=[17, 29, 47])
                failures = [(t["testcase"], t["seed"], t["checks"]) for t in result["results"] if not t["passed"]]
                self.assertTrue(result["passed"], failures)

    def test_invalid_input_and_decimal_written_precision(self):
        q = self.question("numerical-measurement.xml")
        variant = instantiate(q, 17)
        result = grade(q, {"perimeter": "24", "area": "17.5", "reported": "17.50"}, variant=variant)
        self.assertEqual(result["score"], 1)
        result = grade(q, {"perimeter": "24", "area": "17.5", "reported": "17.5"}, variant=variant)
        self.assertLess(result["score"], 1)
        result = grade(q, {"perimeter": "x", "area": "17.5", "reported": "17.50"}, variant=variant)
        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["inputs"]["perimeter"]["valid"])

    def test_render_payload_is_json_and_script_safe(self):
        path = ROOT / "questions/polynomial-expansion.xml"
        output = render(str(path), "Expand a product (form-sensitive)", "question-1", 2, 17, True)
        self.assertIn('class="stack-prompt stack-question"', output)
        self.assertIn('class="stack-tests"', output)
        payload = output.split('<script type="application/json" class="stack-sympy-data">', 1)[1].split('</script>', 1)[0]
        data = json.loads(payload)
        self.assertEqual([v["seed"] for v in data["variants"]], [17, 18])
        self.assertEqual(data["question"]["name"], "Expand a product (form-sensitive)")
        self.assertNotIn("<", payload)

    def test_unsupported_castext_is_diagnostic(self):
        q = self.question("polynomial-expansion.xml")
        q["questiontext"] += "[[if test]]"
        with self.assertRaisesRegex(UnsupportedQuestion, "unsupported CASText block"):
            instantiate(q, 1)

    def test_qtest_display_precision_with_semicolon_assignments(self):
        q = {"name": "precision", "variables": "a:1; b:dispdp(a,2)"}
        self.assertEqual(_qtest_answer(q, "b", assignments(q["variables"])), "1.00")

    def test_validate_previews_written_form_without_grading(self):
        q = self.question("polynomial-expansion.xml")
        result = validate(q, {"ans": "x+x"}, variant=instantiate(q, 17))
        self.assertEqual(result["status"], "valid")
        self.assertIn("x + x", result["inputs"]["ans"]["latex"])
        self.assertNotIn("score", result)

    def test_input_star_modes_share_validation_and_form_grading(self):
        q = self.question("polynomial-expansion.xml")
        variant = instantiate(q, 17)
        implied = "x**2+8x+15"
        result = validate(q, {"ans": implied}, variant=variant)
        self.assertEqual(result["inputs"]["ans"]["latex"], r"x^{2} + 8x + 15")
        self.assertEqual(grade(q, {"ans": implied}, variant=variant)["score"], 1)
        self.assertEqual(grade(q, {"ans": "(x+3)(x+5)"}, variant=variant)["score"], 0.5)
        self.assertEqual(grade(q, {"ans": "x+x"}, variant=variant)["inputs"]["ans"]["latex"], "x + x")

        q["inputs"][0]["insertstars"] = 0
        strict = validate(q, {"ans": implied}, variant=variant)
        self.assertEqual(strict["status"], "invalid")
        self.assertIn("Missing *", strict["inputs"]["ans"]["feedback"])
        self.assertEqual(grade(q, {"ans": implied}, variant=variant)["status"], "invalid")
        self.assertEqual(grade(q, {"ans": "x**2+8*x+15"}, variant=variant)["score"], 1)

    def test_qtest_alias_preserves_unsimplified_form(self):
        q = {"name": "raw", "variables": "raw:x+x", "simplify": False}
        self.assertEqual(_qtest_answer(q, "raw", assignments(q["variables"]), preserve_form=True), "x+x")

    def test_qtest_note_order_and_anchors(self):
        notes = ["first", "middle", "last"]
        self.assertTrue(_answer_note_matches("middle|last", notes))
        self.assertFalse(_answer_note_matches("last|middle", notes))
        self.assertTrue(_answer_note_matches("(middle)", notes))
        self.assertFalse(_answer_note_matches("middle", notes))
        self.assertTrue(_answer_note_matches("[first|last]", notes))
        self.assertFalse(_answer_note_matches("[middle|last]", notes))
        self.assertTrue(_answer_note_matches("NULL", []))
        self.assertFalse(_answer_note_matches("NULL", notes))
        self.assertTrue(_answer_note_matches("()", notes))
        self.assertFalse(_answer_note_matches("", []))

    def test_native_form_sensitive_corpus_qtests(self):
        for stem in ("AlgMap-1-5", "AlgMap-2-1", "AlgMap-4-1", "AlgMap-6-4",
                     "AlgMap-6-7", "AlgMap-8-5", "AlgMap-10-1", "AlgMap-13-1-"):
            q = import_xml(ROOT / "questions/corpus" / f"{stem}.xml")[0]
            with self.subTest(stem=stem):
                result = run_question_tests(q, seeds=q["deployedseeds"][:3] or [17, 29, 47])
                self.assertTrue(result["passed"], [(row["testcase"], row["seed"], row["checks"])
                                                   for row in result["results"] if not row["passed"]])

    def test_unsimplified_castext_shows_written_powers(self):
        q = import_xml(ROOT / "questions/corpus/AlgMap-1-5.xml")[0]
        variant = instantiate(q, q["deployedseeds"][0])
        html = variant["question_html"]
        self.assertIn("c^{", html)
        self.assertIn(r"\cdot", html)

    def test_castext_retains_tex_grouping_for_fraction_and_exponent(self):
        q = import_xml(ROOT / "questions/corpus/AlgMap-8-5.xml")[0]
        html = instantiate(q, 17)["question_html"]
        self.assertIn(r"\frac{", html)
        self.assertIn("}{", html)
        q = self.question("polynomial-expansion.xml")
        q["questiontext"] += r"\(x^{@12@}\)"
        self.assertIn(r"x^{12}", instantiate(q, 17)["question_html"])

    def test_castext_uses_question_assumptions(self):
        q = self.question("rational-equivalence.xml")
        q["assumepositive"] = True
        q["questiontext"] += " {@sqrt(x^2)@}"
        self.assertIn(r"\(x\)", instantiate(q, 17)["question_html"])

    def test_reject_castext_token_inside_html_attribute(self):
        q = self.question("rational-equivalence.xml")
        q["questiontext"] += '<span title="[[input:ans]]">unsafe</span>'
        with self.assertRaisesRegex(UnsupportedQuestion, "tokens inside HTML tags"):
            instantiate(q, 17)


if __name__ == "__main__":
    unittest.main()
