"""Guard corpus provenance and a representative native XML assessment boundary."""

import json
import unittest
from pathlib import Path

from scripts.check_corpus import BASELINE, MANIFEST, replay_one, seeds_for, validate_manifest
from stack_sympy.engine import grade, instantiate
from stack_sympy.importer import import_xml


class CorpusTests(unittest.TestCase):
    def test_all_xml_has_exact_provenance_and_native_metadata(self):
        entries = validate_manifest(verify_upstream=True)
        self.assertEqual(len(entries), 30)
        self.assertEqual(sum(e["qtest_count"] for e in entries), 73)
        self.assertTrue(all(len(seeds_for(e)) <= 3 for e in entries))
        self.assertEqual(len(list(MANIFEST.parent.glob("*.xml"))), 30)

    def test_corrected_authored_qtests_replay(self):
        entries = {e["file"]: e for e in validate_manifest()}
        for file in ("AlgMap-1-6.xml", "AlgMap-1-5.xml", "AlgMap-10-1.xml", "AlgMap-13-1-.xml",
                     "AlgMap-2-5.xml", "AlgMap-4-13.xml"):
            passing = replay_one(entries[file])
            self.assertEqual(passing["status"], "qtests_pass", file)
            self.assertEqual(passing["replayed_cases"], passing["native_qtests"] * len(passing["seeds"]))
            self.assertEqual(passing["instantiated_seeds"], passing["seeds"])

    def test_report_retains_unsupported_context(self):
        report = json.loads(BASELINE.read_text(encoding="utf-8"))
        by_file = {q["file"]: q for q in report["questions"]}
        for file in ("AlgMap-10-1.xml", "AlgMap-13-1-.xml"):
            row = by_file[file]
            self.assertEqual(row["status"], "qtests_pass", file)
            self.assertEqual(row["replayed_cases"], row["native_qtests"] * len(row["seeds"]))
        self.assertEqual(by_file["AlgMap-3-3.xml"]["status"], "unsupported_instantiate")
        self.assertIn("questionvariables", by_file["AlgMap-3-3.xml"]["diagnostic"]["location"])
        self.assertEqual(by_file["AlgMap-14-1.xml"]["status"], "qtests_pass")
        self.assertEqual(by_file["Logs_1.xml"]["status"], "qtests_pass")
        self.assertIn("only scalar teacher answers", by_file["Complex_Convert_1.xml"]["diagnostic"]["reason"])
        self.assertEqual(by_file["AlgMap-15-1.xml"]["diagnostic"]["location"], "input[ans]/tans")
        self.assertIn("Set expressions", by_file["AlgMap-15-1.xml"]["diagnostic"]["reason"])

    def test_seed_specific_mismatch_is_recorded_without_promoting_question(self):
        report = json.loads(BASELINE.read_text(encoding="utf-8"))
        row = next(q for q in report["questions"] if q["file"] == "AlgMap-8-10.xml")
        self.assertEqual(row["status"], "qtests_mismatch")
        self.assertEqual(row["instantiated_seeds"], row["seeds"])
        self.assertEqual(row["replayed_cases"], row["native_qtests"] * len(row["seeds"]))
        self.assertEqual({case["seed"] for case in row["mismatches"]}, {1856951054})
        self.assertEqual({case["testcase"] for case in row["mismatches"]}, {"1", "2"})
        self.assertEqual(report["summary"]["failed_cases"], len(row["mismatches"]))

    def test_original_lowest_terms_tree_awards_wrong_reduced_value(self):
        # This upstream response-tree ordering is a known authoring limitation,
        # disclosed next to the gallery card. Preserve the XML unmodified.
        question = import_xml(MANIFEST.parent / "AlgMap-2-5.xml")[0]
        variant = instantiate(question, 554625703)
        self.assertNotEqual(str(variant["env"]["ta"]), "123/127")
        result = grade(question, {"ans": "123/127"}, variant=variant)
        self.assertEqual(result["status"], "graded")
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["prts"]["prt1"]["note"], "1-0-T")


if __name__ == "__main__":
    unittest.main()
