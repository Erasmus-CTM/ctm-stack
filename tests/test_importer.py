import unittest
from pathlib import Path

from stack_sympy.importer import UnsupportedQuestion, import_xml
from stack_sympy.engine import instantiate


ROOT = Path(__file__).resolve().parents[1]


class ImporterTests(unittest.TestCase):
    def test_unmodified_stack_exports(self):
        for path in (ROOT / "questions/upstream/algmap-6-1.xml",
                     ROOT / "questions/upstream/bodmas.xml",
                     ROOT / "questions/upstream/rounding-three-dp.xml"):
            with self.subTest(path=path.name):
                question, = import_xml(path)
                self.assertTrue(question["inputs"])
                self.assertTrue(question["prts"])
                self.assertTrue(question["qtests"])

    def test_insertstars_modes_and_unsupported_diagnostic(self):
        xml = (ROOT / "questions/polynomial-expansion.xml").read_text()
        self.assertEqual(import_xml(xml)[0]["inputs"][0]["insertstars"], 1)
        strict = xml.replace("<insertstars>1</insertstars>", "<insertstars>0</insertstars>")
        self.assertEqual(import_xml(strict)[0]["inputs"][0]["insertstars"], 0)
        for mode in ("2", "3", "4", "6", "bogus"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    UnsupportedQuestion, r"input\[ans\]/insertstars.*only 0.*and 1"):
                import_xml(xml.replace("<insertstars>1</insertstars>", f"<insertstars>{mode}</insertstars>"))

    def test_reject_unsupported_answer_test_with_location(self):
        path = ROOT / "questions/upstream/bodmas.xml"
        xml = path.read_text().replace("<answertest>NumRelative</answertest>",
                                       "<answertest>Diff</answertest>")
        with self.assertRaisesRegex(UnsupportedQuestion, r"1\.1\.4\.T2 BODMAS: prt\[prt1\]/node\[0\]/answertest"):
            import_xml(xml)

    def test_reject_cycle_and_dangling_node(self):
        path = ROOT / "questions/upstream/bodmas.xml"
        xml = path.read_text().replace("<truenextnode>-1</truenextnode>", "<truenextnode>0</truenextnode>")
        with self.assertRaisesRegex(UnsupportedQuestion, "cycle in response tree"):
            import_xml(xml)
        xml = path.read_text().replace("<truenextnode>-1</truenextnode>", "<truenextnode>99</truenextnode>")
        with self.assertRaisesRegex(UnsupportedQuestion, "dangling next node"):
            import_xml(xml)

    def test_categories_and_descriptions_are_not_assessments(self):
        xml = '<quiz><question type="category"><category><text>x</text></category></question>' \
              '<question type="description"><name><text>Intro</text></name></question></quiz>'
        self.assertEqual(import_xml(xml), [])

    def test_reject_form_loss_in_equalcomass_and_unsimplified_variables(self):
        path = ROOT / "questions/upstream/algmap-6-1.xml"
        xml = path.read_text().replace("<sans>ans</sans>", "<sans>ans+0</sans>")
        with self.assertRaisesRegex(UnsupportedQuestion, "EqualComAss requires a direct input"):
            import_xml(xml)
        xml = path.read_text().replace("<questionsimplify>1</questionsimplify>",
                                       "<questionsimplify>0</questionsimplify>")
        xml = xml.replace("ta:ev(a*x+b*y-c*x-d*y+5,simp);", "ta:x+x;")
        with self.assertRaisesRegex(UnsupportedQuestion, "loses unsimplified answer form"):
            instantiate(import_xml(xml)[0], 17)

    def test_reject_forward_assignment_and_nonfinite_scoring(self):
        path = ROOT / "questions/upstream/algmap-6-1.xml"
        xml = path.read_text().replace("a:rand(9)+2;", "a:b+1;")
        with self.assertRaisesRegex(UnsupportedQuestion, "forward or cyclic assignment reference"):
            instantiate(import_xml(xml)[0], 17)
        xml = path.read_text().replace("<defaultgrade>1</defaultgrade>",
                                       "<defaultgrade>NaN</defaultgrade>")
        with self.assertRaisesRegex(UnsupportedQuestion, "number must be finite"):
            import_xml(xml)


if __name__ == "__main__":
    unittest.main()
