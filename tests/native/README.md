# Native transport qualification

`accepted-programs.json.gz` freezes the **11 preparation programs and 316
controller programs** from the accepted production-profile build
[40244258581](https://github.com/Erasmus-CTM/stack-wasm-maxima/actions/runs/40244258581),
tested merge `d3ae000d86f165e537d08c0ec9d1ebf7724e6bd2` in
Erasmus-CTM/stack-wasm-maxima. Sources are `site/native/build-manifest.json`
and `test-results/milestone-three/browser.json` in its build artifact. Only
`expression` and `result` were retained, renamed `expression` and `expected`,
in that order. The decompressed fixture SHA-256 is
`d8221715e88e284f22f5ab62ac7dd7511c3b22d0a81947b55d2f0ab233eaff61`.
Compression uses gzip with mtime zero. Generated programs and the source
controller are AGPL-3.0-or-later; the pinned STACK library is GPL-3.0-or-later.

Both new transports must reproduce every complete JSON result exactly. The
earlier build already checked these programs against independent Maxima and
same-source native ECL references. This is **transport regression evidence**;
it is not fresh execution of the UI/controller, independent verification of
the mathematical grading rules, or Moodle PHP-controller compatibility.
The original same-source and independent-reference presentation classifications
remain in the runtime repository's acceptance evidence.

`gc-stress.mjs` sets GC_FREE_SPACE_DIVISOR=1000 before ECL starts and repeats
the eight exact previously failing `[1,1]`/`[2,2]` validations 400 times, then
replays all 327 programs. Its before/after GC counters must prove collection
occurred during the calls. It changes neither v3 bytes nor its normal startup
configuration and exposes no Lisp message endpoint.

`integration.mjs` also checks ordinary CAS errors, internal Lisp faults,
Unicode including a supplementary-plane character, worker replacement,
namespace clearing, a real unbounded loop, whole-batch cache hit/invalidation,
and rejection of a coherently forged STACK source inventory.
`session.test.mjs` supplies deterministic watchdog and stale-message controls.
`browser.py` serves a page without isolation headers, asserts that
SharedArrayBuffer is unavailable, and runs all 327 programs through the same
direct-call core. CI covers Node 22/24 and Chromium/Firefox/WebKit.
