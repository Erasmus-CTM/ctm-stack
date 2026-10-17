# Native STACK image execution

Native CI saves the installed Ubuntu Maxima GCL process after loading the
official STACK library at `10d323311b7f39fb7b092dd10ce75f7d8632f525`.
The saved image contains no answer-test observations or probe calls. Each case
starts a new OS process from that baseline, with a private user directory,
temporary directory, object directory and plot directory. No worker sessions
are reused. The independent small scalar reference harness remains cold.

The image builder supports GCL only and rejects another runtime. An explicit
`--image` never silently falls back to cold execution. Missing images, changed
runtime/source/builder identities and corrupt image bytes fail the run. Omitting
`--image` retains the existing cold process path for diagnostics and comparison.

`prepare_native_image.py --key-only` fingerprints the pinned clean STACK
checkout, absolute source location, Maxima wrapper and GCL binary hashes,
installed package versions, platform, architecture, GC settings, builder and
runner code. GitHub Actions caches the image under this exact key; there are no
partial restore keys. Cached image bytes are checked against their manifest.
The image is rebuilt on a cache miss; no checker outputs are cached.
The first implementation rejects ambient Maxima path/runtime overrides and
unsupported GCL options; it preserves and fingerprints the four GC defaults
used by the official wrapper. Cache hit/build status is recorded in the
image metadata of each native report.

`benchmark_native_image.py` checks cold/image fixture observation equality,
including applicability, marks, answer notes and controlled errors, plus both
loader diagnostic sets. Normal CI runs family sentinels and matrix fixtures;
the path-triggered `Native image full equivalence and performance` workflow
compares all 2,303 observation records, including 872 runnable rows and 1,431
unavailable records, when the implementation changes. Its
artifact records both full observations, same-run wall times and the ratio.
The 2,303-row inventory and existing native scope remain unchanged.

Local Ubuntu commands:

```sh
python scripts/prepare_native_image.py --stack-source .stack-upstream-reference
python scripts/benchmark_native_image.py --stack-source .stack-upstream-reference --image .native-stack-image --full
python scripts/run_compliance_maxima.py --stack-source .stack-upstream-reference --image .native-stack-image
```

Design consultation: Astra xhigh decision cycle 2 of the authorized 3 chose a
saved pristine image with a fresh process per case, preserving the current CAS
runtime and protocol. One decision cycle remains. Performance is an observed
CI result, not a promised fixed speedup; runner contention varies.
