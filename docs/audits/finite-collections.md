# Flat finite scalar collections audit

Independent reviewer: GPT-6 Sol, xhigh, read-only review of the development
branch. Base: merged PR #8 (`b8b01e01fe2f423ca86b7decd69834a9efa0d9dd`).

## Scope

Existing algebraic input, flat lists and sets of up to 32 existing scalar
expressions, `AlgEquiv` and `Sets`; no nested/logical members, new input widget,
student indexing, set operators, `SameType` or collection `EqualComAss` yet.

The change includes parsing, held set repetitions, frozen variants, written
previews, CASText, typed PRT feedback variables, validation flags, XML qtests,
portable fixtures, bundle regeneration and native scope fingerprints.

## Findings and resolutions

- Scalar binary64 comparisons were initially lost inside lists. Preserve direct
  literal element ASTs, with native controls for 452 / 4.52*10^2, subtraction,
  and 1/3 / a written decimal. Frozen collection variables containing decimal
  literals or transitive decimal aliases now fail closed with a precise error;
  authors can use exact fractions. Dependency traversal uses a visited set.
- Scalar PRT placeholders prevented author indexing of a list input. Use typed
  teacher placeholders consistently for feedback variables and node preflight.
- Lowest-term validation dereferenced scalar properties on collection operands.
  Reject those operands as invalid arithmetic before examining fractions.
- A proposed product-to-sum rewrite was broader than observed native set
  preparation and had expansion risks. Remove it entirely. Lists retain scalar
  algebraic equivalence; sets retain structural members. Native positive list
  and negative set trigonometric controls pin the difference.
- Limit rectangular conversion to a rational coefficient times one exact
  exp(i*pi*q), |numerator(q)| <= 100 and denominator(q) <= 24, for AlgEquiv only.
- Regenerate the actual Pyodide source bundle after the final runtime edits.

## Explicit semantic observations

Pinned native Maxima 5.46 returns false for legacy set rows 201, 203 and 212.
Rows 201 and 203 carry authored desired score -3; exact canonical radicals and
rational-angle rectangular constants give the desired acceptance, recorded as
known native mathematical failures on the separate compatibility axis.
Row 212 expects false but SymPy canonicalizes the positive radical constants
before comparison. It remains an exact case-pinned known port difference, not a
pass. The public semantics page gives the counterexample, source documentation
and a concrete question for the STACK author. No expression-specific grader
exception or imported fixture modification is used.

## Validation

Focused Python/engine/corpus tests and the full non-rendering suite pass locally.
The native corpus and project regressions use the exact pinned STACK checkout;
CI additionally requires Quarto rendering, browser Worker/Pyodide execution,
portable parity and independent native compatibility checks. Local Quarto cannot
run its Sass runtime in this container, so local rendering is not claimed.
The complex-number corpus question now replays successfully with its list answer;
the corpus baseline and gallery are regenerated from the unchanged XML imports.
