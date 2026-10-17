# Python IsBasis and course examples audit

## Scope and source

Implementation starts at stack-sympy `6b45c4903692f5fdf6e234dad4415d08abe8f34f`. A pinned source archive was materialized because Git clone failed in this environment. `python-basis-inputs.json` records the commit and complete 191-file input list; local snapshot Git is used only for diffing. Remote commits use the real upstream parent.

Course source: aacchhee/ingmat3a_ntnu `b05dda5a9e8405d87e2b89668c63c81dc37b2a7a`, section 3.8. Three exact source blocks, their labels, revision, hashes, CC BY-SA attribution, converted XML hashes and behavioral changes are recorded in `questions/course-examples-provenance.json`. Two nullspace problems (B and C) use IsBasis; the ordinary B rank/pivot example uses AlgEquiv.

The reusable assess_basis function is extracted unchanged from math-exercise `5945f8f56f605e9d051d2c2636411755eabde1db`. The AGPL-3.0-or-later source, function and module hashes are in `vendor/basis-helper-provenance.json`. No upstream repository refactor is required.

## Contract

IsBasis is explicitly a Python-only registered answer test. It uses standard XML sans/tans/testoptions and ordinary true/false PRT branches; the helper diagnostic fraction never awards credit. A valid independent rational reference defines the target span. Nonzero membership, independence and full dimension determine correctness. The exact predicate uses vector count and helper membership/independence statuses, not a floating diagnostic score. Native test meanings, the official inventory and eligibility scope are unchanged.

The adapter supports rows or columns, positive matrix dimensions, at most 64 entries and 256-bit rational numerators/denominators. It rejects decimal syntax, symbolic/irrational/complex values and malformed references. XML cannot supply Python code, imports or arbitrary module names. IsBasis requires a direct matrix input. The input model answer must itself pass the test, preventing configurations that cannot fit any correct basis. Validation performs domain/shape checks without membership or correctness feedback.

Colors are diagnostic only and are cleared on edits, resizing, resets and variant changes. Quiet nodes suppress diagnostic text and colors. The source exercises' fractional grading becomes binary basis grading; the ordinary exercise uses two equally weighted all-or-nothing parts. Positive dimension limits exclude the empty-basis case. These changes are explained in plain language in `docs/python-answer-tests.qmd` and on examples.qmd.

## Independent review

Independent Sol xhigh design audit identified an unreachable-input configuration: the input model could differ from the IsBasis reference and have insufficient columns. Fixed by requiring the model to pass the basis predicate during instantiation; regression included. The audit also requested exact correctness independent of the helper float, which is implemented. That was the initial design review. The follow-up independent Astra xhigh
design and implementation reviews are now approved; see
[PythonChecker audit](python-checker-api.md) for corrections, API decisions and
current validation.

## Historical local results before the API follow-up

117 focused tests and 27 subtests passed (basis, matrices, matrix inputs, importer and engine). All three XML questions pass authored qtests. The broader non-render run computed 686 passing tests and 149 passing subtests, 1 skipped; eight existing reference-runner tests failed at Windows symlink privilege checks. The local Quarto/browser attempt was blocked by Windows command resolution and sandbox cache permissions, so no successful browser/render result is claimed locally. JavaScript syntax and runtime-source generation passed.

## Original runs needed (superseded by follow-up evidence)

Full Linux Python/render/browser workflow, CPython/Pyodide parity, native compliance and project regressions on the exact PR head; new Worker/Pyodide basis browser test; final independent review of changes and CI evidence. No PR is to be merged automatically.

The follow-up API audit records the exact-head validation and final review
status. The original branch CI already passed 722 tests and 149 subtests, native
compliance and project regressions, but stopped at corpus source-fingerprint
drift before browser tests. Its audit record previously had not been updated.
