# Elementary functions, held logic, and polynomial equations

Implemented against STACK `10d323311b7f39fb7b092dd10ce75f7d8632f525`, SymPy 1.13.3, and AI Feedback 0.8.0. The imported inventory remains the same 2,303 upstream rows.

The port now accepts reciprocal trigonometric and hyperbolic functions (including `cosec`/`cosech` aliases), typed propositions and logical nouns, and polynomial equation disjunctions. Elementary proofs add bounded exponential rewriting. Scalar comparisons first use deterministic rejection-only numerical probes: agreement cannot establish equality, and nonfinite, nonreal or unstable evaluations are skipped. The screen uses two precision levels, an operation/magnitude budget, and conservative separation margins; it is a heuristic optimization, not a numerical grading tolerance or a certified interval proof.

## Traced STACK behavior

- `stack/answertest/at_general_cas.class.php` nounifies both answers before invoking answer tests. `stack/cas/security-map.json` maps `and`, `or`, and `not` to `nounand`, `nounor`, and `nounnot`. The map does not supply equivalent noun mappings for `xor`, `xnor`, or `implies`.
- `stack/maxima/assessment.mac`, `logic_to_poly`, converts disjunctions of equations to products of residuals. `stack/maxima/stackmaxima.mac`, `ATAlgEquivfun` and `ATEquation`, retain repeated factors and reject cancellation of symbolic factors.
- A held disjunction preserves duplicate branches before conversion. Consequently `x=0 or x=0` matches `x^2=0`, not `x=0`. Pure propositional truth tables may collapse duplicate propositions independently.
- Boolean student constants may answer equation teacher values; the reverse is deliberately asymmetric in STACK. Input syntax validity and CAS applicability remain separate.
- `assessment.mac`, `numerical_not_alg_equiv`, screens at fixed substitutions before expensive algebra. Its real-valued numerical test can reject but never accept equivalence. The port uses stricter high-precision stability checks and larger relative scaling.
- `assessment.mac`, `algebraic_equivalence`, calls `rectform` when the difference contains `i`, then exponentializes. A bounded numeric `expand_complex` proof fixes upstream #46 and #49, and the CAS applicability discrepancy in #668. It does not force symbolic root denesting or logarithm branches.

## Reference preparation correction

Raw Maxima evaluates `a=0 or b=0` to `false` too early. Noun preparation preserves the expression and makes #252/#253 match STACK's intended `a*b=0` equivalence. #255 also matches; #254, #268, #269 and repeated-root controls remain false as authored. Both native reference harnesses now apply token-aware nounification, preserving whole identifiers and quoted strings.

The large native runner records `stack-logic-nouns-v1` in metadata and its scope hash. The report rejects observations lacking the current preparation marker, and compatibility also verifies the reviewed scope fingerprint. Old native observations cannot be presented as current results.

## Scope and regression coverage

Equation sides must be polynomials over rational complex coefficients, with numeric denominators, at most eight variables, degree at most 100, and a conservative 2,048-term expansion estimate. Denominators are checked before simplification, so `x/x=1` and `0/x=0` remain unsupported. Equation conjunctions, negations, mixed propositions/equations, inequalities, general systems, and inverse/logarithmic branch identities remain outside this milestone.

Regression coverage includes function aliases, poles, genuine inequalities between expressions, numerical probe collisions, singular probes, Boolean precedence/De Morgan, equation scaling, symbolic factors, root and duplicate-branch multiplicity, principal complex-root controls, frozen XML variants, rendered previews, browser validation and grading, and the native reference gate. Three new Moodle XML examples exercise functions, Boolean expressions, and zero-product equations.

The resolved Python exceptions are #46, #49, and #147. The resolved native applicability exception is #668. Newly executable #149 is an existing upstream `-3` sentinel: the exact cotangent/radical identity is true in Python and false in the pinned native implementation, so it has a specific native mathematical-failure entry. No new Python defect waivers are added.


## Additional scalar helper inventory

| Mechanism | Source and purpose | Port implication |
| --- | --- | --- |
| Held arithmetic | `noun_simp.mac`: `noun_arith_full`, `equals_commute_prepare`, `verb_arith`; noun forms of addition, multiplication, division, powers, signs and equality | Retain the raw AST separately from mathematical values. Activation belongs in a proof copy, not the form being graded. Existing `EqualComAss` deviations still need individual traces. |
| Decimal/scientific display | `910_inert_float_for_display.filter.php` wraps raw floats using `dispdp`/`displaysci`; `assessment.mac` also defines `displaydp`, `displaysf`, and `remove_numerical_inert` | Preserve written precision separately from numeric value. The port already retains raw decimal spelling for `NumDecPlaces`; it does not claim all native inert-wrapper behavior. |
| Held calculus/root calls | `security-map.json` maps `diff` to `noundiff`, `int`/`integrate` to `nounint`, `limit` to `nounlimit`, and `root` to quoted `root`; `algebraic_equivalence` deliberately activates nouns | Future student calculus support requires held calls. Existing author `diff` deliberately computes its result; that does not establish student noun-calculus compatibility. |
| Logarithm bases | `002_log_candy.filter.php` translates forms such as `log_10(x)` into `lg(x,10)`; `logbasesimp` evaluates via logarithm ratios | Add explicit bounded syntax and base/domain checks before admitting these forms. Do not force general logarithm identities. |
| Plus/minus | `502_replace_pm.filter.php` preserves `+-` as `#pm#`; `pm_replace` expands a single occurrence into a noun disjunction | A natural extension of equation disjunctions, but repeated occurrences have ambiguous correlated/independent sign semantics. Still rejected in this milestone. |
| Numeric subexpression cleanup | `radcan_num` simplifies constant subexpressions without expanding surrounding symbolic brackets; `num_ensure_rational` rationalizes float leaves while retaining the operator tree | Keep normalization local and separate decimal syntax from mathematical values. Blanket conversion can conflict with native floating arithmetic cases already recorded in policy. |
| Display equation wrappers | `remove_stackeq` strips the display wrapper before equivalence | Display-only wrappers should be unwrapped at a typed boundary, not interpreted as arbitrary student functions. |
| Case diagnostics | `exdowncase` is tried after equivalence fails to detect a wrong-case answer note | It supplies feedback; it does not turn differently cased scalar symbols into an accepted answer. |

These are distinct layers, not a universal list of substitutions. In particular, default answer-test preparation uses `nounify=2` (logic nouns); general nounification/activation has separate contexts. Unit wrappers and collection nouns also exist but are outside plain scalar scope.
