"""Contract checks for the portable evaluator and desired-outcome axis."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_extensions/stack-sympy"))
sys.path.insert(0, str(ROOT / "scripts"))
from native_compliance.common import desired_outcome, expected_error_kind, matches_desired
from native_compliance.python_runner import classify_case, evaluate_case
from run_compliance_python import assess, load_policy, run


def sample(**changes):
    case = {"id": "case-1", "test": "AlgEquiv", "student": "x+1", "teacher": "1+x",
            "options": "", "expected_score": 1, "extra_fields": []}
    case.update(changes)
    return case


class PythonConformanceTests(unittest.TestCase):
    def test_desired_codes_are_mathematical_axis(self):
        self.assertEqual(desired_outcome(-2), {"kind": "result", "correct": False})
        self.assertEqual(desired_outcome(-3), {"kind": "result", "correct": True})
        note = "ATNumDecPlaces_OptNotInt."
        self.assertEqual(desired_outcome(-1, note), {"kind": "controlled_error", "correct": None,
                                                      "error_kind": "invalid_option"})
        self.assertFalse(matches_desired({"kind": "unexpected_exception", "correct": False}, -1, note))
        self.assertFalse(matches_desired({"kind": "unsupported"}, -1, note))
        self.assertTrue(matches_desired({"kind": "invalid_option"}, -1, note))
        self.assertFalse(matches_desired({"kind": "invalid_student"}, -1, note))
        self.assertFalse(matches_desired({"kind": "invalid_option"}, -1, "TEST_FAILED"))
        self.assertIsNone(expected_error_kind("_STACKERROR_SAns. _STACKERROR_TAns."))

    def test_upstream_error_origin_notes(self):
        for note, kind in (("ATAlgEquiv_STACKERROR_SAns.", "invalid_student"),
                           ("ATAlgEquivTEST_FAILED-Empty SA.", "invalid_student"),
                           ("ATAlgEquiv_STACKERROR_TAns.", "invalid_teacher"),
                           ("ATAlgEquivTEST_FAILED-Empty TA.", "invalid_teacher"),
                           ("ATNumRelative_STACKERROR_Opt.", "invalid_option"),
                           ("ATNumerical_STACKERROR_tol.", "invalid_option"),
                           ("ATNumDecPlaces_OptNotInt.", "invalid_option"),
                           ("STACKERROR_OPTION.", "invalid_option")):
            with self.subTest(note=note):
                self.assertEqual(expected_error_kind(note), kind)
                self.assertTrue(matches_desired({"kind": kind}, -1, note))
                for other in {"invalid_student", "invalid_teacher", "invalid_option"} - {kind}:
                    self.assertFalse(matches_desired({"kind": other}, -1, note))

    def test_runner_rejects_wrong_or_unknown_error_origin(self):
        case = sample(expected_score=-1, answer_note="ATAlgEquiv_STACKERROR_SAns.")
        wrong = {"case_id": "case-1", "test": "AlgEquiv", "kind": "invalid_teacher",
                 "message": "teacher evaluation failed"}
        assessed = assess(case, wrong, {}, {"kind": "supported"})
        self.assertEqual(assessed["desired"]["error_kind"], "invalid_student")
        self.assertFalse(assessed["desired_match"])
        self.assertEqual(assessed["policy_status"], "unexpected")
        self.assertEqual(assess({**case, "answer_note": "TEST_FAILED"},
                                {**wrong, "kind": "invalid_student"}, {},
                                {"kind": "supported"})["policy_status"], "unexpected")

    def test_equalcomass_wrong_value_is_ordinary_result(self):
        observation = evaluate_case(sample(test="EqualComAss", student="x+1", teacher="x+2",
                                           expected_score=0))
        self.assertEqual((observation["kind"], observation["cas_valid"], observation["correct"]),
                         ("result", False, False))
        self.assertTrue(matches_desired(observation, 0))
        self.assertFalse(matches_desired({"kind": "invalid_student", "valid": False, "correct": False}, 0))

    def test_source_errors_are_attributed_without_excusing_exception(self):
        self.assertEqual(evaluate_case(sample(student="1/0", expected_score=-1))["kind"], "invalid_student")
        self.assertEqual(evaluate_case(sample(teacher="1/0", expected_score=-1))["kind"], "invalid_teacher")
        self.assertEqual(evaluate_case(sample(test="NumDecPlaces", student="0.1", teacher="1",
                                              options="1/0", expected_score=-1))["kind"], "invalid_option")
        self.assertEqual(classify_case(sample(test="FacForm", options=""))["kind"], "unsupported")

    def test_scope_preserves_header_and_raw_decimal(self):
        case = sample(test="NumDecPlaces", student="1.230", teacher="1.23", options="3",
                      extra_fields=["header"])
        self.assertEqual(classify_case(case)["kind"], "supported")
        self.assertTrue(evaluate_case(case)["correct"])
        self.assertEqual(classify_case(sample(test="Units"))["kind"], "unsupported")
        self.assertEqual(classify_case(sample(student="[x]"))["kind"], "unsupported")

    def test_case_specific_policy_is_exact_and_stale_entries_fail(self):
        case = sample(expected_score=1)
        observed = {"case_id": "case-1", "test": "AlgEquiv", "kind": "result", "valid": True,
                    "correct": False, "note": ""}
        policy = {"case-1": {"expected_observation": {"kind": "result", "valid": True,
                                                      "correct": False, "note": ""}, "reason": "reviewed defect"}}
        self.assertEqual(assess(case, observed, policy, {"kind": "supported"})["policy_status"], "known_defect")
        self.assertEqual(assess(case, {**observed, "correct": True}, policy,
                                {"kind": "supported"})["policy_status"], "unexpected")
        self.assertEqual(assess(case, {**observed, "note": "changed"}, policy,
                                {"kind": "supported"})["policy_status"], "unexpected")
        self.assertEqual(assess(case, {**observed, "kind": "unexpected_exception"}, policy,
                                {"kind": "supported"})["policy_status"], "unexpected")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps({"schema_version": 1, "scope_sha256": "0" * 64, "cases": {
                "case-1": {"expected_observation": {"kind": "timeout"}, "reason": "too slow"}}}))
            with self.assertRaisesRegex(ValueError, "cannot approve"):
                load_policy(path, {"case-1"})

    def test_scope_kind_drift_fails_before_running_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.json"
            policy = Path(directory) / "policy.json"
            fixture.write_text(json.dumps({"schema_version": 1, "cases": [sample()]}))
            policy.write_text(json.dumps({"schema_version": 1, "scope_sha256": "0" * 64,
                                          "cases": {}}))
            with self.assertRaisesRegex(ValueError, "Preflight scope changed"):
                run(fixture, policy)


if __name__ == "__main__":
    unittest.main()
