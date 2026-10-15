"""Protocol tests for the native STACK oracle (Maxima runs in hosted CI)."""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from native_compliance import maxima_runner as native  # noqa: E402
import run_compliance_maxima  # noqa: E402


def case(suffix="1", test="AlgEquiv", student="x+1", teacher="1+x", options=""):
    return {"id": "a" * 64 + "-" + suffix, "test": test,
            "student": student, "teacher": teacher, "options": options}


class NativeMaximaTests(unittest.TestCase):
    def test_all_fixture_cases_are_accounted_for(self):
        fixture = json.loads((ROOT / "tests/native_compliance/fixtures.json").read_text())
        native.validate_cases(fixture["cases"])
        self.assertEqual(len(fixture["cases"]), 2303)
        self.assertEqual(sum(native._unavailable(row) is None for row in fixture["cases"]), 837)
        self.assertEqual(native.scope_sha256(fixture["cases"]),
                         "437e047c66de2ce7209ef531b7a8f40ec2229f5d9203621a4511bb82a52628e7")
        self.assertEqual(native._unavailable(case(test="NumAbsolute", options="")), None)
        self.assertEqual(native._unavailable(case(test="NotImplemented")), "test_family_not_implemented")
        self.assertEqual(native._unavailable(case(student="")), "empty_answer_requires_php_controller")
        self.assertIsNotNone(native._unavailable(case(student="x);quit()$")))
        self.assertEqual(native._unavailable(case(student="Ω")), "non_ascii_requires_php_parser_student")
        self.assertEqual(native._unavailable(case(student="x#pm#1")), "plus_minus_requires_php_parser_student")
        self.assertEqual(native._unavailable(case(student="1/0")), "undefined_expression_requires_php_controller_student")
        self.assertEqual(native._unavailable(case(student="(x")), "malformed_expression_requires_php_parser_student")

    def test_batch_arguments_simplification_raw_and_default(self):
        cases = [case(), case("2", "EqualComAss"), case("3", "FacForm", options="x"),
                 case("4", "NumAbsolute"), case("5", "NumRelative", options="0.1"),
                 case("6", "NumDecPlaces", student="1.200", teacher="1.2", options="3")]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            batch = native.make_batch(ROOT, cases, home, 7)
        self.assertIn('ATAlgEquiv(parse_string("x+1"),parse_string("1+x"))', batch)
        self.assertIn('block([simp:true', batch)
        self.assertEqual(batch.count('block([simp:false'), 3)
        self.assertIn('ATNumAbsolute(parse_string("x+1"),parse_string("1+x"),parse_string("0.05"))', batch)
        self.assertIn('ATNumRelative(parse_string("x+1"),parse_string("1+x"),parse_string("0.1"))', batch)
        self.assertIn('ATNumDecPlaces(parse_string("1.200"),parse_string("1.2"),parse_string("3"),"1.200")', batch)
        self.assertIn('STACKNATIVE-BEGIN|7|6', batch)
        self.assertIn('STACKNATIVE-END|7|6', batch)
        self.assertIn('[\\\"error\\\",\\\"cas_evaluation\\\",null]', batch)

    def test_protocol_preserves_note_and_controlled_native_error(self):
        rows = [case(), case("2")]
        output = ("Maxima startup\nSTACKNATIVE-BEGIN|0|2\n"
                  f"STACKNATIVE|{rows[0]['id']}|[true,false,\"A pipe | and \\\"quote\\\". \"]\n"
                  f"STACKNATIVE|{rows[1]['id']}|[\"error\",\"cas_evaluation\",null]\n"
                  "STACKNATIVE-END|0|2\n")
        parsed = native.parse_output(output, rows, 0)
        self.assertEqual(parsed[0]["answer_note"], 'A pipe | and "quote". ')
        self.assertEqual(parsed[0]["status"], "ok")
        self.assertIs(parsed[0]["controlled_error"], False)
        self.assertEqual(parsed[1]["status"], "error")

    def test_controlled_at_error_requires_both_flags_and_an_anchored_note(self):
        samples = [
            (False, False, "ATAlgEquiv_STACKERROR_SAns. ", True),
            (False, False, "ATNumerical_STACKERROR_tol.", True),
            (False, False, "ATNumDecPlaces_OptNotInt.", True),
            (False, False, "STACKERROR_OPTION.", True),
            (False, False, "ATEqualComAss (AlgEquiv-false). ", False),
            (False, False, "ATAlgEquiv_STACKERROR_SAns. other note", False),
            (True, False, "ATAlgEquiv_STACKERROR_SAns.", False),
            (False, True, "STACKERROR_OPTION.", False),
            (False, False, ["ATAlgEquiv_STACKERROR_SAns."], False),
        ]
        for valid, correct, note, expected in samples:
            with self.subTest(note=note, valid=valid, correct=correct):
                self.assertIs(native._controlled_at_error(valid, correct, note), expected)
        row = case()
        output = ("STACKNATIVE-BEGIN|0|1\n"
                  f"STACKNATIVE|{row['id']}|[false,false,\"ATAlgEquiv_STACKERROR_SAns. \"]\n"
                  "STACKNATIVE-END|0|1\n")
        observed = native.parse_output(output, [row], 0)[0]
        self.assertEqual(observed["status"], "ok")
        self.assertIs(observed["controlled_error"], True)

    def test_fail_closed_on_incomplete_duplicate_or_bad_output(self):
        row = case()
        marker = f"STACKNATIVE|{row['id']}|[true,true,\"\"]\n"
        valid = "STACKNATIVE-BEGIN|1|1\n" + marker + "STACKNATIVE-END|1|1\n"
        self.assertEqual(native.parse_output(valid, [row], 1)[0]["correct"], True)
        echoed = ("print(\"STACKNATIVE-BEGIN|1|1\")\n"
                  f'block([simp:true],print(sconcat("STACKNATIVE|{row["id"]}|", "[true,true,\\\"\\\"]")))$\n'
                  '(%i9) print("STACKNATIVE-END|1|1")$\n')
        self.assertEqual(native.parse_output(echoed + valid, [row], 1)[0]["correct"], True)
        for bad in (valid.replace("STACKNATIVE-END|1|1\n", ""),
                    valid.replace(marker, marker + marker),
                    valid.replace("[true,true,\"\"]", "[1,true,\"\"]"),
                    valid.replace("[true,true,\"\"]", "{broken}"),
                    valid + "STACKNATIVE|bad marker\n",
                    valid + "STACKNATIVE-BEGIN|1|oops\n",
                    valid.replace("BEGIN|1|1", "BEGIN|1|2")):
            with self.subTest(bad=bad[-80:]), self.assertRaises(native.NativeProtocolError):
                native.parse_output(bad, [row], 1)

    def test_timeout_and_process_exit_are_distinct(self):
        row = case()
        partial = f"STACKNATIVE-BEGIN|0|1\nSTACKNATIVE|{row['id']}|[true,true,\"\"]\n"
        timeout = subprocess.TimeoutExpired("maxima", 2, output=partial.encode())
        with patch.object(native.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(native.NativeProcessError, f"last_case_id={row['id']}"):
                native._command(["maxima"], 2)
        response = subprocess.CompletedProcess(["maxima"], 13, stdout="partial", stderr="fatal")
        with patch.object(native.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(native.NativeProcessError, "exit 13"):
                native._command(["maxima"], 2)

    def test_runner_orders_all_rows_and_labels_direct_cas_scope(self):
        rows = [case(test="NotImplemented"), case("2"), case("3", student=""), case("4")]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            maxima_dir = source / "stack/maxima"
            maxima_dir.mkdir(parents=True)
            (maxima_dir / "stacklocallinux.mac").write_text("", encoding="utf-8")
            (maxima_dir / "stackmaxima.mac").write_text("stackmaximaversion:123$", encoding="utf-8")

            def command(argv, timeout):
                if argv[0] == "git":
                    return native.STACK_SHA + "\n"
                if "--version" in argv:
                    return "Maxima 5.x\n"
                batch = Path(argv[-1].removeprefix("--batch=")).read_text()
                self.assertEqual(len(re.findall(r'ATAlgEquiv\(parse_string\("x\+1"\),parse_string\("1\+x"\)\)', batch)), 1)
                number = int(re.search(r"STACKNATIVE-BEGIN\|(\d+)\|1", batch).group(1))
                current = rows[1] if number == 0 else rows[3]
                mark = "true" if number == 0 else "false"
                return (f"STACKNATIVE-BEGIN|{number}|1\n"
                        f"STACKNATIVE|{current['id']}|[true,{mark},\"\"]\n"
                        f"STACKNATIVE-END|{number}|1\n")

            with patch.object(native, "_command", side_effect=command), patch.object(native.shutil, "which", return_value="/usr/bin/maxima"):
                result = native.run_native(rows, source, jobs=1)
        self.assertEqual(result["metadata"]["reference_layer"], "direct_official_maxima_AT")
        self.assertEqual(result["metadata"]["execution_isolation"], "fresh_maxima_process_per_case")
        self.assertEqual(result["metadata"]["native_scope_sha256"], native.scope_sha256(rows))
        self.assertEqual([x["status"] for x in result["observations"]], ["unavailable", "ok", "unavailable", "ok"])
        self.assertEqual(result["summary"], {"total": 4, "ok": 2, "error": 0, "unavailable": 2})

    def test_runner_process_failure_names_batch_and_fixture_ordinals(self):
        row = {**case(), "ordinal": 42}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            maxima_dir = source / "stack/maxima"
            maxima_dir.mkdir(parents=True)
            (maxima_dir / "stacklocallinux.mac").write_text("", encoding="utf-8")
            (maxima_dir / "stackmaxima.mac").write_text("stackmaximaversion:123$", encoding="utf-8")
            calls = iter([native.STACK_SHA, "Maxima 5.x"])

            def command(argv, timeout):
                if "--batch=" in argv[-1]:
                    raise native.NativeProcessError("timeout after 300s")
                return next(calls)

            with patch.object(native, "_command", side_effect=command), patch.object(native.shutil, "which", return_value="/usr/bin/maxima"):
                with self.assertRaisesRegex(native.NativeProcessError, rf"case process 0 \(fixture ordinal 42, id {row['id']}\): timeout"):
                    native.run_native([row], source)

    def test_cli_writes_failure_document_when_maxima_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "native.json"
            fixture = ROOT / "tests/native_compliance/fixtures.json"
            with patch.object(run_compliance_maxima, "run_native", side_effect=native.NativeProcessError("missing")):
                status = run_compliance_maxima.main(["--fixture", str(fixture), "--stack-source", str(ROOT),
                                                     "--output", str(report)])
            self.assertEqual(status, 1)
            data = json.loads(report.read_text())
            self.assertEqual(data["observations"], [])
            self.assertIn("NativeProcessError: missing", data["error"])


if __name__ == "__main__":
    unittest.main()
