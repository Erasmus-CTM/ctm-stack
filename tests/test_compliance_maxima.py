"""Protocol tests for the native STACK oracle (Maxima runs in hosted CI)."""

from contextlib import redirect_stdout
import io
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

PROBE_VALUES = ["%i", "%i", "1/(1+%i)", "1/(1+%i)",
                [True, False, "ATLowestTerms_not_rat. "],
                [True, False, "ATLowestTerms_not_rat. "],
                [True, False, "ATLowestTerms_not_rat. "],
                [True, True, ""], [True, False, ""]]


def warmup_output():
    return ("STACKNATIVE-BEGIN|0|0\nSTACKNATIVE-DIAG|" + json.dumps(PROBE_VALUES, separators=(",", ":"))
            + "\nSTACKNATIVE-END|0|0\n")


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
                         "375e45aa5b73d1dd4d514807d583b6f3322b915f0c73b19a706339d27b237fd7")
        self.assertEqual(native._unavailable(case(test="NumAbsolute", options="")), None)
        self.assertEqual(native._unavailable(case(test="NotImplemented")), "test_family_not_implemented")
        self.assertEqual(native._unavailable(case(student="")), "empty_answer_requires_php_controller")
        self.assertIsNotNone(native._unavailable(case(student="x);quit()$")))
        self.assertEqual(native._unavailable(case(student="Ω")), "non_ascii_requires_php_parser_student")
        self.assertEqual(native._unavailable(case(student="x#pm#1")), "plus_minus_requires_php_parser_student")
        self.assertEqual(native._unavailable(case(student="1/0")), "undefined_expression_requires_php_controller_student")
        self.assertEqual(native._unavailable(case(student="(x")), "malformed_expression_requires_php_parser_student")

    def test_logic_preparation_is_token_aware_and_fingerprinted(self):
        source = 'a=0 or b=0 and not c=1'
        self.assertEqual(native.prepare_logic(source), 'a=0 nounor b=0 nounand nounnot c=1')
        preserved = 'floor(x)+ordinary+nounor+notable+"and or not"'
        self.assertEqual(native.prepare_logic(preserved), preserved)
        self.assertIn('eval_string("a=0 nounor b=0")',
                      native._call(case(student='a=0 or b=0', teacher='a*b=0')))
        self.assertEqual(native.INPUT_PREPARATION, 'stack-logic-nouns-v1')

    def test_batch_arguments_simplification_raw_and_default(self):
        cases = [case(), case("2", "EqualComAss"), case("3", "FacForm", options="x"),
                 case("4", "NumAbsolute"), case("5", "NumRelative", options="0.1"),
                 case("6", "NumDecPlaces", student="1.200", teacher="1.2", options="3")]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            batch = native.make_batch(ROOT, cases, home, 7)
        self.assertIn('ATAlgEquiv(eval_string("x+1"),eval_string("1+x"))', batch)
        self.assertIn('block([simp:true', batch)
        self.assertEqual(batch.count('block([simp:false'), 3)
        self.assertIn('ATNumAbsolute(eval_string("x+1"),eval_string("1+x"),eval_string("0.05"))', batch)
        self.assertIn('ATNumRelative(eval_string("x+1"),eval_string("1+x"),eval_string("0.1"))', batch)
        self.assertIn('ATNumDecPlaces(eval_string("1.200"),eval_string("1.2"),eval_string("3"),"1.200")', batch)
        self.assertIn('ATLowestTerms(eval_string("1/(1+i)"),eval_string("(1-i)/2"))',
                      native._call(case(test="LowestTerms", student="1/(1+i)", teacher="(1-i)/2")))
        self.assertIn('STACKNATIVE-BEGIN|7|6', batch)
        self.assertIn('STACKNATIVE-END|7|6', batch)
        self.assertIn('[\\\"error\\\",\\\"cas_evaluation\\\",null]', batch)

    def test_warmup_probe_is_separate_from_fixture_results(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = native.make_warmup_batch(ROOT, Path(directory))
        self.assertIn('STACKNATIVE-BEGIN|0|0', batch)
        self.assertIn('simp:false$\nprint(sconcat("STACKNATIVE-DIAG|"', batch)
        self.assertIn('ATLowestTerms(1/(1+i),(1-i)/2)', batch)
        self.assertIn('ATLowestTerms(ev(parse_string("1/(1+i)"),simp:false)', batch)
        self.assertIn('ATEqualComAss(ev(parse_string("cos(0)"),simp:false)', batch)
        self.assertIn('ATEqualComAss(ev(parse_string("sqrt(3)"),simp:false)', batch)
        self.assertEqual(native.parse_output(warmup_output(), [], 0), [])
        self.assertEqual(native.parse_probe_output(warmup_output())["literal_lowest_terms"], PROBE_VALUES[4])
        with self.assertRaises(native.NativeProtocolError):
            native.parse_probe_output("STACKNATIVE-BEGIN|0|0\nSTACKNATIVE-END|0|0\n")

    def test_standalone_probe_has_two_stage_and_inline_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = native.make_standalone_probe_batch(ROOT, Path(directory))
        self.assertIn('ATLowestTerms(1/(1+i),(1-i)/2)', batch)
        self.assertIn('ATLowestTerms(eval_string("1/(1+i)"),eval_string("(1-i)/2"))', batch)
        self.assertIn('_probe_sa:parse_string("1/(1+i)"),_probe_ta:parse_string("(1-i)/2")', batch)
        self.assertIn('_probe_sa:eval_string("1/(1+i)"),_probe_ta:eval_string("(1-i)/2")', batch)
        self.assertIn('ATEqualComAss(_probe_sa,_probe_ta)', batch)
        self.assertIn('block([simp:true,_probe_result],_probe_result:errcatch(ATAlgEquiv', batch)
        self.assertIn('makelist(significantfigures(%pi,i),i,8)', batch)
        self.assertIn('STACKNATIVE-PROBE|', batch)
        self.assertNotIn('STACKNATIVE-DIAG|', batch)
        self.assertEqual(batch.count('STACKNATIVE-END|0|0'), 1)

    def test_standalone_probe_protocol_and_cli_are_independent_of_fixture(self):
        names = native.STANDALONE_PROBE_KEYS
        values = [[name, name] for name in names]
        output = ("STACKNATIVE-BEGIN|0|0\n"
                  + "STACKNATIVE-PROBE|" + json.dumps(values, separators=(",", ":"))
                  + "\nSTACKNATIVE-END|0|0\n")
        self.assertEqual(native.parse_output(output, [], 0), [])
        self.assertEqual(native.parse_standalone_probe_output(output)["i_binding"], "i_binding")
        for invalid in (output.replace("STACKNATIVE-PROBE|", "print(\"STACKNATIVE-PROBE|"),
                        output.replace("\nSTACKNATIVE-END", "\nSTACKNATIVE-PROBE|[]\nSTACKNATIVE-END"),
                        output.replace('[["i_binding","i_binding"]', '[["i_binding","wrong"]')
                        .replace('["parse_i","parse_i"]', '["i_binding","duplicate"]'),
                        "STACKNATIVE-PROBE|{broken}\n"):
            with self.subTest(invalid=invalid[-80:]), self.assertRaises(native.NativeProtocolError):
                native.parse_standalone_probe_output(invalid)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "probe.json"
            bogus_fixture = Path(directory) / "missing-fixture.json"
            fake = {"schema_version": 1, "engine": "maxima_diagnostic", "probe": {"i_binding": "%i"}}
            with patch.object(run_compliance_maxima, "run_standalone_probe", return_value=fake) as run:
                status = run_compliance_maxima.main([
                    "--probe-only", "--fixture", str(bogus_fixture),
                    "--stack-source", str(ROOT), "--output", str(destination)])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(destination.read_text()), fake)
            run.assert_called_once()
            with patch.object(run_compliance_maxima, "ROOT", Path(directory)), patch.object(
                    run_compliance_maxima, "run_standalone_probe", return_value=fake):
                status = run_compliance_maxima.main([
                    "--probe-only", "--fixture", str(bogus_fixture),
                    "--stack-source", str(ROOT)])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads((Path(directory) / "test-results/compliance/maxima-loader-probe.json")
                                        .read_text()), fake)
            self.assertFalse((Path(directory) / "test-results/compliance/maxima.json").exists())

    def test_standalone_probe_runs_only_one_pinned_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            maxima_dir = source / "stack/maxima"
            maxima_dir.mkdir(parents=True)
            (maxima_dir / "stacklocallinux.mac").write_text("", encoding="utf-8")
            batches = []

            def command(argv, timeout):
                if argv[0] == "git":
                    return native.STACK_SHA + "\n"
                if "--version" in argv:
                    return "Maxima 5.x\n"
                batches.append(Path(argv[-1].removeprefix("--batch=")).read_text())
                values = [[name, name] for name in native.STANDALONE_PROBE_KEYS]
                return ("STACKNATIVE-BEGIN|0|0\nSTACKNATIVE-PROBE|"
                        + json.dumps(values) + "\nSTACKNATIVE-END|0|0\n")

            with patch.object(native, "_command", side_effect=command), patch.object(
                    native.shutil, "which", return_value="/usr/bin/maxima"):
                report = native.run_standalone_probe(source)
        self.assertEqual(report["engine"], "maxima_diagnostic")
        self.assertEqual(report["metadata"]["stack_sha"], native.STACK_SHA)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].count('load("'), 1)
        self.assertNotIn("STACKNATIVE|", batches[0])

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
            calls = []

            def command(argv, timeout):
                if argv[0] == "git":
                    return native.STACK_SHA + "\n"
                if "--version" in argv:
                    return "Maxima 5.x\n"
                batch = Path(argv[-1].removeprefix("--batch=")).read_text()
                if 'STACKNATIVE-BEGIN|0|0' in batch:
                    calls.append("warmup")
                    return warmup_output()
                calls.append("case")
                self.assertEqual(len(re.findall(r'ATAlgEquiv\(eval_string\("x\+1"\),eval_string\("1\+x"\)\)', batch)), 1)
                number = int(re.search(r"STACKNATIVE-BEGIN\|(\d+)\|1", batch).group(1))
                current = rows[1] if number == 0 else rows[3]
                mark = "true" if number == 0 else "false"
                return (f"STACKNATIVE-BEGIN|{number}|1\n"
                        f"STACKNATIVE|{current['id']}|[true,{mark},\"\"]\n"
                        f"STACKNATIVE-END|{number}|1\n")

            progress = io.StringIO()
            with patch.object(native, "_command", side_effect=command), patch.object(
                    native.shutil, "which", return_value="/usr/bin/maxima"), redirect_stdout(progress):
                result = native.run_native(rows, source, jobs=1)
        self.assertEqual(result["metadata"]["reference_layer"], "direct_official_maxima_AT")
        self.assertEqual(result["metadata"]["execution_isolation"], "fresh_maxima_process_per_case")
        self.assertEqual(calls, ["warmup", "case", "case"])
        self.assertRegex(progress.getvalue(), r"Native cases: 2/2 completed in [0-9.]+s")
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
                    if 'STACKNATIVE-BEGIN|0|0' in Path(argv[-1].removeprefix("--batch=")).read_text():
                        return warmup_output()
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
