"""Run pinned STACK's native Maxima AT oracle over the extracted fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from native_compliance.maxima_runner import NativeProcessError, NativeProtocolError, STACK_SHA, run_native


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/native_compliance/fixtures.json")
    parser.add_argument("--stack-source", type=Path, required=True)
    parser.add_argument("--maxima", default="maxima")
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/compliance/maxima.json")
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=300, help="seconds per Maxima batch")
    args = parser.parse_args(argv)
    report: dict = {"schema_version": 1, "engine": "maxima", "metadata": {
        "reference_layer": "direct_official_maxima_AT", "stack_sha": STACK_SHA},
        "observations": [], "summary": {"total": 0, "ok": 0, "error": 0, "unavailable": 0}}
    try:
        fixture_bytes = args.fixture.read_bytes()
        fixture = json.loads(fixture_bytes)
        if fixture.get("schema_version") != 1 or fixture.get("upstream", {}).get("commit") != STACK_SHA:
            raise ValueError("Fixture is not from the pinned STACK revision")
        report = run_native(fixture["cases"], args.stack_source, args.maxima,
                            chunk_size=args.chunk_size, timeout=args.timeout)
        report["metadata"]["fixture_sha256"] = hashlib.sha256(fixture_bytes).hexdigest()
    except (OSError, KeyError, TypeError, ValueError, NativeProcessError, NativeProtocolError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Maxima observations: {report['summary']} → {args.output}")
    if "error" in report:
        print(report["error"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
