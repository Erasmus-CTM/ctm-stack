"""Check that malformed or incomplete Maxima output cannot turn CI green."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compare_stack_maxima", ROOT / "scripts/compare_stack_maxima.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class ReferenceRunnerTests(unittest.TestCase):
    def test_fixture_covers_five_real_answer_tests(self):
        cases = reference.load_cases(ROOT / "tests/reference_cases.json")
        self.assertEqual({case["test"] for case in cases}, set(reference.TESTS))
        self.assertGreaterEqual(len(cases), 35)

    def test_result_parser_requires_every_unique_boolean_pair(self):
        cases = [{"id": "first"}, {"id": "second"}]
        parsed = reference.parse_maxima_output("startup\nSTACKREF|first|true|false\nSTACKREF|second|false|false\n", cases)
        self.assertEqual(parsed, {"first": (True, False), "second": (False, False)})
        with self.assertRaisesRegex(RuntimeError, "Missing Maxima results"):
            reference.parse_maxima_output("STACKREF|first|true|false\n", cases)
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            reference.parse_maxima_output("STACKREF|first|true|false\nSTACKREF|first|true|true\n", cases)
        with self.assertRaisesRegex(RuntimeError, "Missing Maxima results"):
            reference.parse_maxima_output("STACKREF|first|yes|false\nSTACKREF|second|false|false\n", cases)

    def test_batch_calls_official_loader_and_each_answer_test(self):
        cases = reference.load_cases(ROOT / "tests/reference_cases.json")
        with tempfile.TemporaryDirectory() as tmp:
            # The loader needs the checkout symlink; no Maxima executable is
            # required to inspect the generated batch in the ordinary suite.
            source = Path(tmp) / "source"
            source.mkdir()
            home = Path(tmp) / "home"
            home.mkdir()
            batch = reference.maxima_batch(source, cases, home)
        self.assertIn("stacklocallinux.mac", batch)
        self.assertIn("a=0 nounor b=0", batch)
        for name in reference.TESTS:
            self.assertIn(f"AT{name}(", batch)
        self.assertEqual(batch.count('print(sconcat("STACKREF|'), len(cases))

    def test_compares_cas_valid_without_conflating_input_validation(self):
        case = {"id": "eca_wrong_value", "test": "EqualComAss", "student": "x+1",
                "teacher": "x+2", "options": "", "source": "unit boundary"}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            maxima_dir = source / "stack/maxima"
            maxima_dir.mkdir(parents=True)
            (maxima_dir / "stacklocallinux.mac").write_text("", encoding="utf-8")
            (maxima_dir / "stackmaxima.mac").write_text("stackmaximaversion:123$", encoding="utf-8")

            def fake_output(command, *, timeout):
                if command[0] == "git":
                    return reference.STACK_SHA + "\n"
                if "--version" in command:
                    return "Maxima test version\n"
                return "STACKREF|eca_wrong_value|false|false\n"

            with patch.object(reference, "_command_output", side_effect=fake_output), \
                    patch.object(reference.shutil, "which", return_value="/usr/bin/maxima"):
                result = reference.compare(source, "maxima", [case])
        self.assertTrue(result["passed"])
        self.assertEqual(result["cases"][0]["maxima"], {"cas_valid": False, "correct": False})
        self.assertTrue(result["cases"][0]["adapter_input_valid"])


if __name__ == "__main__":
    unittest.main()
