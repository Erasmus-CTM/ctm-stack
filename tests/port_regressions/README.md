# Project-owned port regressions

`fixtures.json` records discoveries made while porting STACK and controls that
prevent over-broad fixes. It is separate from the unchanged 2,303 imported
upstream rows. Each stable `port-*` ID has an expected result, group, reason,
and origin; an upstream ordinal links a discovery to the legacy inventory
without presenting the new case as upstream-authored.

The fixture pins syntax validity, CAS applicability, and the mathematical mark
separately. Explicit unsupported/error cases are **boundary checks**, not
mathematical compatibility passes. A remaining `EqualComAss` division-form
defect has a case-specific observation pin: silently fixing it fails the check
until its exception is removed. The negative-real fifth-root case separately
records Maxima's real-root convention versus SymPy's principal-complex power
convention; it is not labeled a native mathematical failure.

Run `python scripts/run_port_regressions.py --stack-source /pinned/STACK` after
installing the project development requirements, Maxima, and Playwright
Chromium. This runs isolated CPython cases, official native STACK calls for
eligible cases, and the same portable evaluator in a browser Pyodide worker.
`--without-browser` is a local diagnostic: the resulting report is explicitly
incomplete and does not pass the overall gate.

The independent CI job uploads `compliance-port-regressions`. Report assembly
checks the fixture hash, source bundle hash, preparation marker, complete case
coverage, contract fields, and verdicts. The **Port regressions** page and its JSON download have separate counts and filters. Missing runners remain
unavailable; legacy percentages and denominators do not change.

Keep cross-cutting parser/AST/numeric-screen unit tests in the normal Python
suite and end-to-end XML/validation tests in `tests/browser.py`. Add portable
answer-test discoveries here, including a nearby negative control whenever a
new proof strategy accepts a new form.

Logical-operator cases link to upstream rows 495–498 and 500: `implies`, `xor`,
and `xnor` must parse and grade, including a directional implication control
and STACK’s parity semantics for chained `xnor`. Numerical-option cases link
to rows 1697 and 1735. The `NumAbsolute`/`NumRelative` branch of STACK’s
`stack/answertest/controller.class.php` replaces an absent or syntactically
invalid option with `0.05`; the port follows that behavior for malformed
syntax in its supported grammar. A parseable but invalid tolerance such as
`1/0`, `x`, or `%i` is still an error. Acceptance controls prevent implementing
the malformed-option cases as unconditional rejection.

Corpus function regressions cover the `ln` alias, polynomial GCD numeric
content, signed/zero-divisor modulo, and reduction modulo a real multiple of
pi. An integral `SingleFrac` control reproduces the native form behavior
behind the AlgMap-8.10 upstream PRT authoring bug. Symbolic complex logarithms
retain an explicit boundary until branch-aware proof machinery is available.
