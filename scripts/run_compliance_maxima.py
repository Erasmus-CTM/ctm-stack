"""Run pinned STACK's native Maxima AT oracle over the extracted fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from native_compliance.maxima_runner import (NativeProcessError, NativeProtocolError,
                                             STACK_SHA, run_native, run_standalone_probe)


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/native_compliance/fixtures.json")
    parser.add_argument("--stack-source", type=Path, required=True)
    parser.add_argument("--maxima", default="maxima")
    parser.add_argument("--image", type=Path, help="validated preloaded GCL image directory")
    parser.add_argument("--output", type=Path, help="JSON output; defaults depend on --probe-only")
    parser.add_argument("--jobs", type=int, default=4, help="concurrent isolated Maxima case processes")
    parser.add_argument("--timeout", type=int, default=300, help="seconds per Maxima case process")
    parser.add_argument("--probe-only", action="store_true", help="one-process diagnostic; no fixture observations")
    args = parser.parse_args(argv)
    if args.output is None:
        filename = "maxima-loader-probe.json" if args.probe_only else "maxima.json"
        args.output = ROOT / "test-results/compliance" / filename
    if args.probe_only:
        report: dict = {"schema_version": 1, "engine": "maxima_diagnostic",
                        "metadata": {"reference_layer": "direct_official_maxima_AT",
                                     "stack_sha": STACK_SHA}, "probe": {}}
        try:
            report = run_standalone_probe(args.stack_source, args.maxima, timeout=args.timeout, image=args.image)
        except (OSError, TypeError, ValueError, NativeProcessError, NativeProtocolError) as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Maxima standalone diagnostic → {args.output}")
        if "error" in report:
            print(report["error"], file=sys.stderr)
            return 1
        return 0
    report: dict = {"schema_version": 1, "engine": "maxima", "metadata": {
        "reference_layer": "direct_official_maxima_AT", "stack_sha": STACK_SHA},
        "observations": [], "summary": {"total": 0, "ok": 0, "error": 0, "unavailable": 0}}
    try:
        fixture_bytes = args.fixture.read_bytes()
        fixture = json.loads(fixture_bytes)
        if fixture.get("schema_version") != 1 or fixture.get("upstream", {}).get("commit") != STACK_SHA:
            raise ValueError("Fixture is not from the pinned STACK revision")
        report = run_native(fixture["cases"], args.stack_source, args.maxima,
                            jobs=args.jobs, timeout=args.timeout, image=args.image)
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
