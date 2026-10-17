# PythonChecker v1 design and implementation audit

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

## Validation evidence

The original branch CI run 39048871211 passed 722 tests and 149 subtests, with
one skip, and passed native reference/compliance, project regressions and
CPython/Pyodide parity. It stopped at corpus fingerprint drift before browser
tests/publication. These are historical results on `1490f17`, not validation of
the new API.

The initial local regenerated baseline had identical question records and
summary: 35 originals, 23 passing questions, 1 known mismatch, 3 unsupported
imports, 8 unsupported instantiations, 162 replayed cases and 2 failed checks.
Only revision/runtime/source fingerprint fields changed. The fingerprint now
includes every runtime Python module rather than a manually incomplete list.

Local focused API/builtin/importer/engine run: 115 tests and 27 subtests passed
under Python 3.12.10, SymPy 1.13.3, pytest 9.1.1. Astra xhigh approved the final core implementation, tests and API documentation
with no remaining blocking findings; exact-head Linux/browser CI is still
pending. A broader Windows run passed 739 tests and 149 subtests with one skip;
six native-runner tests hit missing symlink privileges, one native-image mock
hit a zero-resolution timer, and one parity check saw a runtime bundle made
stale by a subsequent signature fix. The bundle was regenerated and the
focused API/parity run then passed 49 tests. The first Linux run on `b65d548` passed 765 tests and 149 subtests (1 skip);
its only failure was corpus-page copy drift caused by JSON serialization
changing 1.0 to 1. The Python generator output was restored and checked
against the generated corpus page. A final independent documentation review
also found a quiet invalid-result diagnostic retained in the Python return
value; that field now matches the generic input feedback, with a regression
test and renewed Astra xhigh approval. Final rerun evidence follows below. Local Quarto attempts with
both installed 1.9.35 and pinned 1.8.27 were blocked by Windows Deno cache/CMD
environment errors; no local render/browser success is claimed.

## Runs needed

Final exact-head Linux Python/render/browser workflow, fresh corpus comparison,
native compliance/project regressions and independent final CI-evidence review.
No PR is to be merged automatically.
