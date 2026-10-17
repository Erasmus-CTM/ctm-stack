# PythonChecker v1 design and implementation audit

This is a historical audit of the initial implementation. Custom checker
loading has since been simplified to filename selection without source digest
checks; see [the follow-up](filename-checkers-and-spd.md) and the
[current author guide](../python-checker-api.qmd).

## Source and scope

Follow-up to `feature/python-custom-checkers` at
`1490f17910f0498d225c1079e6a02864f6869da0`, based on main
`6b45c4903692f5fdf6e234dad4415d08abe8f34f`.
`python-checker-inputs.json` records all 207 input files and Git blob hashes.
The pinned source archive was materialized after Git clone failed. Local
snapshot Git is a diff aid, not upstream provenance; remote commits use the
real branch parent and a checked branch-head lease.

The original branch added IsBasis and MatrixProperty but not a general custom
checker API. This follow-up adds the explicit `PythonChecker` entry point,
module selection in Quarto/CLI, a documented versioned value/result contract,
and the same embedded source in CPython and Pyodide. Native test names, native
eligibility, the 2,303 upstream rows, corpus XML and math helper provenance are
unchanged.

## Independent design audit before implementation

At AC's explicit request, **Astra xhigh** reviewed the architecture and proposed
API before any API implementation. The revised v1 design was approved subject
to implementation checks. The central decisions were:

- Explicit trusted author file; XML only selects a case-sensitive registry ID.
- A 64 KiB source descriptor with API version 1 and SHA-256, without local paths.
- `checker(student, teacher)` with immutable scalar/matrix/held values; no raw
  source, environment context or callback-owned scores.
- Actual bool or strict valid/correct result, optional plain-text feedback and
  dimension-checked matrix diagnostics; no ambiguous note/score fields.
- Fresh module namespace per invocation; no global registry mutation or callable
  cache; synchronous signatures/results; discard author stdout/stderr.
- Import, instantiate and Validate do not execute author modules. Explicit build
  preflight checks all registry references, then follows actual model PRT paths.
  A predicate may correctly return false. No implicit full-credit requirement.
- Keep generic dispatch outside native applicability restrictions and separate
  from the two rational-only matrix builtins.
- Author exceptions remain errors; deliberate invalid results mark the direct
  learner input invalid; successful diagnostic text is escaped before HTML use.

Held sets and logical expressions retain repetitions and multiplicity instead
of being silently converted into simplifying SymPy sets/Boolean expressions.
The public `checker_api` facade exposes those immutable values plus normal
SymPy ImmutableMatrix ergonomics. Author code remains trusted and public, not
sandboxed; imported module state and third-party package installation are not
isolated/provided by this API.

## Independent implementation review

Astra xhigh reviewed the implementation separately and reproduced issues before
their fixes. Corrections include:

- Prepare model answers through the qtest conversion path, allowing author-only
  expressions without treating them as student syntax.
- Retain static true/false branch CASText validation for custom nodes, including
  unreachable branches, without eagerly evaluating guarded teacher expressions.
- Invoke callbacks with the already validated student value; avoid rebinding an
  input's own symbolic name and changing the displayed answer before grading.
- Wrap module-level and callback SystemExit as contextual author errors.
- Detect async/generator functions, callable objects and partials when validating
  references, in addition to rejecting asynchronous runtime results.

Regression tests cover these discoveries, schema/source failures, scalar and
symbolic/irrational matrix values, held list/set/equation/logic structure,
assessment and quiet nodes, printed output, qtest order, variants and two
questions using the same ID with different source. The browser test uses the
actual Worker/Pyodide and compares complete qtest results with CPython; it also
checks invalid feedback, literal HTML-looking feedback, card isolation, reset,
variant clearing and AI prompt exclusions.

## Documentation audit

A separate independent read-only review identified and corrected the Moodle
reimport qualification, incomplete unittest command, a time-sensitive pending-PR
label, color wording that overstated independence when red columns coexist,
and the missing general API contract. The builtins' rational-domain description
is now distinguished from the generic API. The author guide links the complete
API, portability contract and executable positive-multiple example.

## Final validation evidence

Tested implementation: `3c995cd310c4bc2f30f747604d4b9cccfa51549e`.
[Complete Linux workflow](https://github.com/Erasmus-CTM/stack-sympy/actions/runs/39053500680)
passed, including publication of the tested feature preview and matching reports.

| Check | Computed result |
|---|---|
| Python/unit/render suite | 769 passed; 149 subtests passed; 1 skipped |
| Real browser suite | 13 passed, including the new author-module test |
| Fresh corpus scan | Baseline matches: 35 originals, 23 passing questions, 1 known mismatch, 11 unsupported questions, 162 replayed cases |
| Independent scalar native reference | 65 of 65 match |
| Legacy Python desired outcomes | All 2,303 inventory rows classified; zero unexpected outcomes |
| Official STACK/Maxima observations and comparison | Passed |
| Legacy CPython/Pyodide parity | Passed |
| Project regressions across Python, native STACK and Pyodide | Passed |
| Inspectable report assembly and publication | Passed |

The new browser test compares complete custom-checker qtest results against
CPython using the same embedded descriptor and source. It also checks fresh
state, two cards with the same ID and different source, invalid feedback,
literal HTML-looking feedback, editing/reset/variant clearing and AI prompt
exclusions. The pre-existing matrix/basis/feedback browser tests also pass.

Local focused API/builtin/importer/engine checks passed 115 tests and 27
subtests. The API file alone passed 47 tests. Runtime bundle freshness,
corpus-page generator equality and the complete runtime source fingerprint
were checked. All regenerated corpus question records and summary compare
equal to the original branch baseline; native source XML is untouched.

Original branch run 39048871211 had stopped at source-fingerprint drift. The
first follow-up Linux run on `b65d548` exposed corpus-page copy drift when JSON
serialization changed 1.0 to 1; restoring the Python generator's numeric format
resolved it. The final passing run above supersedes those incomplete runs.
Local Windows Quarto attempts were blocked by Deno cache/CMD environment
errors; render/browser success is established by the Linux evidence above.

Astra xhigh approved the revised design before implementation and approved the
final implementation, tests, documentation and quiet-result correction with no
remaining blocking findings. A separate independent documentation review
confirmed the public contract and identified the final quiet-result fix.
Final CI evidence was independently reviewed against the exact implementation
SHA. Audit-record-only updates after that SHA do not change runtime sources,
examples, tests or the baseline.

## Runs needed

None for the requested API, browser-validation and documentation-audit scope.
Existing declared native incompatibilities and unsupported cases remain visible
and are not represented as compatibility successes. No PR is merged automatically.
