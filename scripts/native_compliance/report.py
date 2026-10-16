"""Assemble a browseable, provenance-rich report from independent checker runs.

An absent or malformed result stays visibly unavailable. This command never
substitutes an older successful result or runs a checker while rendering.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

try:
    from .common import matches_desired
    from .maxima_runner import INPUT_PREPARATION
except ImportError:  # Direct CLI invocation.
    from common import matches_desired
    from maxima_runner import INPUT_PREPARATION

ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("top-level JSON must be an object")
        return value, None
    except (OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def observation_map(document: dict | None, key: str = "observations") -> dict[str, dict]:
    if not document or not isinstance(document.get(key), list):
        return {}
    return {str(row["case_id"]): row for row in document[key]
            if isinstance(row, dict) and "case_id" in row}


def parity_map(document: dict | None) -> dict[str, dict]:
    if not document or not isinstance(document.get("cases"), list):
        return {}
    return {str(row.get("case_id", row.get("id"))): row for row in document["cases"]
            if isinstance(row, dict) and ("case_id" in row or "id" in row)}


def _native_status(native: dict | None, python: dict | None) -> str:
    if native is None:
        return "unavailable"
    if native.get("status") != "ok":
        return native.get("status") if native.get("status") in {"unsupported", "unavailable"} else "error"
    if not python or python.get("kind") not in ("result", "ok"):
        return "not_compared"
    if not all(isinstance(row.get("correct"), bool) for row in (native, python)):
        return "not_compared"
    python_cas_valid = python.get("cas_valid", python.get("valid"))
    if not isinstance(python_cas_valid, bool) or not isinstance(native.get("cas_valid"), bool):
        return "not_compared"
    return "match" if (native["correct"], native["cas_valid"]) == (python["correct"], python_cas_valid) else "mismatch"


def _native_dimension(native: dict | None, python: dict | None, field: str) -> str:
    if native is None:
        return "unavailable"
    if native.get("status") != "ok":
        return native.get("status") if native.get("status") in {"unavailable", "unsupported"} else "error"
    if not python or python.get("kind") != "result":
        return "not_compared"
    local = python.get("cas_valid", python.get("valid")) if field == "cas_valid" else python.get("correct")
    reference = native.get(field)
    if not isinstance(local, bool) or not isinstance(reference, bool):
        return "not_compared"
    return "match" if local == reference else "mismatch"


def _desired_status(python: dict | None) -> str:
    if python is None:
        return "unavailable"
    status = python.get("policy_status")
    if status in {"pass", "known_defect", "approved_difference", "unexpected", "out_of_contract", "unsupported"}:
        return status
    return "error"


def _parity_status(parity: dict | None) -> str:
    if parity is None:
        return "unavailable"
    if parity.get("match") is True:
        return "match"
    if parity.get("match") is False:
        return "mismatch"
    return str(parity.get("status", "not_compared"))


def _native_desired(case: dict, native: dict | None, reference: dict | None) -> str:
    if native is None or native.get("status") != "ok" or not isinstance(native.get("correct"), bool):
        return "not_compared"
    score = case.get("expected_score")
    if score == -1:
        return "matches_desired" if native.get("controlled_error") is True else "expected_controlled_error_not_observed"
    if score not in {-3, -2, 0, 1}:
        return "unknown_expectation"
    desired = score in {1, -3}
    if score in {-2, -3} and native["correct"] != desired:
        return ("known_native_mathematical_failure" if reference and
                reference.get("status") == "known_native_mathematical_failure" else
                "upstream_negative_sentinel_difference")
    return "matches_desired" if native["correct"] == desired else "unexpected_native_deviation"


def validated_run(document: dict | None, read_error: str | None, expected_hash: str,
                  expected_cases: dict[str, dict], engine: str) -> tuple[dict | None, str | None]:
    if read_error:
        return None, read_error
    if document is None:
        return None, "No result document"
    if document.get("schema_version") != 1:
        return None, "Unsupported result schema version"
    if document.get("engine") != ("maxima" if engine == "native" else engine):
        return None, f"Wrong result engine: {document.get('engine')!r}"
    if document.get("error"):
        return None, f"Runner error: {document['error']}"
    if engine != "native" and not isinstance(document.get("passed"), bool):
        return None, "Missing checker pass/fail verdict"
    metadata = document.get("metadata")
    if engine in {"python", "native"} and not isinstance(metadata, dict):
        return None, "Missing runner metadata"
    if engine == "native" and metadata.get("input_preparation") != INPUT_PREPARATION:
        return None, "Native input preparation differs from current noun mapping"
    observed_hash = metadata.get("fixture_sha256") if engine in {"python", "native"} else document.get("fixture_sha256")
    if observed_hash != expected_hash:
        return None, f"Fixture SHA-256 mismatch or missing ({observed_hash!r})"
    key = "cases" if engine == "parity" else "observations"
    observations = document.get(key)
    if not isinstance(observations, list):
        return None, f"Missing {key} array"
    ids = [row.get("case_id", row.get("id")) if isinstance(row, dict) else None for row in observations]
    if any(not isinstance(case_id, str) for case_id in ids):
        return None, "Malformed result case IDs"
    if len(ids) != len(set(ids)) or set(ids) != set(expected_cases):
        return None, f"Result IDs differ from fixture: {len(ids)} rows, {len(set(ids))} unique; expected {len(expected_cases)}"
    for row, case_id in zip(observations, ids):
        if not isinstance(row, dict) or ("test" in row and row["test"] != expected_cases[case_id]["test"]):
            return None, f"Malformed or mismatched observation for {case_id}"
        if engine == "python":
            if row.get("policy_status") not in {"pass", "known_defect", "unexpected", "out_of_contract"}:
                return None, f"Invalid Python policy status for {case_id}"
            if not isinstance(row.get("kind"), str) or not isinstance(row.get("desired_match"), bool):
                return None, f"Invalid Python observation for {case_id}"
            score = expected_cases[case_id]["expected_score"]
            if score not in {-3, -2, -1, 0, 1}:
                return None, f"Unknown authored score for {case_id}"
            actual_match = matches_desired(row, score, expected_cases[case_id].get("answer_note", ""))
            if row["desired_match"] is not actual_match:
                return None, f"Contradictory Python desired mark for {case_id}"
            if ((row["policy_status"] == "pass" and not actual_match) or
                    (row["policy_status"] == "known_defect" and actual_match) or
                    (row["policy_status"] == "out_of_contract" and row.get("scope") == "supported")):
                return None, f"Contradictory Python policy status for {case_id}"
        elif engine == "native":
            if row.get("status") not in {"ok", "error", "unavailable", "unsupported"}:
                return None, f"Invalid native status for {case_id}"
            if row["status"] == "ok" and not all(isinstance(row.get(k), bool) for k in ("cas_valid", "correct")):
                return None, f"Invalid native result for {case_id}"
        elif engine == "compatibility":
            if row.get("status") not in {"match", "match_controlled_error", "known_native_mathematical_failure", "approved_difference",
                                         "known_port_defect", "known_port_limitation", "unavailable", "not_compared",
                                         "unexpected_mismatch", "unexpected_execution_error"}:
                return None, f"Invalid compatibility verdict for {case_id}"
        elif not isinstance(row.get("match"), bool):
            return None, f"Invalid parity result for {case_id}"
    if engine == "python" and document["passed"] is any(row["policy_status"] == "unexpected" for row in observations):
        return None, "Python verdict contradicts case policy statuses"
    if engine == "compatibility":
        unexpected = any(row["status"] in {"unexpected_mismatch", "unexpected_execution_error"} for row in observations)
        if document["passed"] is unexpected:
            return None, "Compatibility verdict contradicts case statuses"
    if engine == "parity" and document["passed"] is not all(row["match"] for row in observations):
        return None, "Parity verdict contradicts case statuses"
    return document, None


def assemble(fixture_path: Path, python_path: Path, maxima_path: Path, pyodide_path: Path,
             reference_path: Path | None = None) -> dict:
    reference_path = reference_path or ROOT / "test-results/compliance/reference.json"
    fixture, fixture_error = read_json(fixture_path)
    if fixture_error or not isinstance(fixture.get("cases"), list):
        raise ValueError(f"Cannot build report without the pinned fixture: {fixture_error or 'cases missing'}")
    fixture_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    cases_by_id = {case["id"]: case for case in fixture["cases"]}
    if len(cases_by_id) != len(fixture["cases"]):
        raise ValueError("Fixture has duplicate case IDs")
    python, python_error = validated_run(*read_json(python_path), fixture_hash, cases_by_id, "python")
    maxima, maxima_error = validated_run(*read_json(maxima_path), fixture_hash, cases_by_id, "native")
    pyodide, pyodide_error = validated_run(*read_json(pyodide_path), fixture_hash, cases_by_id, "parity")
    reference, reference_error = validated_run(*read_json(reference_path), fixture_hash, cases_by_id, "compatibility")
    policy_path = ROOT / "tests/native_compliance/policy.json"
    policy, policy_error = read_json(policy_path)
    if policy_error:
        raise ValueError(f"Cannot load case explanations: {policy_error}")
    if python is not None and python["metadata"].get("policy_sha256") != hashlib.sha256(policy_path.read_bytes()).hexdigest():
        python, python_error = None, "Python policy hash differs from checked-in policy"
    if reference is not None:
        native_policy = ROOT / "tests/native_compliance/native_policy.json"
        if reference.get("policy_sha256") != hashlib.sha256(native_policy.read_bytes()).hexdigest():
            reference, reference_error = None, "Native policy hash differs from checked-in policy"
    if reference is not None:
        source_hashes = {"python_report_sha256": python_path, "native_report_sha256": maxima_path}
        for field, path in source_hashes.items():
            if (not path.exists() or reference.get(field) != hashlib.sha256(path.read_bytes()).hexdigest()
                    or (field.startswith("python") and python is None)
                    or (field.startswith("native") and maxima is None)):
                reference, reference_error = None, f"Compatibility source mismatch or unavailable: {field}"
                break
    if pyodide is not None and (python is None or not python_path.exists() or
                            pyodide.get("python_report_sha256") != hashlib.sha256(python_path.read_bytes()).hexdigest()):
        pyodide, pyodide_error = None, "Parity Python source mismatch or unavailable"
    by_python = observation_map(python)
    by_native = observation_map(maxima)
    by_parity = parity_map(pyodide)
    by_reference = observation_map(reference)
    source = fixture.get("upstream", {})
    source_url = source.get("source_url")
    rows = []
    for case in fixture["cases"]:
        case_id = case["id"]
        p, n, b, ref = by_python.get(case_id), by_native.get(case_id), by_parity.get(case_id), by_reference.get(case_id)
        line = case.get("source_line")
        source_link = f"{source_url}#L{line}" if source_url and isinstance(line, int) else source_url
        rows.append({
            "id": case_id, "ordinal": case.get("ordinal"), "test": case.get("test"),
            "student": case.get("student"), "teacher": case.get("teacher"),
            "options": case.get("options"), "expected_score": case.get("expected_score"),
            "answer_note": case.get("answer_note"), "notes": case.get("notes"),
            "extra_fields": case.get("extra_fields"), "source_line": line,
            "source_url": source_link, "python": p, "native": n, "parity": b, "compatibility": ref,
            "discussion": policy.get("cases", {}).get(case_id, {}).get("discussion"),
            "desired_status": _desired_status(p), "native_status": ref["status"] if ref else "unavailable",
            "native_boolean_status": _native_status(n, p),
            "native_mark_status": _native_dimension(n, p, "correct"),
            "native_applicability_status": _native_dimension(n, p, "cas_valid"),
            "native_desired_status": _native_desired(case, n, ref),
            "answer_note_status": (("controlled_error_note_matched" if n["answer_note"].strip() == case["answer_note"].strip()
                                    else "controlled_error_note_mismatch")
                                   if case.get("expected_score") == -1 and n and n.get("status") == "ok" and
                                   isinstance(n.get("answer_note"), str) and isinstance(case.get("answer_note"), str)
                                   else "not_compared"),
            "parity_status": _parity_status(b),
        })
    run_url = None
    if os.getenv("GITHUB_REPOSITORY") and os.getenv("GITHUB_RUN_ID"):
        run_url = f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    results = {
        "python": {"path": str(python_path), "available": python is not None,
                   "error": python_error or (python or {}).get("error"), "metadata": (python or {}).get("metadata"),
                   "summary": (python or {}).get("summary"), "passed": (python or {}).get("passed")},
        "native": {"path": str(maxima_path), "available": maxima is not None,
                   "error": maxima_error or (maxima or {}).get("error"), "metadata": (maxima or {}).get("metadata"),
                   "summary": (maxima or {}).get("summary")},
        "compatibility": {"path": str(reference_path), "available": reference is not None,
                          "error": reference_error, "summary": (reference or {}).get("summary"),
                          "passed": (reference or {}).get("passed"),
                          "metadata": {"policy_sha256": reference.get("policy_sha256")} if reference else None},
        "parity": {"path": str(pyodide_path), "available": pyodide is not None,
                   "error": pyodide_error or (pyodide or {}).get("error"),
                   "passed": (pyodide or {}).get("passed"),
                   "metadata": {"pyodide_version": pyodide.get("pyodide_version"),
                                "sympy_version": pyodide.get("sympy_version"),
                                "browser_versions": pyodide.get("browser_versions"),
                                "source_bundle_sha256": pyodide.get("source_bundle_sha256")}
                   if pyodide else None,
                   "summary": (pyodide or {}).get("summary")},
    }
    for component in results.values():
        for key in ("metadata", "summary"):
            if isinstance(component[key], dict):
                component[key] = {k: v for k, v in component[key].items() if k != "observations"}
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Pinned upstream static answer-test rows only; CAS-only comparison, not Moodle controller grading or deployment fidelity.",
        "provenance": {"code_sha": os.getenv("GITHUB_SHA") or git_sha(), "run_url": run_url,
                       "fixture_sha256": fixture_hash,
                       "fixture_upstream": source, "fixture_inventory": fixture.get("inventory", {}),
                       "python_version": platform.python_version()},
        "results": results,
        "summary": {axis: dict(Counter(row[f"{axis}_status"] for row in rows))
                    for axis in ("desired", "native", "native_mark", "native_applicability", "native_desired", "parity")},
        "cases": rows,
    }



def port_regressions(path: Path) -> dict:
    """Keep project contracts and their denominator separate from legacy rows."""
    try:
        try:
            from .port_contract import load_fixture, assemble as assemble_port
        except ImportError:
            from port_contract import load_fixture, assemble as assemble_port
        fixture = ROOT / "tests/port_regressions/fixtures.json"
        cases = load_fixture(fixture)
        report, error = read_json(path)
        if error:
            raise ValueError(error)
        provenance = report.get("provenance", {})
        if (report.get("schema_version") != 1 or report.get("suite") != "project_port_regressions"
                or provenance.get("fixture_sha256") != hashlib.sha256(fixture.read_bytes()).hexdigest()
                or provenance.get("input_preparation") != INPUT_PREPARATION
                or provenance.get("source_bundle_sha256") != hashlib.sha256(
                    (ROOT / "_extensions/stack-sympy/runtime-sources.js").read_bytes()).hexdigest()):
            raise ValueError("Port regression provenance differs from current fixture/preparation/runtime")
        rows = report.get("cases", [])
        if [row.get("id") for row in rows] != [case["id"] for case in cases]:
            raise ValueError("Port regression coverage differs from fixture")
        for case, row in zip(cases, rows):
            if any(row.get(key) != value for key,value in case.items()):
                raise ValueError("Port regression contract differs from fixture")
        native = {"observations":[row["native"] for row in rows if row.get("native")]}
        parity = {"cases":[row["parity"] for row in rows if row.get("parity")]}
        check = assemble_port(cases, [row["python"] for row in rows if row.get("python")],
                              native, parity, report.get("errors"))
        if report.get("passed") is not check["passed"] or report.get("summary") != check["summary"]:
            raise ValueError("Port regression verdict contradicts observations")
        if any(any(row.get(key) != expected[key] for key in ("python_status","native_status","parity_status"))
               for row,expected in zip(rows,check["cases"])):
            raise ValueError("Port regression statuses contradict observations")
        return {"available":True, **report}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"available":False,"passed":False,"error":str(exc),"cases":[]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/native_compliance/fixtures.json")
    parser.add_argument("--python", type=Path, default=ROOT / "test-results/compliance/python.json")
    parser.add_argument("--maxima", type=Path, default=ROOT / "test-results/compliance/maxima.json")
    parser.add_argument("--pyodide", type=Path, default=ROOT / "test-results/compliance/pyodide.json")
    parser.add_argument("--reference", type=Path, default=ROOT / "test-results/compliance/reference.json")
    parser.add_argument("--output", type=Path, default=ROOT / "compliance-report/report.json")
    args = parser.parse_args(argv)
    try:
        report = assemble(args.fixture, args.python, args.maxima, args.pyodide, args.reference)
    except (ValueError, OSError) as exc:
        print(f"Report assembly failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    port_output = args.output.with_name("port-regressions.json")
    port = port_regressions(ROOT / "test-results/compliance/port-regressions.json")
    port_output.write_text(json.dumps(port, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Port report: {port_output}")
    print(f"Report: {args.output} ({len(report['cases'])} imported rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
