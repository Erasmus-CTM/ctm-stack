"""Report joins only same-fixture observations and preserves distinct axes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from native_compliance.report import ROOT, assemble
from native_compliance.compatibility import assess


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def inputs(tmp_path: Path):
    cases = [{"id": "a", "ordinal": 1, "test": "AlgEquiv", "student": "x+1", "teacher": "x",
              "options": "", "expected_score": -2, "answer_note": "", "source_line": 5},
             {"id": "b", "ordinal": 2, "test": "UnsupportedTest", "student": "1", "teacher": "1",
              "options": "", "expected_score": 1, "answer_note": "", "source_line": 8}]
    fixture = write(tmp_path / "fixture.json", {"schema_version": 1, "cases": cases,
                  "upstream": {"commit": "pinned", "source_url": "https://github.com/org/repo/blob/pinned/source.php"},
                  "inventory": {"total_rows": 2}})
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    python = write(tmp_path / "python.json", {"schema_version": 1, "engine": "python", "passed": False,
                   "metadata": {"fixture_sha256": digest,
                                "policy_sha256": hashlib.sha256((ROOT / "tests/native_compliance/policy.json").read_bytes()).hexdigest()},
                   "observations": [
                       {"case_id": "a", "kind": "result", "valid": True, "correct": True,
                        "desired_match": False, "policy_status": "unexpected"},
                       {"case_id": "b", "kind": "unsupported", "desired_match": False,
                        "policy_status": "out_of_contract"}]})
    maxima = write(tmp_path / "maxima.json", {"schema_version": 1, "engine": "maxima",
                   "metadata": {"fixture_sha256": digest, "stack_sha": "pinned", "native_scope_sha256": "0" * 64}, "observations": [
                       {"case_id": "a", "status": "ok", "cas_valid": True, "correct": True},
                       {"case_id": "b", "status": "unavailable", "reason": "outside scope"}]})
    parity = write(tmp_path / "parity.json", {"schema_version": 1, "engine": "parity", "passed": True, "fixture_sha256": digest,
                   "cases": [{"id": "a", "match": True}, {"id": "b", "match": True}]})
    reference = write(tmp_path / "reference.json", {"schema_version": 1, "engine": "compatibility", "passed": True,
                      "fixture_sha256": digest,
                      "policy_sha256": hashlib.sha256((ROOT / "tests/native_compliance/native_policy.json").read_bytes()).hexdigest(),
                      "python_report_sha256": hashlib.sha256(python.read_bytes()).hexdigest(),
                      "native_report_sha256": hashlib.sha256(maxima.read_bytes()).hexdigest(),
                      "observations": [
                          {"case_id": "a", "status": "match"}, {"case_id": "b", "status": "unavailable"}]})
    pdata = json.loads(parity.read_text())
    pdata["python_report_sha256"] = hashlib.sha256(python.read_bytes()).hexdigest()
    write(parity, pdata)
    return fixture, python, maxima, parity, reference


def test_separate_desired_native_and_parity_axes(tmp_path):
    report = assemble(*inputs(tmp_path))
    a, b = report["cases"]
    assert (a["desired_status"], a["native_status"], a["native_desired_status"], a["parity_status"]) == (
        "unexpected", "match", "upstream_negative_sentinel_difference", "match")
    assert b["native_status"] == "unavailable"
    assert report["provenance"]["fixture_upstream"]["commit"] == "pinned"


def test_same_final_mark_can_have_different_cas_applicability(tmp_path):
    fixture, python, maxima, parity, reference = inputs(tmp_path)
    data = json.loads(python.read_text())
    data["observations"][0]["cas_valid"] = False
    write(python, data)
    report = assemble(fixture, python, maxima, parity, reference)
    row = report["cases"][0]
    assert row["native_mark_status"] == "match"
    assert row["native_applicability_status"] == "mismatch"
    assert report["summary"]["native_applicability"]["mismatch"] == 1


def test_missing_or_stale_run_is_explicitly_unavailable(tmp_path):
    fixture, python, maxima, parity, reference = inputs(tmp_path)
    parity.unlink()
    report = assemble(fixture, python, maxima, parity, reference)
    assert not report["results"]["parity"]["available"]
    assert report["summary"]["parity"] == {"unavailable": 2}
    stale = json.loads(maxima.read_text())
    stale["metadata"]["fixture_sha256"] = "older-run"
    write(maxima, stale)
    report = assemble(fixture, python, maxima, parity, reference)
    assert "mismatch" in report["results"]["native"]["error"]
    assert report["summary"]["native"] == {"unavailable": 2}


def test_parity_cannot_use_a_different_python_run(tmp_path):
    fixture, python, maxima, parity, reference = inputs(tmp_path)
    data = json.loads(parity.read_text())
    data["python_report_sha256"] = "stale"
    write(parity, data)
    report = assemble(fixture, python, maxima, parity, reference)
    assert report["summary"]["parity"] == {"unavailable": 2}
    assert "source mismatch" in report["results"]["parity"]["error"]


def test_duplicate_or_partial_observations_cannot_be_accepted(tmp_path):
    fixture, python, maxima, parity, reference = inputs(tmp_path)
    data = json.loads(python.read_text())
    data["observations"] = [data["observations"][0]] * 2
    write(python, data)
    report = assemble(fixture, python, maxima, parity, reference)
    assert not report["results"]["python"]["available"]
    assert report["summary"]["desired"] == {"unavailable": 2}


def test_native_gate_rejects_unapproved_difference_and_stale_inputs(tmp_path, monkeypatch):
    fixture, python, maxima, _, _ = inputs(tmp_path)
    monkeypatch.setattr("native_compliance.compatibility.scope_sha256", lambda cases: "0" * 64)
    monkeypatch.setattr("native_compliance.compatibility._unavailable",
                        lambda case: "outside scope" if case["test"] == "UnsupportedTest" else None)
    policy = write(tmp_path / "native_policy.json", {"schema_version": 1, "native_scope_sha256": "0" * 64, "cases": {}})
    result = assess(fixture, python, maxima, policy)
    assert result["summary"]["match"] == 1
    assert result["summary"]["unavailable"] == 1
    data = json.loads(maxima.read_text())
    data["observations"][0]["correct"] = False
    write(maxima, data)
    result = assess(fixture, python, maxima, policy)
    assert not result["passed"] and result["summary"]["unexpected_mismatch"] == 1
    data["metadata"]["fixture_sha256"] = "stale"
    write(maxima, data)
    import pytest
    with pytest.raises(ValueError, match="Fixture SHA-256 mismatch"):
        assess(fixture, python, maxima, policy)


def test_native_failure_label_requires_upstream_negative_sentinel(tmp_path, monkeypatch):
    fixture, python, maxima, _, _ = inputs(tmp_path)
    monkeypatch.setattr("native_compliance.compatibility.scope_sha256", lambda cases: "0" * 64)
    policy = write(tmp_path / "native_policy.json", {"schema_version": 1, "native_scope_sha256": "0" * 64,
                   "cases": {"b": {"category": "known_native_mathematical_failure",
                                   "reason": "Incorrectly labeled non-sentinel",
                                   "python": {"cas_valid": True, "correct": True},
                                   "native": {"cas_valid": True, "correct": False}}}})
    import pytest
    with pytest.raises(ValueError, match="Invalid known native mathematical failure"):
        assess(fixture, python, maxima, policy)


def test_reviewed_native_exception_cannot_silently_improve(tmp_path, monkeypatch):
    fixture, python, maxima, _, _ = inputs(tmp_path)
    monkeypatch.setattr("native_compliance.compatibility.scope_sha256", lambda cases: "0" * 64)
    monkeypatch.setattr("native_compliance.compatibility._unavailable",
                        lambda case: "outside scope" if case["test"] == "UnsupportedTest" else None)
    policy = write(tmp_path / "native_policy.json", {"schema_version": 1, "native_scope_sha256": "0" * 64,
                   "cases": {"a": {"category": "approved_difference", "reason": "Previously reviewed mark difference",
                                   "python": {"cas_valid": True, "correct": True},
                                   "native": {"cas_valid": True, "correct": False}}}})
    import pytest
    with pytest.raises(ValueError, match="Stale or contradicted native policy"):
        assess(fixture, python, maxima, policy)


def test_python_controlled_error_requires_authored_origin(tmp_path):
    fixture, python, maxima, parity, reference = inputs(tmp_path)
    import pytest
    for note, kind in [("ATAlgEquiv_STACKERROR_SAns.", "invalid_option"),
                       ("unknown error note", "invalid_student")]:
        source = json.loads(fixture.read_text())
        source["cases"][0].update(expected_score=-1, answer_note=note)
        write(fixture, source)
        observed = json.loads(python.read_text())
        observed["metadata"]["fixture_sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        observed["observations"][0].update(kind=kind, desired_match=True, policy_status="pass")
        observed["passed"] = True
        write(python, observed)
        report = assemble(fixture, python, maxima, parity, reference)
        assert report["results"]["python"]["error"].startswith("Contradictory Python desired mark")
        assert report["summary"]["desired"] == {"unavailable": 2}


def test_native_controlled_error_requires_exact_asserted_note(tmp_path, monkeypatch):
    fixture, python, maxima, _, _ = inputs(tmp_path)
    source = json.loads(fixture.read_text())
    source["cases"][0].update(expected_score=-1, answer_note="ATAlgEquiv_STACKERROR_SAns.")
    write(fixture, source)
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    observed = json.loads(python.read_text())
    observed["metadata"]["fixture_sha256"] = digest
    observed["observations"][0].update(kind="invalid_student", desired_match=True, policy_status="pass")
    observed["passed"] = True
    write(python, observed)
    native = json.loads(maxima.read_text())
    native["metadata"]["fixture_sha256"] = digest
    native["observations"][0].update(cas_valid=False, correct=False, controlled_error=True,
                                      answer_note="ATAlgEquiv_STACKERROR_TAns.")
    write(maxima, native)
    monkeypatch.setattr("native_compliance.compatibility.scope_sha256", lambda cases: "0" * 64)
    monkeypatch.setattr("native_compliance.compatibility._unavailable",
                        lambda case: "outside scope" if case["test"] == "UnsupportedTest" else None)
    policy = write(tmp_path / "native_policy.json", {"schema_version": 1, "native_scope_sha256": "0" * 64, "cases": {}})
    result = assess(fixture, python, maxima, policy)
    assert not result["passed"]
    assert result["observations"][0]["status"] == "unexpected_mismatch"


def test_note_display_is_independent_of_python_error_origin(tmp_path):
    fixture, python, maxima, parity, reference = inputs(tmp_path)
    fixture_data = json.loads(fixture.read_text())
    fixture_data["cases"][0].update(expected_score=-1, answer_note="ATAlgEquiv_STACKERROR_SAns.")
    write(fixture, fixture_data)
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    python_data = json.loads(python.read_text())
    python_data["metadata"]["fixture_sha256"] = digest
    python_data["observations"][0].update(kind="invalid_option", desired_match=False, policy_status="unexpected")
    write(python, python_data)
    native_data = json.loads(maxima.read_text())
    native_data["metadata"]["fixture_sha256"] = digest
    native_data["observations"][0].update(cas_valid=False, correct=False, controlled_error=True,
                                           answer_note="ATAlgEquiv_STACKERROR_SAns.  ")
    write(maxima, native_data)
    report = assemble(fixture, python, maxima, parity, reference)
    assert report["cases"][0]["answer_note_status"] == "controlled_error_note_matched"
    assert report["cases"][0]["desired_status"] == "unexpected"
