# Checker arithmetic and invalid matrix diagnostics

Reviewed against main `e383541b4826ef2e09aacf3c23b260e1fdba24fa`.

## Problems and changes

Learner powers previously checked the exponent but not the growing base.
`((2^100)^100)^100` constructed a million-bit integer before the supplied
basis checker rejected its entries. The common evaluator now applies a
16,384-bit rational computation budget. Conservative estimates reject growing
powers before calling SymPy; rational atoms and held sums/products are checked
too. Held equation arithmetic and numeric coefficients of symbolic expressions
are included, because later simplification can otherwise bypass the early
check. This is a bounded-parser resource policy, not a sandbox for arbitrary
author Python. The supplied basis checker's separate 256-bit domain is unchanged.

An invalid checker on a later input could leave an earlier input's vector
assessment in the returned result. Invalid grading now removes every input's
assessment. The editor also displays vector colors only for a graded result
and an input not marked invalid. Tests cover the same or a different input,
quiet nodes, literal invalid feedback, and a two-input browser fixture.

## Independent review

GPT-6 Sol at xhigh reviewed the implementation before the PR. Its findings
added coverage for symbolic coefficients, held equation powers, and held
multiplication. The parent implemented those changes and reran the broad
non-rendering suite. The audit also checked the two-input browser fixture
and the engine/frontend state rules.

## Computed local checks

- 839 tests passed, 1 existing upstream-checkout skip, 163 subtests passed
  (`pytest -q tests --ignore=tests/test_render.py`).
- All 35 original corpus records replayed with unchanged outcomes: 23 passing,
  1 authored-test mismatch and 11 unsupported questions; 162 cases replayed,
  2 existing failed checks. Only baseline provenance metadata changed.
- The new browser fixture imports, preflights its model, renders through the
  CLI and grades its positive and invalid cases correctly in CPython.
- Runtime bundle freshness, JavaScript syntax and whitespace checks passed.

## Runs needed

Quarto is unavailable locally. Full Quarto/render, real Worker/Pyodide browser
interaction, native STACK comparison and compatibility jobs must pass on the
PR head in GitHub Actions. No local browser result is claimed here.
