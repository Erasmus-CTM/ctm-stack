# Filename-selected checkers and the SPD authoring example

Quarto selects custom checker source with `python-checkers: questions/file.py`.
The build reads that file and includes its source for local and browser grading.
The loader no longer computes or verifies a source digest, and temporary module
names no longer depend on one. Authors provide no manifest or digest setting.
Existing typed arguments, result checks, temporary namespaces and PRT scoring
remain unchanged.

The teacher guide now distinguishes the three built-in `MatrixProperty`
conditions from a custom property. Built-in nodes receive the submitted matrix
and the expected property value, such as determinant 1. A custom function
receives the submitted answer and whichever teacher value its PRT selects.

The complete SPD example is `questions/spd-checker.py`, selected by filename for
`questions/symmetric-positive-definite.xml`. It checks rational matrices using
Sylvester's criterion after checking shape and symmetry. The expected property
value is `true`; the identity input model fixes the editor's dimensions and is
only one accepted answer. The guide includes the full checker, an XML node,
full XML download, live question, Quarto block and CLI command. Sol xhigh revised
the walkthrough and related teacher guidance.

Validation:

- 791 Python tests passed, 1 skipped, 149 subtests passed (excluding render tests).
- All 14 rendered-page tests passed. The guide and examples both contain the
  selected checker file in their SPD payload, with no digest field.
- The documented CLI command passed all seven authored SPD cases.
- Corpus replay retained its previous results; the runtime source bundle matches
  the current Python files.
- New tests challenge negative definite, singular semidefinite, nonsymmetric,
  indefinite, rectangular and higher-dimensional matrices, exact fractional
  answers and unsupported entries. They also verify that changing a checker
  file takes effect at the next build, while an already-built question retains
  the source selected for it.
- The browser test now exercises the SPD card and filename-selected source in
  the actual worker. Local Chromium cannot start in this environment, so that
  interaction check requires CI.
