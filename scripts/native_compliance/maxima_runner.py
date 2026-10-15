"""Observe the pinned STACK answer-test functions in native Maxima.

This runs official ``AT*`` functions, not the Moodle/PHP answer-test
controller or its input validation.  A result therefore describes that CAS
layer only.  The report layer independently compares desired fixture scores,
Python behaviour and these native observations.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


STACK_SHA = "10d323311b7f39fb7b092dd10ce75f7d8632f525"
# controller.class.php $pops, columns: required options, CAS options, simp,
# required raw.  Only families implemented by stack-sympy are in scope.
TESTS = {
    "AlgEquiv": (False, True, False),
    "EqualComAss": (False, False, False),
    "FacForm": (True, False, False),
    "SingleFrac": (False, False, False),
    "LowestTerms": (False, False, False),
    "NumAbsolute": (True, True, False),
    "NumRelative": (True, True, False),
    "NumDecPlaces": (True, False, True),
}
CASE_ID = re.compile(r"[0-9a-f]{64}-[1-9][0-9]*\Z")
RESULT = re.compile(r"^\s*STACKNATIVE\|([0-9a-f]{64}-[1-9][0-9]*)\|(.+?)\s*$")
BEGIN = re.compile(r"^\s*STACKNATIVE-BEGIN\|(\d+)\|(\d+)\s*$")
END = re.compile(r"^\s*STACKNATIVE-END\|(\d+)\|(\d+)\s*$")
CONTROLLED_AT_ERROR = re.compile(
    r"(?:AT[A-Za-z0-9]+_STACKERROR_(?:SAns|TAns|Opt|Raw|tol)"
    r"|ATNumDecPlaces_OptNotInt|STACKERROR_OPTION)\.\Z"
)
UNSAFE = re.compile(r"[;:$\"\r\n]|/\*|\*/|\b(?:load|system|kill|batch|file_search_maxima|with_stdout)\s*\(", re.I)
CHUNK_SIZE = 100


class NativeProtocolError(RuntimeError):
    """Native process output is incomplete or malformed."""


class NativeProcessError(RuntimeError):
    """Maxima failed before a complete set of observations was collected."""


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _unbalanced_delimiters(value: str) -> bool:
    stack: list[str] = []
    opening = {"(": ")", "[": "]", "{": "}"}
    for char in value:
        if char in opening:
            stack.append(opening[char])
        elif char in ")]}" and (not stack or stack.pop() != char):
            return True
    return bool(stack)


def _unavailable(case: dict) -> str | None:
    """Identify input paths that require PHP AST validation/preparation.

    The direct CAS oracle must never label those as a Moodle observation.
    Empty inputs and special PHP input notation cannot be inferred from a
    raw Maxima call. Runtime parse failures are marked as native errors.
    """
    if case["test"] not in TESTS:
        return "test_family_not_implemented"
    if not case["student"].strip() or not case["teacher"].strip():
        return "empty_answer_requires_php_controller"
    if TESTS[case["test"]][0] and not case["options"].strip() and case["test"] not in {"NumAbsolute", "NumRelative"}:
        return "missing_option_requires_php_controller"
    for field in ("student", "teacher", "options"):
        if not case[field].isascii():
            return f"non_ascii_requires_php_parser_{field}"
        if "#pm#" in case[field]:
            return f"plus_minus_requires_php_parser_{field}"
        if case[field].strip() == "1/0":
            return f"undefined_expression_requires_php_controller_{field}"
        if _unbalanced_delimiters(case[field]):
            return f"malformed_expression_requires_php_parser_{field}"
        if UNSAFE.search(case[field]):
            return f"unsafe_or_php_preprocessed_{field}"
    return None


def validate_cases(cases: list[dict]) -> None:
    if not cases:
        raise ValueError("No fixture cases")
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id) or case_id in seen:
            raise ValueError(f"Invalid or duplicate case ID: {case_id!r}")
        seen.add(case_id)
        if not isinstance(case.get("test"), str):
            raise ValueError(f"{case_id}: test must be a string")
        for field in ("student", "teacher", "options"):
            if not isinstance(case.get(field), str):
                raise ValueError(f"{case_id}: {field} must be a string")


def scope_sha256(cases: list[dict]) -> str:
    """Fingerprint ordered direct-call eligibility, including exclusion reasons."""
    validate_cases(cases)
    scope = [[case["id"], _unavailable(case) or "available"] for case in cases]
    canonical = json.dumps(scope, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _call(case: dict) -> str:
    test = case["test"]
    requires_option, simplifying, raw = TESTS[test]
    args = [f"parse_string({_literal(case['student'])})", f"parse_string({_literal(case['teacher'])})"]
    if requires_option:
        option = case["options"] or "0.05"  # controller default for NumAbsolute/Relative
        args.append(f"parse_string({_literal(option)})")
    if raw:
        # PHP uses get_inputform(true, 1).  For supported plain numeric input
        # the fixture's spelling is the pertinent raw input; nontrivial AST
        # normalization remains a separate PHP-controller limitation.
        args.append(_literal(case["student"]))
    return f"AT{test}({','.join(args)})"


def _controlled_at_error(valid: bool, correct: bool, note: str | list) -> bool:
    """Recognize an explicit failed AT's controlled diagnostic, never a mark alone."""
    return (not valid and not correct and isinstance(note, str)
            and bool(CONTROLLED_AT_ERROR.fullmatch(note.strip())))


def make_batch(source: Path, cases: list[dict], home: Path, batch_number: int) -> str:
    """Create an isolated Maxima batch with bounded, JSON-encoded records."""
    (home / "moodle-qtype_stack-master").symlink_to(source, target_is_directory=True)
    (home / "tmp").mkdir()
    (home / "plots").mkdir()
    loader = home / "moodle-qtype_stack-master/stack/maxima/stacklocallinux.mac"
    lines = [
        "display2d:false$",
        f"maxima_userdir:{_literal(str(home))}$",
        f"load({_literal(str(loader))})$",
        "display2d:false$",
        "linel:10000$",
        f'print("STACKNATIVE-BEGIN|{batch_number}|{len(cases)}")$',
    ]
    for case in cases:
        test = case["test"]
        simp = "true" if TESTS[test][1] else "false"
        # errcatch encloses parsing and AT evaluation, so one CAS error does
        # not erase subsequent observations.  The third result is the native
        # answer note.  STACK's result[1] is test applicability, not syntax
        # validity of the original student input.
        marker = _literal(f"STACKNATIVE|{case['id']}|")
        bad = _literal('["error","cas_evaluation",null]')
        malformed = _literal('["error","malformed_at_result",null]')
        expression = _call(case)
        lines.append(
            f"block([simp:{simp},_native_result,_native_value,_native_json],"
            f"_native_result:errcatch({expression}),"
            f"if _native_result=[] then print(sconcat({marker},{bad})) "
            f"else (_native_value:first(_native_result),"
            f"if not listp(_native_value) or length(_native_value)<4 then "
            f"print(sconcat({marker},{malformed})) "
            f"else (_native_json:errcatch(stackjson_stringify("
            f"[_native_value[1],_native_value[2],_native_value[3]])),"
            f"if _native_json=[] then print(sconcat({marker},{malformed})) "
            f"else print(sconcat({marker},first(_native_json))))))$"
        )
    lines.extend([f'print("STACKNATIVE-END|{batch_number}|{len(cases)}")$', 'quit()$'])
    return "\n".join(lines) + "\n"


def parse_output(output: str, cases: list[dict], batch_number: int) -> list[dict]:
    expected = {c["id"] for c in cases}
    observations: dict[str, dict] = {}
    beginnings = endings = 0
    for line in output.splitlines():
        match = BEGIN.fullmatch(line)
        if match:
            if (int(match[1]), int(match[2])) != (batch_number, len(cases)):
                raise NativeProtocolError(f"Wrong begin marker: {line}")
            beginnings += 1
            continue
        match = END.fullmatch(line)
        if match:
            if (int(match[1]), int(match[2])) != (batch_number, len(cases)):
                raise NativeProtocolError(f"Wrong end marker: {line}")
            endings += 1
            continue
        match = RESULT.fullmatch(line)
        if match:
            case_id, payload = match.groups()
            if case_id not in expected or case_id in observations:
                raise NativeProtocolError(f"Unexpected or duplicate result: {case_id}")
            try:
                result = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise NativeProtocolError(f"Invalid JSON result for {case_id}: {exc}") from exc
            if not isinstance(result, list) or len(result) != 3:
                raise NativeProtocolError(f"Malformed result for {case_id}: {result!r}")
            case = next(c for c in cases if c["id"] == case_id)
            observation = {"case_id": case_id, "test": case["test"]}
            if result[0] == "error" and isinstance(result[1], str):
                observation.update(status="error", error=result[1])
            elif type(result[0]) is bool and type(result[1]) is bool and isinstance(result[2], (str, list)):
                observation.update(status="ok", cas_valid=result[0], correct=result[1], answer_note=result[2],
                                   controlled_error=_controlled_at_error(result[0], result[1], result[2]))
            else:
                raise NativeProtocolError(f"Invalid AT value for {case_id}: {result!r}")
            observations[case_id] = observation
            continue
        # --batch echoes input commands such as print("STACKNATIVE-BEGIN|...").
        # Only an output line beginning with our marker prefix is a malformed
        # marker; all other source echoes and Maxima diagnostics are noise.
        if line.lstrip().startswith(("STACKNATIVE|", "STACKNATIVE-BEGIN|", "STACKNATIVE-END|")):
            raise NativeProtocolError(f"Malformed native marker: {line[:300]}")
    if beginnings != 1 or endings != 1 or observations.keys() != expected:
        missing = sorted(expected - observations.keys())
        raise NativeProtocolError(f"Incomplete batch {batch_number}: begin={beginnings}, end={endings}, missing={missing}; output tail={output[-2000:]!r}")
    return [observations[c["id"]] for c in cases]


def _command(command: list[str], timeout: int) -> str:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise NativeProcessError(f"Maxima timeout after {timeout}s: {command[0]}") from exc
    if proc.returncode:
        raise NativeProcessError(f"Maxima exit {proc.returncode}: {(proc.stdout + proc.stderr)[-3000:]}")
    return proc.stdout + proc.stderr


def run_native(cases: list[dict], source: Path, maxima: str = "maxima", *, chunk_size: int = CHUNK_SIZE,
               timeout: int = 300) -> dict:
    """Return independent native observations and version/provenance metadata."""
    validate_cases(cases)
    if chunk_size < 1 or timeout < 1:
        raise ValueError("chunk_size and timeout must be positive")
    source = source.resolve()
    if not (source / "stack/maxima/stacklocallinux.mac").is_file():
        raise NativeProcessError(f"Not a STACK Maxima source checkout: {source}")
    checkout = _command(["git", "-C", str(source), "rev-parse", "HEAD"], 10).strip()
    if checkout != STACK_SHA:
        raise NativeProcessError(f"Expected pinned STACK {STACK_SHA}, got {checkout}")
    executable = shutil.which(maxima)
    if executable is None:
        raise NativeProcessError(f"Maxima executable unavailable: {maxima!r}")
    version = _command([executable, "--version"], 15).strip()
    library = (source / "stack/maxima/stackmaxima.mac").read_text(encoding="utf-8")
    library_match = re.search(r"stackmaximaversion:(\d+)", library)
    if not library_match:
        raise NativeProcessError("Missing STACK Maxima library version")
    observations: list[dict] = []
    runnable: list[dict] = []
    unavailable: dict[str, str] = {}
    for case in cases:
        reason = _unavailable(case)
        if reason:
            unavailable[case["id"]] = reason
        else:
            runnable.append(case)
    for offset in range(0, len(runnable), chunk_size):
        chunk = runnable[offset:offset + chunk_size]
        batch_number = offset // chunk_size
        with tempfile.TemporaryDirectory(prefix="stack-compliance-maxima-") as directory:
            home = Path(directory)
            batch = home / "native.mac"
            batch.write_text(make_batch(source, chunk, home, batch_number), encoding="utf-8")
            output = _command([executable, "--very-quiet", f"--batch={batch}"], timeout)
        observations.extend(parse_output(output, chunk, batch_number))
    by_id = {row["case_id"]: row for row in observations}
    for case in cases:
        if case["id"] in unavailable:
            by_id[case["id"]] = {"case_id": case["id"], "test": case["test"],
                                "status": "unavailable", "reason": unavailable[case["id"]]}
    ordered = [by_id[case["id"]] for case in cases]
    return {"schema_version": 1, "engine": "maxima",
            "metadata": {"reference_layer": "direct_official_maxima_AT", "stack_sha": checkout,
                         "stack_library_version": library_match[1], "maxima_version": version,
                         "native_scope_sha256": scope_sha256(cases)},
            "observations": ordered,
            "summary": {"total": len(ordered), "ok": sum(r["status"] == "ok" for r in ordered),
                        "error": sum(r["status"] == "error" for r in ordered),
                        "unavailable": len(unavailable)}}
