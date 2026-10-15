"""Protocol and coverage checks that do not require a browser download."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_compliance_pyodide import (compare_observations, load_fixture,
                                    validate_bundle, validate_observations)


CASES = [{"id": "case-one", "test": "AlgEquiv"},
         {"id": "case-two", "test": "FacForm"}]


def _result(case: dict, **changes):
    return {"case_id": case["id"], "test": case["test"],
            "kind": "result", "valid": True, "correct": True, "note": "same", **changes}


def test_parity_uses_all_cases_and_only_semantic_fields():
    native = [_result(case, elapsed_ms=20, expected_score=1, policy_status="pass") for case in CASES]
    browser = [_result(case, elapsed_ms=77) for case in CASES]
    rows, summary = compare_observations(CASES, native, browser)
    assert all(row["match"] for row in rows)
    assert summary["total"] == summary["matched"] == 2
    assert summary["python_observed"] == summary["pyodide_observed"] == 2
    assert summary["eligible"] == summary["eligible_matched"] == 2
    browser[1]["correct"] = False
    rows, summary = compare_observations(CASES, native, browser)
    assert [row["match"] for row in rows] == [True, False]
    assert summary["mismatched"] == 1
    assert summary["eligible_matched"] == 1


def test_missing_reordered_and_unknown_cases_fail_coverage():
    observations = [_result(case) for case in CASES]
    with pytest.raises(ValueError, match="coverage"):
        validate_observations(CASES, observations[:1], "pyodide")
    with pytest.raises(ValueError, match="order/identity"):
        validate_observations(CASES, observations[::-1], "pyodide")
    with pytest.raises(ValueError, match="kind"):
        validate_observations(CASES, [dict(observations[0], kind="mystery"), observations[1]], "pyodide")


def test_matching_faults_are_not_successes():
    for kind in ("timeout", "unexpected_exception"):
        native = [_result(CASES[0], kind=kind), _result(CASES[1])]
        rows, summary = compare_observations(CASES, native, [dict(item) for item in native])
        assert rows[0]["match"] is False
        assert summary["mismatched"] == 1
        assert summary["python_faults"] == summary["pyodide_faults"] == 1


def test_unsupported_rows_are_accounted_separately():
    outside = {"case_id": CASES[0]["id"], "test": CASES[0]["test"],
               "kind": "unsupported", "message": "outside subset", "scope": "unsupported"}
    native = [outside, _result(CASES[1], scope="supported")]
    browser = [{k: v for k, v in outside.items() if k != "scope"}, _result(CASES[1])]
    rows, summary = compare_observations(CASES, native, browser)
    assert rows[0]["eligible"] is False
    assert summary["total"] == 2 and summary["eligible"] == 1
    assert summary["unsupported_agreement"] == summary["eligible_matched"] == 1


def test_fixture_sha_and_unique_identity(tmp_path):
    fixture = tmp_path / "fixtures.json"
    fixture.write_text(json.dumps({"schema_version": 1, "cases": CASES}), encoding="utf-8")
    cases, digest = load_fixture(fixture)
    assert cases == CASES and len(digest) == 64
    fixture.write_text(json.dumps({"schema_version": 1, "cases": [CASES[0], CASES[0]]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_fixture(fixture)


def test_parity_worker_executes_portable_python_with_current_bundle():
    assert len(validate_bundle()) == 64
    worker = (ROOT / "scripts/native_compliance/pyodide_worker.js").read_text(encoding="utf-8")
    harness = (ROOT / "scripts/native_compliance/pyodide_harness.html").read_text(encoding="utf-8")
    assert "from native_compliance.python_runner import evaluate_case" in worker
    assert "await instance.loadPackage('sympy')" in worker
    assert "runtime-sources.js" in worker
    assert "worker.terminate()" in harness
