"""Compare the supported scalar answer-test subset against native STACK/Maxima.

Requires an installed Maxima and an exact, pinned checkout of upstream STACK.
No stored expected marks are used: both implementations evaluate every case.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import sympy


STACK_SHA = "10d323311b7f39fb7b092dd10ce75f7d8632f525"
TESTS = {"AlgEquiv": 2, "EqualComAss": 2, "FacForm": 3, "SingleFrac": 2, "LowestTerms": 2}
MARKER = re.compile(r"^\s*STACKREF\|([a-z][a-z0-9_]*)\|(true|false)\|(true|false)\s*$", re.M)
CASE_ID = re.compile(r"[a-z][a-z0-9_]*\Z")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from native_compliance.maxima_runner import prepare_logic


def load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Reference fixture must be a nonempty JSON array")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "test", "student", "teacher", "options", "source"}:
            raise ValueError(f"Malformed reference case: {case!r}")
        if not isinstance(case["id"], str) or not CASE_ID.fullmatch(case["id"]) or case["id"] in seen:
            raise ValueError(f"Duplicate or invalid case id: {case['id']!r}")
        seen.add(case["id"])
        if case["test"] not in TESTS:
            raise ValueError(f"Unsupported answer test: {case['test']!r}")
        for key in ("student", "teacher", "options", "source"):
            if not isinstance(case[key], str):
                raise ValueError(f"{case['id']}: {key} must be a string")
        if not case["student"] or not case["teacher"] or not case["source"]:
            raise ValueError(f"{case['id']}: student, teacher and source are required")
        # Fixture expressions are trusted source-controlled data, but never
        # let a malformed entry inject a second Maxima command into the batch.
        for key in ("student", "teacher", "options"):
            if any(char in case[key] for char in ';$\n\r"'):
                raise ValueError(f"{case['id']}: unsafe Maxima expression in {key}")
        if (case["test"] == "FacForm") != bool(case["options"]):
            raise ValueError(f"{case['id']}: FacForm alone requires an option")
    if set(TESTS) - {case["test"] for case in cases}:
        raise ValueError("Reference fixture must exercise every supported test")
    return cases


def parse_maxima_output(output: str, cases: list[dict]) -> dict[str, tuple[bool, bool]]:
    expected = {case["id"] for case in cases}
    values: dict[str, tuple[bool, bool]] = {}
    for match in MARKER.finditer(output):
        case_id = match.group(1)
        if case_id not in expected or case_id in values:
            raise RuntimeError(f"Unexpected or duplicate Maxima result for {case_id}")
        values[case_id] = (match.group(2) == "true", match.group(3) == "true")
    if values.keys() != expected:
        raise RuntimeError(f"Missing Maxima results: {', '.join(sorted(expected - values.keys()))}; output tail:\n{output[-8000:]}")
    return values


def _maxima_literal(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def maxima_batch(source: Path, cases: list[dict], home: Path) -> str:
    """Bootstrap official stacklocallinux.mac, which loads stackmaxima.mac.

    The official loader expects the checkout under maxima_userdir, so create
    that symlink in a temporary directory instead of altering upstream files.
    """
    (home / "moodle-qtype_stack-master").symlink_to(source, target_is_directory=True)
    (home / "tmp").mkdir()
    (home / "plots").mkdir()
    loader = home / "moodle-qtype_stack-master/stack/maxima/stacklocallinux.mac"
    lines = [
        "display2d:false$",
        f"maxima_userdir:{_maxima_literal(str(home))}$",
        f"load({_maxima_literal(str(loader))})$",
        "display2d:false$",
        "simp:false$",
    ]
    for case in cases:
        args = ",".join(prepare_logic(value) for value in
                        [case["student"], case["teacher"]] + ([case["options"]] if TESTS[case["test"]] == 3 else []))
        call = f'AT{case["test"]}({args})'
        # [1]/[2] are the actual validity and raw mark from the upstream AT.
        # A failing call leaves its result marker missing and fails the run.
        lines.append(
            f'block([stack_ref_result],stack_ref_result:{call},'
            f'print(sconcat("STACKREF|{case["id"]}|",'
            'string(stack_ref_result[1]),"|",string(stack_ref_result[2]))))$'
        )
    lines.append('quit()$')
    return "\n".join(lines) + "\n"


def _command_output(command: list[str], *, timeout: int) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{' '.join(command[:2])} failed ({result.returncode}):\n{(result.stdout + result.stderr)[-8000:]}")
    return result.stdout + result.stderr


def compare(source: Path, maxima: str, cases: list[dict]) -> dict:
    sys.path.insert(0, str(ROOT / "_extensions/stack-sympy"))
    from stack_sympy.assessment import answer_test

    if not (source / "stack/maxima/stacklocallinux.mac").is_file():
        raise RuntimeError(f"Not an official STACK source checkout: {source}")
    checkout = _command_output(["git", "-C", str(source), "rev-parse", "HEAD"], timeout=10).strip()
    if checkout != STACK_SHA:
        raise RuntimeError(f"STACK source must be pinned to {STACK_SHA}; got {checkout}")
    executable = shutil.which(maxima)
    if executable is None:
        raise RuntimeError(f"Maxima executable is required: {maxima!r}")
    report = {
        "stack_sha": checkout,
        "stack_library_version": re.search(r"stackmaximaversion:(\d+)", (source / "stack/maxima/stackmaxima.mac").read_text()).group(1),
        "maxima_version": _command_output([executable, "--version"], timeout=15).strip(),
        "sympy_version": sympy.__version__,
        "case_count": len(cases),
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="stack-maxima-ref-") as work:
        home = Path(work)
        batch = home / "compare.mac"
        batch.write_text(maxima_batch(source, cases, home), encoding="utf-8")
        output = _command_output([executable, "--very-quiet", f"--batch={batch}"], timeout=180)
    reference = parse_maxima_output(output, cases)
    for case in cases:
        native = dict(zip(("cas_valid", "correct"), reference[case["id"]]))
        try:
            python_result = answer_test(case["test"], case["student"], case["teacher"], case["options"])
            # The adapter's `valid` concerns student input syntax; STACK's
            # first AT result instead represents answer-test applicability.
            # EqualComAss can return false here on a well-formed wrong value.
            local = {"cas_valid": python_result.get("cas_valid", python_result["valid"]),
                     "correct": python_result["correct"]}
            input_valid = python_result["valid"]
            error = None
        except Exception as exc:
            local = None
            input_valid = None
            error = f"{type(exc).__name__}: {exc}"
        report["cases"].append({**case, "maxima": native, "sympy": local,
                                "adapter_input_valid": input_valid, "error": error,
                                "match": native == local and error is None})
    report["passed"] = all(case["match"] for case in report["cases"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-source", required=True, type=Path, help="official STACK checkout at the pinned SHA")
    parser.add_argument("--maxima", default="maxima")
    parser.add_argument("--cases", type=Path, default=ROOT / "tests/reference_cases.json")
    parser.add_argument("--report", type=Path, default=ROOT / "test-results/maxima-reference.json")
    args = parser.parse_args()
    report: dict = {"passed": False}
    try:
        report = compare(args.stack_source.resolve(), args.maxima, load_cases(args.cases))
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if "error" in report:
        print(f"Maxima reference comparison failed: {report['error']}", file=sys.stderr)
    else:
        print(f"STACK {report['stack_sha']} / {report['maxima_version']} / SymPy {report['sympy_version']}")
        for case in report["cases"]:
            if not case["match"]:
                print(f"{case['id']} ({case['source']}): AT{case['test']}({case['student']}, {case['teacher']}, {case['options']!r}) "
                      f"Maxima={case['maxima']} SymPy={case['sympy']} error={case['error']}", file=sys.stderr)
        print(f"Matched {sum(c['match'] for c in report['cases'])}/{report['case_count']} native STACK answer tests")
    print(f"Report: {args.report}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
