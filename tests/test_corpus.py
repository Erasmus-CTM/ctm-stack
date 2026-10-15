"""Guard corpus provenance and a representative native XML assessment boundary."""

import json
import unittest
from pathlib import Path

from scripts.check_corpus import BASELINE, MANIFEST, replay_one, seeds_for, validate_manifest


class CorpusTests(unittest.TestCase):
    def test_all_xml_has_exact_provenance_and_native_metadata(self):
        entries = validate_manifest(verify_upstream=True)
        self.assertEqual(len(entries), 30)
        self.assertEqual(sum(e["qtest_count"] for e in entries), 73)
        self.assertTrue(all(len(seeds_for(e)) <= 3 for e in entries))
        self.assertEqual(len(list(MANIFEST.parent.glob("*.xml"))), 30)

    def test_supported_author_qtests_and_visible_mismatch(self):
        entries = {e["file"]: e for e in validate_manifest()}
        passing = replay_one(entries["AlgMap-1-6.xml"])
        self.assertEqual(passing["status"], "qtests_pass")
        self.assertEqual(passing["replayed_cases"], passing["native_qtests"] * len(passing["seeds"]))
        self.assertEqual(passing["instantiated_seeds"], passing["seeds"])

        mismatch = replay_one(entries["AlgMap-1-5.xml"])
        self.assertEqual(mismatch["status"], "qtests_mismatch")
        self.assertGreater(mismatch["failed_checks"], 0)
        check = mismatch["mismatches"][0]["checks"][0]
        self.assertIn("expected", check)
        self.assertIn("actual", check)
        self.assertNotEqual(check["actual"], check["expected"])

    def test_report_retains_unsupported_context(self):
        report = json.loads(BASELINE.read_text(encoding="utf-8"))
        by_file = {q["file"]: q for q in report["questions"]}
        self.assertEqual(by_file["AlgMap-10-1.xml"]["status"], "unsupported_import")
        self.assertIn("answertest", by_file["AlgMap-10-1.xml"]["diagnostic"]["location"])
        self.assertEqual(by_file["AlgMap-3-3.xml"]["status"], "unsupported_instantiate")
        self.assertIn("questionvariables", by_file["AlgMap-3-3.xml"]["diagnostic"]["location"])


if __name__ == "__main__":
    unittest.main()
