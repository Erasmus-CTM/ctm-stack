# Project-owned port regressions

`fixtures.json` records discoveries made while porting STACK and controls that
prevent over-broad fixes. It is separate from the unchanged 2,303 imported
upstream rows. Each stable `port-*` ID has an expected result, group, reason,
and origin; an upstream ordinal links a discovery to the legacy inventory
without presenting the new case as upstream-authored.

The fixture pins syntax validity, CAS applicability, and the mathematical mark
separately. Explicit unsupported/error cases are **boundary checks**, not
mathematical compatibility passes. The resolved `EqualComAss` division-form
case now asserts the desired rejection, with nearby native acceptance controls.
The negative-real fifth-root case separately
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

Documented native semantics cases cover held reciprocal structure, sign context
in `LowestTerms`, bounded literal binary64 arithmetic, the symbolic reciprocal
square-root convention, and a principal logarithmic-power proof. These include
nearby rejection controls and do not change the upstream fixture. See
`compliance-report/semantics.qmd` for the exact scope, upstream motivations, and
the remaining questions for the STACK author.

Finite collection controls cover ordered list positions and length, per-element
binary64 behavior, unordered sets and repetitions, detailed `Sets` feedback,
structural set normalization, type applicability, and flat/scalar/size boundaries.
The unchanged legacy rows separately expose the radical normalization difference
in row 212; it is not counted as a mathematical or native pass.

Nested controls compare recursive list values, lists inside sets, inner-set
normalization and outer duplicate feedback, SameType applicability (including
length mismatches), held collection EqualComAss and finite author helpers.
Former nesting boundaries now assert explicit supported type mismatches.
Depth, total-tree size, scalar-leaf, helper arity/type, ordering and learner-call
boundaries remain separate from mathematical passes.
