# Form fixes and documented semantics — development audit

Base: `92c618b8392a8fb86d94815593dd195e0b3a007b`.
Upstream STACK: `10d323311b7f39fb7b092dd10ce75f7d8632f525`.
The imported 2,303-row fixture and its upstream bytes remain unchanged.

## Scope

Ten formerly pinned desired-result differences are resolved: 32, 37, 43
(bounded literal binary64 `AlgEquiv`); 80 (the explicitly documented symbolic
reciprocal-square-root convention); 166 (an exact principal-power exponential
proof); 645, 647, 658, 665 (held reciprocal form); and 2278 (numeric-fraction
sign context). Removing each exception is required for its new result to pass.

Eight domain/branch differences (50, 76, 92, 99, 101, 127, 155, 167) and two
missing proofs (471, 474) remain individually pinned. The report and its new
semantics page provide counterexamples/proof gaps, upstream evidence, and a
specific question for discussion with STACK. An implementation mechanism is
not presented as an author-approved mathematical rationale.

## Independent review

AC requested a separate **gpt-6-sol, xhigh** development audit. The auditor
made no edits and reviewed the runtime, fixtures, policy, documentation, and
report metadata/presentation against the pinned upstream sources.

- A high-severity finding identified an overbroad quotient-chain normalization:
  `a/b/c` had incorrectly been grouped as `a/(b*c)`. Pinned upstream fixtures
  at lines 1250–1257 require the optional `recipMul` rule to equate their held
  forms. The implementation was corrected to keep separate reciprocals, an
  existing unit expectation was corrected, and a portable native rejection
  control was added.
- The auditor identified that recursive reciprocal-root rewriting would extend
  the convention into logarithms and products. The final rewrite is top-level
  only, with rejection controls for nested logarithms and ratio/product roots.
- The proof-limitation tooltip was clarified: case 471 lacks a stated real-domain
  contract; the report must not imply one was supplied by the fixture.
- After the quotient correction the auditor reported no further source-proven
  blocker. Its focused read-only check passed 146 tests and 79 subtests, and
  `git diff --check` passed. Native/browser execution was outside that independent
  review's environment; the implementation agent ran the native checks below.

## Validation actually performed during development

- Non-rendering Python suite: **363 tests and 146 subtests passed**.
- CPython legacy conformance: **404 desired passes, 10 pinned differences,
  1,889 out of contract, zero unexpected**, over all 2,303 rows.
- Project regressions: **80 Python result passes, eight expected boundaries**.
  Native Maxima 5.46.0, with the pinned official STACK loader and isolated
  processes: **79 match desired, one pinned root-convention difference, eight
  outside native scope**. All 80 eligible native controls met their contract.
  This local diagnostic deliberately omitted browser parity and therefore did
  not pass the complete three-engine gate.
- Exact fixture-byte import check and committed browser-source bundle check
  passed. The refreshed 30-question corpus baseline has unchanged outcomes:
  18 qtest passes, one qtest mismatch, 11 unsupported imports/instantiations.

Local full-render tests were attempted but the downloaded Quarto 1.8.27 Dart
runtime failed with `Failed to retrieve stack bounds`; no rendering success
is claimed from that run. Local browser installation also failed, so browser
parity and rendered UI behavior require the GitHub workflow evidence linked
from the pull request. CI runs native legacy conformance, project regressions
in all three engines, the smaller native reference suite, rendering, and browser
integration before publication.

The public [semantics page source](../../compliance-report/semantics.qmd) is the
case-by-case discussion document. This audit is a bounded development record,
not a claim of complete STACK, Moodle-controller, or arbitrary-float parity.
