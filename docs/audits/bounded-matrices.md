# Bounded matrix value contract

Design decision cycle 1 of the authorized 3 was reviewed with Astra xhigh.
Two decision cycles remain. This decision concerns matrices only; the pending
set matching and trigonometric set normalization questions are unchanged.

## Evidence and chosen policy

The official reference is STACK revision
`10d323311b7f39fb7b092dd10ce75f7d8632f525`. Its
[ATMatrix implementation](https://github.com/maths/moodle-qtype_stack/blob/10d323311b7f39fb7b092dd10ce75f7d8632f525/stack/maxima/stackmaxima.mac#L1638-L1666)
first checks row count, then column count, and compares ordered rows/entries
through algebraic equivalence. A size mismatch is an applicable incorrect
answer. The port returns `ATMatrix_wrongsz_rows`,
`ATMatrix_wrongsz_columns`, or `ATMatrix_wrongentries` accordingly.
It supplies whole-matrix feedback without allocating cell scores.

[EqualComAss](https://github.com/maths/moodle-qtype_stack/blob/10d323311b7f39fb7b092dd10ce75f7d8632f525/stack/maxima/noun_simp.mac#L213-L240)
requires compatible types and algebraic equality before comparing written form.
Unequal values or shapes produce `cas_valid=false`; algebraically equal entries
in different written forms produce `cas_valid=true, correct=false`.
`matrix([x+x])` therefore differs from `matrix([2*x])` under EqualComAss.
`SameType` compares applicability: two supported matrices have the same type
even when their dimensions differ; a matrix and a nested list do not.

The supported matrix answer tests are AlgEquiv, SameType and EqualComAss.
Other tests fail explicitly outside the port contract. This is a port boundary,
not a claim about native STACK: for example native LowestTerms recursively
examines matrix entries (the imported fixture includes such a row).

## Bounds, values and provenance

Matrices use `matrix([a,b],[c,d])` syntax and immutable `MatrixValue` containers.
They retain a distinct matrix kind and ordered rectangular shape; they are not
ordinary nested lists and do not expose SymPy matrix arithmetic. Each axis is
1–16 and the total number of entries is at most 64, in addition to existing
expression character, token, depth and scalar-complexity limits. Entries must be
finite supported scalar expressions. Ragged rows, missing cells, empty rows,
zero dimensions, nested matrices, non-scalar entries, matrix arithmetic and
matrix operations are rejected. Zero dimensions are deliberately rejected,
instead of silently adopting the editor's historical 0-by-0 convention.

The editor preserves raw strings; the consumer composes matrix constructor
syntax and uses the same bounded parser as scalar/list answers. Preview and
EqualComAss retain each cell's AST (`x+x`, `0.1`, `1/2`) rather than rebuilding
it from a simplified value. AlgEquiv compares each cell with existing scalar
equivalence and constant binary64 provenance. In particular `100.4-80.0` and
`20.4` remain unequal within matrix cells, just as for scalar/list answers.

Exact author matrix variables freeze and restore as explicit matrix source
strings. Decimal matrix author variables, transitive decimal aliases in matrix
expressions, symbolic/function decimal cells, and transformed decimal matrix
expressions fail closed under the existing collection provenance policy.
Literal constant arithmetic in direct matrix input and qtests is retained.
Sensitive learner aliases and learner-dependent matrix reconstruction in PRTs
are rejected when they would discard original cell precision/form.
Unsimplified matrix aliases receive the same transitive written-form checks as
lists. No new scalar/list/set equivalence or decimal policy was introduced.

## Input and feedback contract

Matrix inputs default to the teacher's fixed positive dimensions. Explicit
per-axis configuration can permit learner-selected dimensions within positive
bounds; fixed axes must retain their initial dimension. Input validation checks
these rules before PRT execution. Wrong shapes in a resizable editor remain
valid input and receive an incorrect whole-matrix algebraic result. Validation
checks syntax/type/bounds without revealing correctness. PRT scoring remains
author-defined; visual assessment states do not award partial credit.

## Coverage and verification record

The imported 2,303-row fixture is unchanged. At main `a007cdf`, preflight has
452 supported rows, 7 controlled-invalid cases and 1,844 unsupported rows.
The matrix implementation supports 465 rows (+13), retains 7 controlled-invalid
cases and leaves 1,831 unsupported rows. All 13 newly supported official matrix
rows matched their desired outcomes in direct CPython execution. Of 25 imported
rows mentioning matrices, 12 remain excluded: indexed expressions, non-scalar
entries/relations, unsupported SubstEquiv/NumSigFigs, and the explicit matrix
LowestTerms boundary. No row was removed or relabeled as a passing boundary.

Project regressions separately add 13 native-scope matrix comparisons and five
explicit boundaries. Unit tests exercise dimensions, distinct type, scalar
entries, written form, decimal precision, exact frozen variants, CASText,
validation, PRT scoring and qtest replay. Full native Maxima comparison and
browser Pyodide parity run through the existing pinned GitHub Actions harness;
the final PR's CI observations are the authoritative full-run evidence.

## Independent Sol xhigh review

The independent review required author qtest shapes to be checked during
instantiation, rather than allowing an impossible fixed/out-of-bounds qtest to
survive until grading. The fix shares `_matrix_input_shape` between learner
validation and qtest preflight, with regressions for five rows against a
four-row maximum and a 1-by-1 qtest against a fixed 2-by-2 input. Diagnostics
identify the qtest and input. The fixed-input markup test now removes the
resizable example's deliberate wrong-shape qtests before changing that example
to fixed dimensions.

The UI review also identified an authoring feasibility gap: explicit fixed
dimensions or resizable bounds could exclude the teacher shape when no qtests
were supplied. Instantiation now applies the same shape helper to the teacher
itself, requiring a fixed axis to match its initial size and a resizable axis
to include the teacher size. Four no-qtest controls cover both axes and upper
and lower exclusions, preventing an input whose correct answer is unreachable.

Self-review also added explicit author-operation and nested-matrix rejection
(`ev`, `diff`, general calls, and list-of-matrices), plus held CASText and
transitive unsimplified-alias controls. Before the final review fixes, the
targeted Python suite passed 403 tests and 103 subtests. Final focused rerun
results and the independent review verdict are recorded with the PR; no native
or browser run is represented by these local unit counts.
