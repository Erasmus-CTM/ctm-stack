# Matrix-defined basis questions and teacher documentation

The `IsBasis` answer test now accepts the defining matrix rather than requiring
an author to write a reference basis. The `nullspace` and `columnspace` options
treat student columns as vectors; `rowspace` treats student rows as vectors.
The existing `columns` and `rows` options retain their reference-basis meaning.

The approach follows the dynamic matrix examples and `assess_basis` guidance in
[Erasmus-CTM/math-exercise](https://github.com/Erasmus-CTM/math-exercise/tree/5945f8f56f605e9d051d2c2636411755eabde1db),
particularly `dynamic-matrix-tests.qmd` and `docs/assess-basis.md`. Null-space
membership uses the original homogeneous equations; row/column-space membership
uses rank after adjoining the proposed vector. Completeness and independence
remain properties of the whole submitted family. Ordinary PRT branches award
credit; the reused helper's diagnostic fraction is not used as a score.

Author-only `nullspace_basis(A)`, `columnspace_basis(A)` and `rowspace_basis(A)`
compute the input model answer required by the XML format. Grading still uses
`A` itself. The two course null-space questions now use this arrangement.
The exact-rational domain and matrix-size limits are unchanged. Empty bases
still cannot be represented by the current matrix editor, and a zero-dimensional
target produces an explicit author error.

The public guide combines Python-only answer tests, differences from Moodle
STACK, and the custom checker API on one page linked from the navbar. Sol xhigh
revised teacher-facing site copy. Question sources are collected at the ends
of examples and the generated corpus page; detailed provenance and legal
notices remain in their source records.

## Validation

- Python tests outside `test_render.py`: 777 passed, 1 skipped, 149 subtests passed.
- Focused basis, custom checker, matrix and question tests: 178 passed, 9 subtests passed.
- The new cases cover alternative/mixed bases, incomplete and dependent families,
  zero/out-of-space vectors, wrong ambient dimensions, rectangular defining
  matrices, all three spaces, changing the original matrix, generated models,
  and invalid or unrepresentable targets.
- Corpus replay retained the same mathematical results: 23 passing questions,
  1 existing mismatch, 3 unsupported imports and 8 unsupported variants;
  162 replayed cases with 2 existing mismatches. Only run/source metadata changed.
- All 14 rendered-page tests passed.
- The runtime source bundle, generator round-trip and JavaScript syntax checks passed.
- Quarto 1.8.27 built the site locally. Its native Sass executable could not run
  in this environment; the local build used the JavaScript Sass compiler instead.
- Local Chromium exits during startup in this environment. Browser interaction
  and worker checks must therefore run in GitHub Actions before merge.
