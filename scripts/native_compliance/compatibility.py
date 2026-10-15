"""Gate Python/native compatibility using this run's pinned observations."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_compliance.report import ROOT, read_json, validated_run
from native_compliance.maxima_runner import _unavailable, scope_sha256


def assess(fixture_path: Path, python_path: Path, native_path: Path, policy_path: Path) -> dict:
    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes)
    cases = fixture["cases"]
    by_case = {case["id"]: case for case in cases}
    if len(by_case) != len(cases):
        raise ValueError("Duplicate fixture IDs")
    digest = hashlib.sha256(fixture_bytes).hexdigest()
    python, python_error = validated_run(*read_json(python_path), digest, by_case, "python")
    native, native_error = validated_run(*read_json(native_path), digest, by_case, "native")
    if python_error or native_error:
        raise ValueError(f"Cannot compare unavailable observations: Python={python_error}; native={native_error}")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    exceptions = policy.get("cases")
    if policy.get("schema_version") != 1 or not isinstance(exceptions, dict) or set(exceptions) - set(by_case):
        raise ValueError("Invalid native compatibility policy")
    scope = policy.get("native_scope_sha256")
    if not isinstance(scope, str) or not re.fullmatch(r"[0-9a-f]{64}", scope) or native["metadata"].get("native_scope_sha256") != scope:
        raise ValueError("Native availability scope differs from reviewed policy")
    if scope_sha256(cases) != scope:
        raise ValueError("Current native preflight differs from reviewed policy")
    if native["metadata"].get("stack_sha") != fixture.get("upstream", {}).get("commit"):
        raise ValueError("Native STACK commit differs from pinned fixture")
    python_policy = ROOT / "tests/native_compliance/policy.json"
    if python["metadata"].get("policy_sha256") != hashlib.sha256(python_policy.read_bytes()).hexdigest():
        raise ValueError("Python policy differs from reviewed report")
    for case_id, entry in exceptions.items():
        if (not isinstance(entry, dict) or entry.get("category") not in
                {"known_native_mathematical_failure", "known_port_limitation", "approved_difference"}
                or not isinstance(entry.get("reason"), str) or not entry["reason"].strip()
                or not isinstance(entry.get("python"), dict) or not isinstance(entry.get("native"), dict)
                or set(entry["python"]) != {"cas_valid", "correct"}
                or set(entry["native"]) != {"cas_valid", "correct"}
                or any(not isinstance(v, bool) for v in (*entry["python"].values(), *entry["native"].values()))):
            raise ValueError(f"Invalid case-pinned native policy: {case_id}")
        if entry["category"] == "known_native_mathematical_failure":
            score = by_case[case_id]["expected_score"]
            if (score not in {-2, -3} or entry["python"]["correct"] is not (score == -3)
                    or entry["native"]["correct"] is not (score == -2)):
                raise ValueError(f"Invalid known native mathematical failure: {case_id}")
        if entry["category"] == "known_port_limitation":
            if (by_case[case_id]["expected_score"] != 0 or
                    entry["python"]["correct"] is not False or entry["native"]["correct"] is not False or
                    entry["python"]["cas_valid"] is entry["native"]["cas_valid"]):
                raise ValueError(f"Invalid applicability-only port limitation: {case_id}")
    pobs = {row["case_id"]: row for row in python["observations"]}
    nobs = {row["case_id"]: row for row in native["observations"]}
    for case in cases:
        expected_unavailable = _unavailable(case)
        observation = nobs[case["id"]]
        if (expected_unavailable and (observation["status"] != "unavailable" or
                                      observation.get("reason") != expected_unavailable)) or (
                expected_unavailable is None and observation["status"] == "unavailable"):
            raise ValueError(f"Native availability observation disagrees with pinned scope: {case['id']}")
    rows = []
    for case in cases:
        case_id = case["id"]
        p, n = pobs[case_id], nobs[case_id]
        status, reason = "unavailable", n.get("reason")
        if n["status"] == "error":
            status, reason = "unexpected_execution_error", n.get("error")
        elif n["status"] == "ok":
            if case["expected_score"] == -1 and p["kind"] in {"invalid_student", "invalid_teacher", "invalid_option"}:
                status, reason = ("match_controlled_error", None) if n.get("controlled_error") is True else (
                    "unexpected_mismatch", "Authored controlled error was not observed in native CAS")
            elif p["kind"] != "result" or not isinstance(p.get("correct"), bool):
                status, reason = ("not_compared" if p["policy_status"] == "out_of_contract" else "unexpected_execution_error"), p.get("message")
            else:
                pv = {"cas_valid": p.get("cas_valid", p.get("valid")), "correct": p["correct"]}
                nv = {"cas_valid": n["cas_valid"], "correct": n["correct"]}
                if not isinstance(pv["cas_valid"], bool):
                    status, reason = "unexpected_execution_error", "Missing Python CAS validity"
                elif pv == nv:
                    status, reason = "match", None
                elif p["policy_status"] == "known_defect" and p["desired_match"] is False and n["correct"] == p["desired"]["correct"] and pv["cas_valid"] == nv["cas_valid"]:
                    status, reason = "known_port_defect", p.get("reason")
                elif case_id in exceptions and pv == exceptions[case_id]["python"] and nv == exceptions[case_id]["native"]:
                    status, reason = exceptions[case_id]["category"], exceptions[case_id]["reason"]
                else:
                    status, reason = "unexpected_mismatch", "Native and Python CAS applicability or correctness differ"
        rows.append({"case_id": case_id, "test": case["test"], "status": status, "reason": reason})
    verdicts = {row["case_id"]: row["status"] for row in rows}
    for case_id, entry in exceptions.items():
        if verdicts[case_id] != entry["category"]:
            raise ValueError(f"Stale or contradicted native policy for {case_id}: observed {verdicts[case_id]}")
    counts = dict(Counter(row["status"] for row in rows))
    failures = counts.get("unexpected_mismatch", 0) + counts.get("unexpected_execution_error", 0)
    return {"schema_version": 1, "engine": "compatibility", "fixture_sha256": digest,
            "python_report_sha256": hashlib.sha256(python_path.read_bytes()).hexdigest(),
            "native_report_sha256": hashlib.sha256(native_path.read_bytes()).hexdigest(),
            "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            "observations": rows, "summary": {"total": len(rows), **counts}, "passed": failures == 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/native_compliance/fixtures.json")
    parser.add_argument("--python", type=Path, default=ROOT / "test-results/compliance/python.json")
    parser.add_argument("--maxima", type=Path, default=ROOT / "test-results/compliance/maxima.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "tests/native_compliance/native_policy.json")
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/compliance/reference.json")
    args = parser.parse_args(argv)
    try:
        result = assess(args.fixture, args.python, args.maxima, args.policy)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"schema_version": 1, "engine": "compatibility", "passed": False,
                  "error": f"{type(exc).__name__}: {exc}", "observations": [], "summary": {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Native compatibility: {result.get('summary')} -> {args.output}")
    if result.get("error"):
        print(result["error"], file=sys.stderr)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
