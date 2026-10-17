"""Reproduce the native STACK XML corpus baseline with the current adapter.

Run ``python scripts/check_corpus.py`` to write questions/corpus/baseline.json,
or ``python scripts/check_corpus.py --check`` to compare it with a fresh scan.
Each XML runs in a separate, time-limited process; no upstream checkout or
network access is required for a normal scan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "questions" / "corpus"
MANIFEST = CORPUS / "manifest.json"
BASELINE = CORPUS / "baseline.json"
UPSTREAM = ROOT.parent / "stack-upstream"
DEFAULT_SEEDS = (17, 29, 47)
TIMEOUT_SECONDS = 10
SOURCE_FILES = ("importer.py", "engine.py", "expressions.py", "assessment.py", "rendering.py", "collections.py", "collection_ops.py")


def _text(element: ET.Element, path: str) -> str:
    value = element.find(path)
    return "" if value is None or value.text is None else value.text.strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_manifest(manifest_path: Path = MANIFEST, *, verify_upstream: bool = False) -> list[dict]:
    """Check every byte digest and native export field before testing semantics."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["repository"] == "maths/moodle-qtype_stack"
    assert manifest["commit"] == "10d323311b7f39fb7b092dd10ce75f7d8632f525"
    assert manifest["source_base_url"].endswith("/" + manifest["commit"] + "/")
    assert manifest["license"]
    entries = manifest["questions"]
    assert len(entries) == 35, f"expected 35 questions, got {len(entries)}"
    assert len({item["file"] for item in entries}) == len(entries), "duplicate filenames"
    assert len({item["id"] for item in entries}) == len(entries), "duplicate IDs"
    assert len({item["upstream_path"] for item in entries}) == len(entries), "duplicate source paths"
    for item in entries:
        filename = item["file"]
        assert Path(filename).name == filename and filename.endswith(".xml"), filename
        path = manifest_path.parent / filename
        data = path.read_bytes()
        assert _sha256(data) == item["sha256"], f"digest mismatch: {filename}"
        assert item["source_url"] == manifest["source_base_url"] + item["upstream_path"], filename
        source = UPSTREAM / item["upstream_path"]
        assert source.resolve().is_relative_to(UPSTREAM.resolve()), filename
        if verify_upstream and source.exists():
            assert data == source.read_bytes(), f"modified upstream XML: {filename}"
        root = ET.fromstring(data)
        assert root.tag == "quiz", filename
        questions = [q for q in root.findall("question") if q.get("type") not in {"category", "description"}]
        assert len(questions) == 1 and questions[0].get("type") == "stack", filename
        q = questions[0]
        assert item["question_name"] == _text(q, "name/text"), filename
        assert item["input_count"] == len(q.findall("input")), filename
        assert sorted(item["answer_tests"]) == sorted({n.text.strip() for n in q.findall("prt/node/answertest") if n.text}), filename
        assert item["qtest_count"] == len(q.findall("qtest")), filename
        assert item["deployed_seeds"] == [int(s.text) for s in q.findall("deployedseed") if s.text], filename
        assert item["topic"] and item["qtest_count"] > 0 and item["input_count"] > 0, filename
    assert sorted(p.name for p in manifest_path.parent.glob("*.xml")) == sorted(item["file"] for item in entries), "manifest/XML files differ"
    return sorted(entries, key=lambda item: item["file"])


def seeds_for(entry: dict) -> list[int]:
    """Use at most three authored seeds, otherwise fixed adapter-local seeds."""
    return list(entry["deployed_seeds"][:3]) or list(DEFAULT_SEEDS)


def _diagnostic(exc: Exception) -> dict:
    return {"type": type(exc).__name__, "message": str(exc),
            **({"location": exc.location, "reason": exc.reason} if hasattr(exc, "location") else {})}


def replay_one(entry: dict) -> dict:
    """Run inside a subprocess so expensive symbolic work cannot block CI."""
    from stack_sympy.engine import instantiate, run_question_tests
    from stack_sympy.importer import UnsupportedQuestion, import_xml

    result = {"id": entry["id"], "file": entry["file"], "seeds": seeds_for(entry),
              "status": "error", "imported_questions": 0, "instantiated_seeds": [],
              "native_qtests": entry["qtest_count"], "replayed_cases": 0,
              "failed_cases": 0, "failed_checks": 0, "mismatches": []}
    try:
        questions = import_xml(CORPUS / entry["file"])
        result["imported_questions"] = len(questions)
        if len(questions) != 1:
            raise ValueError(f"expected one STACK question, imported {len(questions)}")
    except Exception as exc:
        result.update(status="unsupported_import" if isinstance(exc, UnsupportedQuestion) else "error",
                      diagnostic=_diagnostic(exc))
        return result
    question = questions[0]
    variants = []
    for seed in result["seeds"]:
        try:
            variants.append(instantiate(question, seed))
            result["instantiated_seeds"].append(seed)
        except Exception as exc:
            result.update(status="unsupported_instantiate" if isinstance(exc, UnsupportedQuestion) else "error",
                          diagnostic={"seed": seed, **_diagnostic(exc)})
            return result
    for variant in variants:
        try:
            replay = run_question_tests(question, variants=[variant])
        except Exception as exc:
            result.update(status="unsupported_qtest" if isinstance(exc, UnsupportedQuestion) else "error",
                          diagnostic={"seed": variant["seed"], **_diagnostic(exc)})
            return result
        for case in replay["results"]:
            result["replayed_cases"] += 1
            failed = [check for check in case["checks"] if not check["passed"]]
            if not case["passed"]:
                result["failed_cases"] += 1
                result["failed_checks"] += len(failed)
                result["mismatches"].append({"seed": case["seed"], "testcase": case["testcase"],
                                             "inputs": case["inputs"], "checks": failed,
                                             **({"reason": "no expected PRT checks"} if not case["checks"] else {})})
    result["status"] = "qtests_mismatch" if result["failed_cases"] else "qtests_pass"
    return result


def _worker(filename: str) -> None:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["questions"]
    entry, = [item for item in entries if item["file"] == filename]
    print(json.dumps(replay_one(entry), sort_keys=True))


def _source_digest() -> str:
    parts = [((ROOT / "_extensions/stack-sympy/stack_sympy" / f).read_bytes()) for f in SOURCE_FILES]
    return _sha256(b"\0".join(parts))


def generate(timeout: int = TIMEOUT_SECONDS) -> dict:
    entries = validate_manifest(verify_upstream=True)
    rows = []
    for entry in entries:
        try:
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", entry["file"]],
                                     cwd=ROOT, text=True, capture_output=True, timeout=timeout)
            if process.returncode:
                row = {"id": entry["id"], "file": entry["file"], "seeds": seeds_for(entry),
                       "status": "error", "diagnostic": {"type": "WorkerFailure",
                       "message": (process.stderr or process.stdout)[-2000:]}}
            else:
                row = json.loads(process.stdout)
        except subprocess.TimeoutExpired:
            row = {"id": entry["id"], "file": entry["file"], "seeds": seeds_for(entry),
                   "status": "timeout", "diagnostic": {"type": "TimeoutExpired", "message": f"per-file timeout: {timeout}s"}}
        rows.append(row)
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unknown"
    import sympy
    return {"schema_version": 1, "engine_revision": revision, "adapter_source_sha256": _source_digest(),
            "python_version": platform.python_version(), "sympy_version": sympy.__version__,
            "seed_policy": "first three deployed seeds, or adapter-local 17,29,47 (not Maxima parity)",
            "timeout_seconds_per_file": timeout,
            "summary": {"total": len(rows), "stages": dict(sorted(Counter(row["status"] for row in rows).items())),
                        "imported": sum(row.get("imported_questions", 0) == 1 for row in rows),
                        "instantiated_all_seeds": sum(len(row.get("instantiated_seeds", [])) == len(row["seeds"]) for row in rows),
                        "replayed_cases": sum(row.get("replayed_cases", 0) for row in rows),
                        "failed_cases": sum(row.get("failed_cases", 0) for row in rows),
                        "failed_checks": sum(row.get("failed_checks", 0) for row in rows)},
            "questions": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the recorded baseline differs from a fresh run")
    parser.add_argument("--worker", metavar="FILE", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS, help="per-file worker timeout in seconds")
    args = parser.parse_args()
    if args.worker:
        _worker(args.worker)
        return 0
    report = generate(args.timeout)
    if args.check:
        recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
        # The baseline identifies the revision/runtime where it was recorded;
        # CI may run that same adapter source on a later commit or Python patch.
        comparable = ("schema_version", "adapter_source_sha256", "seed_policy",
                      "timeout_seconds_per_file", "summary", "questions")
        differing = [key for key in comparable if recorded.get(key) != report.get(key)]
        if differing:
            print(f"Corpus baseline drift in {', '.join(differing)}; run python scripts/check_corpus.py", file=sys.stderr)
            return 1
        print(f"Corpus baseline matches: {report['summary']}")
    else:
        BASELINE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {BASELINE}: {report['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
