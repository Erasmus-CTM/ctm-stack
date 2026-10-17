"""Observe the pinned STACK answer-test functions in native Maxima.

This runs official ``AT*`` functions, not the Moodle/PHP answer-test
controller or its input validation.  A result therefore describes that CAS
layer only.  The report layer independently compares desired fixture scores,
Python behaviour and these native observations.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


STACK_SHA = "10d323311b7f39fb7b092dd10ce75f7d8632f525"
INPUT_PREPARATION = "stack-logic-nouns-numeric-default-v2"
# MP_Operation/MP_FunctionCall::toString(nounify=2), security-map.json.
LOGIC_NOUNS = {"and": "nounand", "or": "nounor", "not": "nounnot"}


def prepare_logic(source: str) -> str:
    """Preserve logic as STACK does before evaluating answer-test arguments.

    Tokenize strings and whole identifiers: identifiers such as order, existing
    nounor, and text inside string literals must remain byte for byte intact.
    This is deliberately only the traced logic-noun preparation, not PHP AST
    validation or the rest of STACK's input processing.
    """
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|%?[A-Za-z_][A-Za-z_0-9]*|.', source, re.S)
    return "".join(LOGIC_NOUNS.get(m[0], m[0]) for m in tokens)
# controller.class.php $pops, columns: required options, CAS options, simp,
# required raw.  Only families implemented by stack-sympy are in scope.
TESTS = {
    "AlgEquiv": (False, True, False),
    "Sets": (False, False, False),
    "SameType": (False, True, False),
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
DIAG = re.compile(r"^\s*STACKNATIVE-DIAG\|(.+?)\s*$")
STANDALONE_PROBE = re.compile(r"^\s*STACKNATIVE-PROBE\|(.+?)\s*$")
CONTROLLED_AT_ERROR = re.compile(
    r"(?:AT[A-Za-z0-9]+_STACKERROR_(?:SAns|TAns|Opt|Raw|tol)"
    r"|ATNumDecPlaces_OptNotInt|STACKERROR_OPTION)\.\Z"
)
UNSAFE = re.compile(r"[;:$\"\r\n]|/\*|\*/|\b(?:load|system|kill|batch|file_search_maxima|with_stdout)\s*\(", re.I)
DEFAULT_JOBS = 4
PROBE_KEYS = (
    "i_binding", "parsed_i", "parsed_fraction", "ev_parsed_fraction",
    "literal_lowest_terms", "parsed_lowest_terms", "ev_parsed_lowest_terms",
    "eca_cos_evaluated", "eca_sqrt_evaluated",
)
STANDALONE_PROBE_KEYS = (
    "i_binding", "parse_i", "eval_i", "parse_fraction", "eval_fraction",
    "literal_lowest_terms", "inline_parse_lowest_terms", "inline_eval_lowest_terms",
    "assigned_parse_lowest_terms", "assigned_eval_lowest_terms",
    "inline_eval_eca_cos", "assigned_parse_eca_cos", "assigned_eval_eca_cos",
    "inline_eval_eca_sqrt", "assigned_parse_eca_sqrt", "assigned_eval_eca_sqrt",
    "simp_true_alg_equiv", "assigned_parse_alg_i", "assigned_eval_alg_i",
    "assigned_parse_eca_i", "assigned_eval_eca_i",
    "assigned_parse_bound_i", "assigned_eval_bound_i",
)


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
        if _unbalanced_delimiters(case[field]) and not (
                field == "options" and case["test"] in {"NumAbsolute", "NumRelative"}):
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
    canonical = json.dumps({"preparation": INPUT_PREPARATION, "cases": scope},
                           ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _call(case: dict) -> str:
    test = case["test"]
    requires_option, simplifying, raw = TESTS[test]
    # STACK emits the parsed answer AST as evaluated CAS assignments before
    # invoking AT*.  Maxima parse_string alone leaves configured names such
    # as i symbolic; eval_string evaluates their bindings while simp:false
    # retains form-sensitive expressions (checked by the loader probe).
    args = [f"eval_string({_literal(prepare_logic(case['student']))})",
            f"eval_string({_literal(prepare_logic(case['teacher']))})"]
    if requires_option:
        option = prepare_logic(case["options"])
        if test in {"NumAbsolute", "NumRelative"}:
            # controller.class.php defaults absent or syntactically invalid
            # options. Catch parsing alone: 1/0 must remain an evaluation error.
            option = _literal(option if option.strip() else "0.05")
            args.append(f"block([stack_option],stack_option:errcatch(parse_string({option})),"
                        f"if stack_option=[] then 0.05 else eval_string({option}))")
        else:
            args.append(f"eval_string({_literal(option)})")
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


def make_batch(source: Path, cases: list[dict], home: Path, batch_number: int, *, preloaded: bool = False) -> str:
    """Create an isolated Maxima batch with bounded, JSON-encoded records."""
    (home / "moodle-qtype_stack-master").symlink_to(source, target_is_directory=True)
    (home / "tmp").mkdir()
    (home / "plots").mkdir()
    (home / "obj").mkdir(exist_ok=True)
    loader = home / "moodle-qtype_stack-master/stack/maxima/stacklocallinux.mac"
    lines = [
        "display2d:false$",
        f"maxima_userdir:{_literal(str(home))}$",
        *([f"load({_literal(str(loader))})$",] if not preloaded else [
            ':lisp (ensure-directories-exist (concatenate \'string maxima::*maxima-objdir* "/"))',
            'file_search_maxima:delete(sconcat(stacktmplocation,"/###.{mac,mc}"),file_search_maxima)$',
            'file_search_lisp:delete(sconcat(stacktmplocation,"/###.{lisp}"),file_search_lisp)$',
            'file_search_maxima:delete(sconcat(stacklocation,"/stack/maxima/###.{mac,mc}"),file_search_maxima)$',
            'file_search_lisp:delete(sconcat(stacklocation,"/stack/maxima/###.{lisp}"),file_search_lisp)$',
            f"stacklocation:{_literal(str(home / 'moodle-qtype_stack-master'))}$",
            f"stacktmplocation:{_literal(str(home / 'tmp'))}$",
            f"file_search_maxima:append([{_literal(str(home / 'tmp/###.{mac,mc}'))},{_literal(str(source / 'stack/maxima/###.{mac,mc}'))}],file_search_maxima)$",
            f"file_search_lisp:append([{_literal(str(home / 'tmp/###.{lisp}'))},{_literal(str(source / 'stack/maxima/###.{lisp}'))}],file_search_lisp)$",
            "STACK_SETUP(true)$",
        ]),
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


def _probe_call(call: str, *, simp: bool = False) -> str:
    flag = "true" if simp else "false"
    return (f"block([simp:{flag},_probe_result],_probe_result:errcatch(" + call + "),"
            "if _probe_result=[] then [\"cas_error\"] else "
            "[first(_probe_result)[1],first(_probe_result)[2],first(_probe_result)[3]])")


def _probe_assigned(test: str, student: str, teacher: str, *, parse: bool = True,
                    simp: bool = False) -> str:
    """Evaluate two arguments as separate assignments before the AT call."""
    constructor = "parse_string" if parse else "eval_string"
    flag = "true" if simp else "false"
    call = f"AT{test}(_probe_sa,_probe_ta)"
    return (f"block([simp:{flag},_probe_sa,_probe_ta,_probe_result],"
            f"_probe_sa:{constructor}({_literal(student)}),"
            f"_probe_ta:{constructor}({_literal(teacher)}),"
            f"_probe_result:errcatch({call}),"
            "if _probe_result=[] then [\"cas_error\"] else "
            "[first(_probe_result)[1],first(_probe_result)[2],first(_probe_result)[3]])")


def make_standalone_probe_batch(source: Path, home: Path, *, preloaded: bool = False) -> str:
    """A one-process diagnostic, independent of fixture observations."""
    batch = make_batch(source, [], home, 0, preloaded=preloaded)
    experiments = {
        "i_binding": "string(i)",
        "parse_i": 'string(parse_string("i"))',
        "eval_i": 'string(eval_string("i"))',
        "parse_fraction": 'string(parse_string("1/(1+i)"))',
        "eval_fraction": 'string(eval_string("1/(1+i)"))',
        "literal_lowest_terms": _probe_call("ATLowestTerms(1/(1+i),(1-i)/2)"),
        "inline_parse_lowest_terms": _probe_call(
            'ATLowestTerms(parse_string("1/(1+i)"),parse_string("(1-i)/2"))'),
        "inline_eval_lowest_terms": _probe_call(
            'ATLowestTerms(eval_string("1/(1+i)"),eval_string("(1-i)/2"))'),
        "assigned_parse_lowest_terms": _probe_assigned(
            "LowestTerms", "1/(1+i)", "(1-i)/2"),
        "assigned_eval_lowest_terms": _probe_assigned(
            "LowestTerms", "1/(1+i)", "(1-i)/2", parse=False),
        "inline_eval_eca_cos": _probe_call(
            'ATEqualComAss(eval_string("cos(0)"),eval_string("1"))'),
        "assigned_parse_eca_cos": _probe_assigned(
            "EqualComAss", "cos(0)", "1"),
        "assigned_eval_eca_cos": _probe_assigned(
            "EqualComAss", "cos(0)", "1", parse=False),
        "inline_eval_eca_sqrt": _probe_call(
            'ATEqualComAss(eval_string("sqrt(3)"),eval_string("3^(1/2)"))'),
        "assigned_parse_eca_sqrt": _probe_assigned(
            "EqualComAss", "sqrt(3)", "3^(1/2)"),
        "assigned_eval_eca_sqrt": _probe_assigned(
            "EqualComAss", "sqrt(3)", "3^(1/2)", parse=False),
        "simp_true_alg_equiv": _probe_call('ATAlgEquiv(eval_string("i"),%i)', simp=True),
        "assigned_parse_alg_i": _probe_assigned(
            "AlgEquiv", "i", "disp_complex(0,1)", simp=True),
        "assigned_eval_alg_i": _probe_assigned(
            "AlgEquiv", "i", "disp_complex(0,1)", parse=False, simp=True),
        "assigned_parse_eca_i": _probe_assigned(
            "EqualComAss", "-1/4*%pi*i", "-(%i*%pi)/4"),
        "assigned_eval_eca_i": _probe_assigned(
            "EqualComAss", "-1/4*%pi*i", "-(%i*%pi)/4", parse=False),
        "assigned_parse_bound_i": _probe_assigned(
            "AlgEquiv", "[3,3.1,3.14,3.142,3.1416,3.14159,3.141593,3.1415927]",
            "makelist(significantfigures(%pi,i),i,8)", simp=True),
        "assigned_eval_bound_i": _probe_assigned(
            "AlgEquiv", "[3,3.1,3.14,3.142,3.1416,3.14159,3.141593,3.1415927]",
            "makelist(significantfigures(%pi,i),i,8)", parse=False, simp=True),
    }
    assert tuple(experiments) == STANDALONE_PROBE_KEYS
    pairs = ",".join(f"[{_literal(key)},{value}]" for key, value in experiments.items())
    diagnostic = ('simp:false$\nprint(sconcat("STACKNATIVE-PROBE|",'
                  'stackjson_stringify([' + pairs + '])))$\n')
    end = 'print("STACKNATIVE-END|0|0")$\n'
    if batch.count(end) != 1:
        raise NativeProtocolError("Cannot locate diagnostic end marker")
    return batch.replace(end, diagnostic + end)


def parse_standalone_probe_output(output: str) -> dict:
    payloads = []
    for line in output.splitlines():
        match = STANDALONE_PROBE.fullmatch(line)
        if match:
            payloads.append(match.group(1))
        elif line.lstrip().startswith("STACKNATIVE-PROBE|"):
            raise NativeProtocolError(f"Malformed standalone diagnostic: {line[:300]}")
    if len(payloads) != 1:
        raise NativeProtocolError(f"Expected one standalone diagnostic, got {len(payloads)}")
    try:
        pairs = json.loads(payloads[0])
    except json.JSONDecodeError as exc:
        raise NativeProtocolError(f"Malformed standalone diagnostic JSON: {exc}") from exc
    if not isinstance(pairs, list) or any(not isinstance(pair, list) or len(pair) != 2 or
                                          not isinstance(pair[0], str) for pair in pairs):
        raise NativeProtocolError(f"Unexpected standalone diagnostic shape: {pairs!r}")
    data = dict(pairs)
    if len(data) != len(pairs) or tuple(data) != STANDALONE_PROBE_KEYS:
        raise NativeProtocolError("Missing or duplicate standalone diagnostic keys")
    return data


def make_warmup_batch(source: Path, home: Path, *, preloaded: bool = False) -> str:
    """Prime loader caches and inspect aliases/form handling without fixture marks."""
    batch = make_batch(source, [], home, 0, preloaded=preloaded)
    expressions = [
        "string(i)",
        'string(parse_string("i"))',
        'string(parse_string("1/(1+i)"))',
        'string(ev(parse_string("1/(1+i)"),simp:false))',
        _probe_call("ATLowestTerms(1/(1+i),(1-i)/2)"),
        _probe_call('ATLowestTerms(parse_string("1/(1+i)"),parse_string("(1-i)/2"))'),
        _probe_call('ATLowestTerms(ev(parse_string("1/(1+i)"),simp:false),'
                    'ev(parse_string("(1-i)/2"),simp:false))'),
        _probe_call('ATEqualComAss(ev(parse_string("cos(0)"),simp:false),'
                    'ev(parse_string("1"),simp:false))'),
        _probe_call('ATEqualComAss(ev(parse_string("sqrt(3)"),simp:false),'
                    'ev(parse_string("3^(1/2)"),simp:false))'),
    ]
    diagnostic = ('simp:false$\nprint(sconcat("STACKNATIVE-DIAG|",stackjson_stringify(['
                  + ",".join(expressions) + '])))$\n')
    end = 'print("STACKNATIVE-END|0|0")$\n'
    if batch.count(end) != 1:
        raise NativeProtocolError("Cannot locate loader warm-up end marker")
    return batch.replace(end, diagnostic + end)


def parse_probe_output(output: str) -> dict:
    payloads = []
    for line in output.splitlines():
        match = DIAG.fullmatch(line)
        if match:
            payloads.append(match.group(1))
        elif line.lstrip().startswith("STACKNATIVE-DIAG|"):
            raise NativeProtocolError(f"Malformed loader diagnostic: {line[:300]}")
    if len(payloads) != 1:
        raise NativeProtocolError(f"Expected one loader diagnostic, got {len(payloads)}")
    try:
        values = json.loads(payloads[0])
    except json.JSONDecodeError as exc:
        raise NativeProtocolError(f"Malformed loader diagnostic JSON: {exc}") from exc
    if not isinstance(values, list) or len(values) != len(PROBE_KEYS):
        raise NativeProtocolError(f"Unexpected loader diagnostic shape: {values!r}")
    return dict(zip(PROBE_KEYS, values))


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


def _command(command: list[str], timeout: int, *, env: dict | None = None) -> str:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired as exc:
        captured = exc.stdout or b""
        if isinstance(captured, bytes):
            captured = captured.decode("utf-8", errors="replace")
        completed = [match.group(1) for line in captured.splitlines()
                     if (match := RESULT.fullmatch(line))]
        last = completed[-1] if completed else "none"
        raise NativeProcessError(f"Maxima timeout after {timeout}s: {command[0]}; "
                                 f"completed_result_markers={len(completed)}, last_case_id={last}; "
                                 f"output_tail={captured[-500:]!r}") from exc
    if proc.returncode:
        raise NativeProcessError(f"Maxima exit {proc.returncode}: {(proc.stdout + proc.stderr)[-3000:]}")
    return proc.stdout + proc.stderr


def run_standalone_probe(source: Path, maxima: str = "maxima", *, timeout: int = 300, image: Path | None = None) -> dict:
    """Run loader and argument-evaluation experiments without fixture data."""
    if timeout < 1:
        raise ValueError("timeout must be positive")
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
    from . import native_image
    image_manifest = native_image.validate(image, source, executable) if image else None
    with tempfile.TemporaryDirectory(prefix="stack-compliance-probe-") as directory:
        home = Path(directory)
        batch = home / "probe.mac"
        batch.write_text(make_standalone_probe_batch(source, home, preloaded=bool(image)), encoding="utf-8")
        output = _command(native_image.command(image, batch) if image else [executable, "--very-quiet", f"--batch={batch}"], timeout, **({"env": native_image.environment(home)} if image else {}))
        parse_output(output, [], 0)
        values = parse_standalone_probe_output(output)
    return {"schema_version": 1, "engine": "maxima_diagnostic",
            "metadata": {"reference_layer": "direct_official_maxima_AT",
                         "stack_sha": checkout, "maxima_version": version,
                         "preloaded_image": image_manifest},
            "probe": values}


def run_native(cases: list[dict], source: Path, maxima: str = "maxima", *, jobs: int = DEFAULT_JOBS,
               timeout: int = 300, image: Path | None = None) -> dict:
    """Return independent native observations and version/provenance metadata."""
    validate_cases(cases)
    if not 1 <= jobs <= 16 or timeout < 1:
        raise ValueError("jobs must be 1–16 and timeout must be positive")
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
    from . import native_image
    image_manifest = native_image.validate(image, source, executable) if image else None
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

    if runnable:
        # Several Maxima packages are lazily compiled on the first loader
        # invocation. Prime that shared package cache in a single process
        # before launching isolated case processes concurrently. A failure is
        # fatal: no partial/old observations are substituted for this run.
        with tempfile.TemporaryDirectory(prefix="stack-compliance-warmup-") as directory:
            home = Path(directory)
            batch = home / "warmup.mac"
            batch.write_text(make_warmup_batch(source, home, preloaded=bool(image)), encoding="utf-8")
            try:
                output = _command(native_image.command(image, batch) if image else [executable, "--very-quiet", f"--batch={batch}"], timeout, **({"env": native_image.environment(home)} if image else {}))
                parse_output(output, [], 0)
                probe = parse_probe_output(output)
                print("Native loader probe: " + json.dumps(probe, sort_keys=True), flush=True)
            except (NativeProcessError, NativeProtocolError) as exc:
                raise type(exc)(f"official STACK loader warm-up: {exc}") from exc

    def observe_one(batch_number: int, case: dict) -> dict:
        # An AT or a source expression can change global assumptions/features.
        # A fresh process per case prevents those changes affecting later
        # official fixture rows, as in the Moodle fixture test's CAS sessions.
        with tempfile.TemporaryDirectory(prefix="stack-compliance-maxima-") as directory:
            home = Path(directory)
            batch = home / "native.mac"
            batch.write_text(make_batch(source, [case], home, batch_number, preloaded=bool(image)), encoding="utf-8")
            try:
                output = _command(native_image.command(image, batch) if image else [executable, "--very-quiet", f"--batch={batch}"], timeout, **({"env": native_image.environment(home)} if image else {}))
                return parse_output(output, [case], batch_number)[0]
            except (NativeProcessError, NativeProtocolError) as exc:
                raise type(exc)(f"case process {batch_number} (fixture ordinal "
                                f"{case.get('ordinal', '?')}, id {case['id']}): {exc}") from exc

    started = time.monotonic()
    completed = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(observe_one, index, case): case["id"]
                   for index, case in enumerate(runnable)}
        try:
            for future in as_completed(futures):
                observations.append(future.result())
                completed += 1
                if completed % 50 == 0 or completed == len(runnable):
                    print(f"Native cases: {completed}/{len(runnable)} completed "
                          f"in {time.monotonic() - started:.1f}s", flush=True)
        except (NativeProcessError, NativeProtocolError):
            for future in futures:
                future.cancel()
            raise
    by_id = {row["case_id"]: row for row in observations}
    for case in cases:
        if case["id"] in unavailable:
            by_id[case["id"]] = {"case_id": case["id"], "test": case["test"],
                                "status": "unavailable", "reason": unavailable[case["id"]]}
    ordered = [by_id[case["id"]] for case in cases]
    return {"schema_version": 1, "engine": "maxima",
            "metadata": {"reference_layer": "direct_official_maxima_AT", "stack_sha": checkout,
                         "input_preparation": INPUT_PREPARATION,
                         "stack_library_version": library_match[1], "maxima_version": version,
                         "native_scope_sha256": scope_sha256(cases),
                         "execution_isolation": "fresh_maxima_process_per_case", "jobs": jobs,
                         "loader_warmup": bool(runnable), "preloaded_image": image_manifest,
                         "case_wall_seconds": time.monotonic() - started,
                         "loader_probe": probe if runnable else None},
            "observations": ordered,
            "summary": {"total": len(ordered), "ok": sum(r["status"] == "ok" for r in ordered),
                        "error": sum(r["status"] == "error" for r in ordered),
                        "unavailable": len(unavailable)}}
