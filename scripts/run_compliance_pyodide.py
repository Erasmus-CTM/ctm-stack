"""Compare the exact Python adapter in CPython and the pinned browser Pyodide.

No Quarto build is needed. The static harness hosts the committed Python bundle,
loads Pyodide/SymPy in a real Chromium Worker, and bounds each fixture case.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from native_compliance.common import comparable  # noqa: E402

DEFAULT_FIXTURES = ROOT / "tests/native_compliance/fixtures.json"
DEFAULT_PYTHON = ROOT / "test-results/compliance/python.json"
DEFAULT_REPORT = ROOT / "test-results/compliance/pyodide.json"
PYODIDE_VERSION = "0.27.2"
PINNED_SYMPY = re.search(r"^sympy==([^\s]+)$", (ROOT / "requirements.txt").read_text(), re.M).group(1)
PARITY_KINDS = {"result", "unsupported", "invalid_student", "invalid_teacher", "invalid_option",
                "unexpected_exception", "timeout"}


def load_fixture(path: Path) -> tuple[list[dict], str]:
    contents = path.read_bytes()
    fixture = json.loads(contents)
    if not isinstance(fixture, dict) or fixture.get("schema_version") != 1 or not isinstance(fixture.get("cases"), list):
        raise ValueError("Expected v1 fixture object with cases array")
    cases = fixture["cases"]
    if not cases or any(not isinstance(case, dict) or not isinstance(case.get("id"), str)
                        or not isinstance(case.get("test"), str) for case in cases):
        raise ValueError("Fixture cases must have IDs and test names")
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Fixture case IDs are not unique")
    return cases, hashlib.sha256(contents).hexdigest()


def validate_observations(cases: list[dict], observations: list[dict], engine: str) -> None:
    if not isinstance(observations, list) or len(observations) != len(cases):
        raise ValueError(f"{engine} coverage is incomplete: {len(observations) if isinstance(observations, list) else 'invalid'}"
                         f"/{len(cases)} observations")
    for case, observed in zip(cases, observations):
        if not isinstance(observed, dict) or observed.get("case_id") != case["id"] or observed.get("test") != case["test"]:
            raise ValueError(f"{engine} case order/identity mismatch at {case['id']}")
        if observed.get("kind") not in PARITY_KINDS:
            raise ValueError(f"{engine} invalid observation kind at {case['id']}: {observed.get('kind')!r}")
        if observed["kind"] == "result" and (type(observed.get("valid")) is not bool
                                                or type(observed.get("correct")) is not bool):
            raise ValueError(f"{engine} malformed result observation at {case['id']}")


def compare_observations(cases: list[dict], python: list[dict], pyodide: list[dict]) -> tuple[list[dict], dict]:
    validate_observations(cases, python, "python")
    validate_observations(cases, pyodide, "pyodide")
    rows = []
    for case, local, browser in zip(cases, python, pyodide):
        # Faults must never be accepted as agreeing merely because both
        # environments failed in the same way.
        matched = (local["kind"] not in {"timeout", "unexpected_exception"}
                   and browser["kind"] not in {"timeout", "unexpected_exception"}
                   and comparable(local) == comparable(browser))
        eligible = local.get("scope", "unsupported" if local["kind"] == "unsupported" else "supported") == "supported"
        rows.append({"id": case["id"], "test": case["test"], "python": local,
                     "pyodide": browser, "eligible": eligible, "match": matched})
    summary = {
        "total": len(cases),
        "python_observed": len(python),
        "pyodide_observed": len(pyodide),
        "matched": sum(row["match"] for row in rows),
        "mismatched": sum(not row["match"] for row in rows),
        "python_supported": sum(item["kind"] != "unsupported" for item in python),
        "pyodide_supported": sum(item["kind"] != "unsupported" for item in pyodide),
        "eligible": sum(row["eligible"] for row in rows),
        "eligible_matched": sum(row["eligible"] and row["match"] for row in rows),
        "unsupported_agreement": sum(row["python"]["kind"] == row["pyodide"]["kind"] == "unsupported"
                                     and row["match"] for row in rows),
        "python_faults": sum(item["kind"] in {"timeout", "unexpected_exception"} for item in python),
        "pyodide_faults": sum(item["kind"] in {"timeout", "unexpected_exception"} for item in pyodide),
    }
    if summary["eligible"] == 0:
        raise ValueError("No Python-supported cases were observed; parity coverage is empty")
    return rows, summary


def validate_bundle() -> str:
    """Fail if the real browser bundle does not represent the current sources."""
    from bundle_runtime import OUTPUT, generate
    if OUTPUT.read_text(encoding="utf-8") != generate():
        raise ValueError("Committed runtime-sources.js is stale; run scripts/bundle_runtime.py")
    vendor = ROOT / "_extensions/stack-sympy/vendor"
    provenance = json.loads((vendor / "provenance.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((vendor / "pyodide-runtime.js").read_bytes()).hexdigest()
    if digest != provenance["sha256"] or provenance.get("pyodide") != PYODIDE_VERSION:
        raise ValueError("Vendored Pyodide runtime does not match its pinned provenance")
    return hashlib.sha256(OUTPUT.read_bytes()).hexdigest()


@contextmanager
def serve_repo():
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def browser_observations(cases: list[dict], *, init_timeout_ms: int, case_timeout_ms: int) -> tuple[list[dict], dict]:
    from playwright.sync_api import sync_playwright

    output: list[dict] = []
    with serve_repo() as base, sync_playwright() as pw:
        options = {"headless": True}
        if os.environ.get("STACK_SYMPY_CHROMIUM"):
            options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = pw.chromium.launch(**options)
        try:
            page = browser.new_page()
            page.goto(base + "/scripts/native_compliance/pyodide_harness.html", wait_until="domcontentloaded")
            versions = page.evaluate("ms => window.initializeParity(ms)", init_timeout_ms)
            if versions.get("pyodide_version") != PYODIDE_VERSION:
                raise RuntimeError(f"Browser Pyodide {versions.get('pyodide_version')!r} does not match pinned {PYODIDE_VERSION}")
            if versions.get("sympy_version") != PINNED_SYMPY:
                raise RuntimeError(f"Browser SymPy {versions.get('sympy_version')!r} does not match pinned {PINNED_SYMPY}")
            for index, case in enumerate(cases, 1):
                try:
                    observed = page.evaluate("args => window.evaluateParity(args.case, args.timeout)",
                                             {"case": case, "timeout": case_timeout_ms})
                    if not isinstance(observed, dict):
                        raise ValueError("Browser returned a non-object observation")
                except Exception as exc:
                    message = str(exc)
                    kind = "timeout" if "Pyodide evaluate timeout after" in message else "unexpected_exception"
                    observed = {"case_id": case["id"], "test": case["test"], "kind": kind,
                                "exception_type": type(exc).__name__, "message": message[-1000:]}
                    if kind != "timeout":
                        # Worker errors terminate the active Worker and need
                        # a fresh instance; failures cannot score as parity.
                        page.evaluate("() => window.resetParity()")
                    page.evaluate("ms => window.initializeParity(ms)", init_timeout_ms)
                output.append(observed)
                if index % 100 == 0:
                    print(f"Pyodide observations: {index}/{len(cases)}", flush=True)
            return output, versions
        finally:
            browser.close()


def run(*, fixtures: Path, python_report: Path, init_timeout_ms: int, case_timeout_ms: int) -> dict:
    cases, digest = load_fixture(fixtures)
    bundle_digest = validate_bundle()
    source = json.loads(python_report.read_text(encoding="utf-8"))
    if source.get("schema_version") != 1 or source.get("engine") != "python":
        raise ValueError("Expected a version-one CPython compliance report")
    metadata = source.get("metadata", {})
    if metadata.get("fixture_sha256") != digest:
        raise ValueError("CPython report fixture SHA-256 does not match the parity fixture")
    python = source.get("observations")
    validate_observations(cases, python, "python")
    if metadata.get("sympy_version") != PINNED_SYMPY:
        raise ValueError(f"CPython SymPy version must be {PINNED_SYMPY}")
    observed, versions = browser_observations(cases, init_timeout_ms=init_timeout_ms,
                                              case_timeout_ms=case_timeout_ms)
    rows, summary = compare_observations(cases, python, observed)
    return {"schema_version": 1, "engine": "parity", "fixture_sha256": digest,
            "python_report_sha256": hashlib.sha256(python_report.read_bytes()).hexdigest(),
            "source_bundle_sha256": bundle_digest, "pyodide_version": PYODIDE_VERSION,
            "sympy_version": PINNED_SYMPY, "browser_versions": versions,
            "cases": rows, "summary": summary, "passed": summary["mismatched"] == 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--python-report", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--init-timeout-ms", type=int, default=180000)
    parser.add_argument("--case-timeout-ms", type=int, default=30000)
    args = parser.parse_args(argv)
    result: dict = {"schema_version": 1, "engine": "parity", "passed": False}
    try:
        if args.init_timeout_ms < 1000 or args.case_timeout_ms < 100:
            raise ValueError("Timeouts must be positive, bounded milliseconds")
        result = run(fixtures=args.cases, python_report=args.python_report,
                     init_timeout_ms=args.init_timeout_ms, case_timeout_ms=args.case_timeout_ms)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pyodide parity: {result.get('summary', {}).get('matched', 0)}/"
          f"{result.get('summary', {}).get('total', 0)} matched; report: {args.report}")
    if result.get("error"):
        print(result["error"], file=sys.stderr)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
