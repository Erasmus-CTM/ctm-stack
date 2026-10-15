#!/usr/bin/env python3
"""Bounded, case-isolated native Python conformance against fixture marks."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import sympy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_extensions/stack-sympy"))
sys.path.insert(0, str(ROOT / "scripts"))

from native_compliance.common import OBSERVATION_FIELDS, comparable, desired_outcome, matches_desired
from native_compliance.python_runner import classify_case, evaluate_case

DEFAULT_FIXTURE = ROOT / "tests/native_compliance/fixtures.json"
DEFAULT_POLICY = ROOT / "tests/native_compliance/policy.json"
DEFAULT_OUTPUT = ROOT / "test-results/compliance/python.json"


def load_fixture(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != 1 or not isinstance(fixture.get("cases"), list):
        raise ValueError("Expected a version-one fixture with cases array")
    seen = set()
    for case in fixture["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in seen:
            raise ValueError("Fixture case IDs must be unique strings")
        seen.add(case["id"])
        desired_outcome(case["expected_score"])
    return fixture


def load_policy(path: Path, ids: set[str]) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1 or not isinstance(policy.get("cases"), dict):
        raise ValueError("Expected a version-one case-specific policy")
    if not isinstance(policy.get("scope_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", policy["scope_sha256"]):
        raise ValueError("Policy requires a pinned scope_sha256")
    if policy["cases"].keys() - ids:
        raise ValueError("Policy has IDs absent from the fixture")
    for case_id, entry in policy["cases"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError(f"{case_id}: policy requires a nonempty reason")
        expected = entry.get("expected_observation")
        if not isinstance(expected, dict) or not expected or "kind" not in expected:
            raise ValueError(f"{case_id}: policy requires an explicit expected observation")
        if expected["kind"] in {"unexpected_exception", "timeout", "unsupported"}:
            raise ValueError(f"{case_id}: cannot approve an exception, timeout, or unsupported case as a defect")
        if set(expected) - set(OBSERVATION_FIELDS):
            raise ValueError(f"{case_id}: policy has unknown observation fields")
        if expected["kind"] == "result":
            if type(expected.get("valid")) is not bool or type(expected.get("correct")) is not bool:
                raise ValueError(f"{case_id}: result policy must pin valid and correct booleans")
        elif not isinstance(expected.get("message"), str) or not expected["message"]:
            raise ValueError(f"{case_id}: controlled error policy must pin a nonempty message")
    return policy


def isolated_case(case: dict, timeout: float) -> dict:
    started = time.monotonic()
    command = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    try:
        process = subprocess.run(command, input=json.dumps(case), capture_output=True, text=True,
                                 timeout=timeout, check=False, cwd=ROOT)
        if process.returncode:
            observation = {"case_id": case["id"], "test": case["test"],
                           "kind": "unexpected_exception", "exception_type": "WorkerExit",
                           "message": f"exit {process.returncode}: {process.stderr[-500:]}"}
        else:
            observation = json.loads(process.stdout)
            if (not isinstance(observation, dict) or observation.get("case_id") != case["id"]
                    or observation.get("test") != case["test"] or "kind" not in observation):
                raise ValueError("worker returned mismatched observation")
    except subprocess.TimeoutExpired:
        observation = {"case_id": case["id"], "test": case["test"], "kind": "timeout",
                       "message": f"case exceeded {timeout:g} seconds"}
    except (ValueError, OSError) as exc:
        observation = {"case_id": case["id"], "test": case["test"],
                       "kind": "unexpected_exception", "exception_type": type(exc).__name__, "message": str(exc)}
    observation["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return observation


def assess(case: dict, observation: dict, policy: dict, scope: dict) -> dict:
    expected = desired_outcome(case["expected_score"])
    result = {**observation, "expected_score": case["expected_score"], "desired": expected,
              "desired_match": matches_desired(observation, case["expected_score"]),
              "scope": scope["kind"]}
    if scope["kind"] == "unsupported" or (scope["kind"] in {
            "invalid_student", "invalid_teacher", "invalid_option"} and case["expected_score"] != -1):
        result["policy_status"] = "out_of_contract"
        result["reason"] = scope["reason"]
        return result
    entry = policy.get(case["id"])
    if entry is not None:
        expected_observation = entry["expected_observation"]
        pinned = comparable(observation) == expected_observation
        # If the adapter improves, force the policy owner to remove its stale
        # exception; silently retaining it obscures progress.
        result["policy_status"] = "known_defect" if pinned and not result["desired_match"] else "unexpected"
        result["reason"] = entry["reason"]
    else:
        result["policy_status"] = "pass" if result["desired_match"] else "unexpected"
    return result


def run(fixture_path: Path, policy_path: Path, *, timeout: float = 5, jobs: int = 4) -> dict:
    fixture = load_fixture(fixture_path)
    cases = fixture["cases"]
    policy = load_policy(policy_path, {case["id"] for case in cases})
    scopes = [classify_case(case) for case in cases]
    scope_pairs = [(case["id"], scope["kind"]) for case, scope in zip(cases, scopes)]
    scoped_ids = [case_id for case_id, kind in scope_pairs if kind != "unsupported"]
    scoped_sha256 = hashlib.sha256(("\n".join(f"{case_id}|{kind}" for case_id, kind in scope_pairs)
                                     + "\n").encode()).hexdigest()
    if policy["scope_sha256"] != scoped_sha256:
        raise ValueError(f"Preflight scope changed: expected {policy['scope_sha256']}, got {scoped_sha256}")
    supported_ids = {case_id for case_id, kind in scope_pairs if kind == "supported"}
    if policy["cases"].keys() - supported_ids:
        raise ValueError("Policy entry fell outside supported preflight scope")
    observations = [None] * len(cases)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        pending = {pool.submit(isolated_case, case, timeout): i for i, (case, scope) in enumerate(zip(cases, scopes))
                   if scope["kind"] == "supported"}
        for i, (case, scope) in enumerate(zip(cases, scopes)):
            if scope["kind"] != "supported":
                observations[i] = evaluate_case(case)
        for task, i in pending.items():
            observations[i] = task.result()
    assessed = [assess(case, obs, policy["cases"], scope)
                for case, obs, scope in zip(cases, observations, scopes)]
    statuses = {name: sum(x["policy_status"] == name for x in assessed)
                for name in ("pass", "known_defect", "unexpected", "out_of_contract")}
    return {"schema_version": 1, "engine": "python",
            "metadata": {"fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                         "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                         "fixture_upstream": fixture.get("upstream"), "timeout_seconds": timeout,
                         "python_version": sys.version.split()[0], "sympy_version": sympy.__version__,
                         "scope_sha256": scoped_sha256, "scoped_cases": len(scoped_ids),
                         "scope_counts": {kind: sum(scope["kind"] == kind for scope in scopes)
                                          for kind in ("supported", "unsupported", "invalid_student",
                                                       "invalid_teacher", "invalid_option")}},
            "observations": assessed, "summary": {"total": len(cases), **statuses},
            "passed": statuses["unexpected"] == 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.worker:
        case = json.load(sys.stdin)
        print(json.dumps(evaluate_case(case), ensure_ascii=False))
        return 0
    if args.timeout <= 0 or not 1 <= args.jobs <= 16:
        parser.error("--timeout must be positive and --jobs between 1 and 16")
    try:
        report = run(args.fixture, args.policy, timeout=args.timeout, jobs=args.jobs)
    except (ValueError, OSError) as exc:
        report = {"schema_version": 1, "engine": "python", "passed": False,
                  "observations": [], "summary": {"total": 0, "pass": 0, "known_defect": 0,
                                                   "unexpected": 0, "out_of_contract": 0},
                  "error": f"{type(exc).__name__}: {exc}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Python conformance: {report.get('error', report['summary'])} -> {args.output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
