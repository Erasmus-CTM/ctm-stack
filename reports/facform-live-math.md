# Live exercise checks after FacForm support

Tested 2026-10-15 UTC in a cloud Chromium browser against deployed commit `6590df2295e3b0b7c5c535138540e597b0e2b3d8` (v0.1.6). The browser tab's verified URL was `https://erasmus-ctm.github.io/stack-sympy/corpus.html`. The page showed **14 interactive cards** and a corpus baseline of **14 passed, 0 mismatches, 16 blocked**. This report records direct interactions with eight newly enabled or corrected cards: six formerly mismatching native examples and two new FacForm cards (10.1 and 13.1). For every syntactically valid row, the card's Check button was disabled after typing, Validate answers displayed an “Interpreted as …” preview and enabled Check, and Check answer produced the result below. “retry” is the UI's “Not quite. Try again.” state.

| Exercise and displayed task | Entered answer | Observed Check result |
| --- | --- | --- |
| AlgMap-1.5, `c^6 · c^7` | `c^13` | **Correct.** |
| AlgMap-1.5 | `c^6*c^7` | **retry**; equivalent but not fully simplified. |
| AlgMap-2.1, factor `2520` | `2^3*3^2*5*7` | **Correct.** |
| AlgMap-2.1 | `2520` | **retry**; equivalent but not fully factored. |
| AlgMap-2.1 | `2*2*2*3*3*5*7` | **retry**; equivalent prime product but not fully factored into powers. |
| AlgMap-4.1, `(8/15)·8` | `64/15` | **Correct.** |
| AlgMap-4.1 | `(8/15)*8` | **retry**; equivalent but not fully simplified. |
| AlgMap-6.4, `c^a · c^b` | `c^(a+b)` | **Correct.** |
| AlgMap-6.4 | `c^a*c^b` | **retry**; equivalent but not fully simplified. |
| AlgMap-6.7, `(5·x)^3` | `125*x^3` | **Correct.** |
| AlgMap-6.7 | `(5*x)^3` | **retry**; unexpanded. |
| AlgMap-6.7 | `5*x^3` | **retry**; feedback reminds the learner to raise the constant too. |
| AlgMap-8.5, `(b-a)/(a-b)` | `-1` | **Correct.** |
| AlgMap-8.5 | `(b-a)/(a-b)` | **retry**; equivalent but not fully simplified. |
| AlgMap-8.5 | `1` | **retry**; feedback identifies the missing minus sign. |
| AlgMap-10.1, factor `18-18*x` | `18*(1-x)` | **Correct.** |
| AlgMap-10.1 | `-18*(x-1)` | **Correct.** Equivalent sign placement accepted. |
| AlgMap-10.1 | `18-18*x` | **retry**; expanded answer. |
| AlgMap-10.1 | `6*(3-3*x)` | **retry**; only part of the integer content extracted. |
| AlgMap-13.1, factor `-4*t^2+33*t-8` | `(8-t)*(4*t-1)` | **Correct.** |
| AlgMap-13.1 | `(4*t-1)*(8-t)` | **Correct.** Factor order accepted. |
| AlgMap-13.1 | `-(t-8)*(4*t-1)` | **Correct.** Equivalent sign placement accepted. |
| AlgMap-13.1 | `4*(8-t)*(t-1/4)` | **Correct.** Scaled rational factorization accepted. |
| AlgMap-13.1 | `-4*t^2+33*t-8` | **retry**; expanded answer. |
| AlgMap-13.1 | `(t-8)*(4*t-1)` | **retry**; wrong overall sign. |

Additional input-state and domain checks:

| Exercise | Entered answer / action | Observed outcome |
| --- | --- | --- |
| AlgMap-10.1 | Empty answer, then Validate | **invalid**; “Enter an answer”; Check disabled. |
| AlgMap-13.1 | `(8-t)*(`, then Validate | **invalid**; “Expected an expression”; Check disabled. |
| AlgMap-13.1 | `t/(t-1)`, then Validate and Check | Parsed preview, then **error**, specifically “FacForm supports only numeric denominators.” This is outside the FacForm rational-polynomial scope, not an incorrect grade. The UI displays a full Python traceback following “Could not check this answer”; that diagnostic is unnecessarily technical for learners. |
| AlgMap-10.1 | Grade `18*(1-x)` Correct, then edit input to `18-18*x` | Old result text and validation preview cleared; Check disabled until a fresh validation. The result element retained a `data-state="correct"` attribute while its text was empty. |

There were **28 distinct entered-answer scenarios** (25 graded valid form or value cases, two invalid validation cases, one unsupported-domain error) plus the edit-invalidation transition. No incorrect grading surfaced. The exposed traceback on an out-of-domain answer is a user-facing presentation issue; the underlying error classification correctly differs from retry. These checks do not assert behavior for the other six interactive cards, which were covered separately in `reports/corpus-live-math.md` at an earlier deployment.

## v0.1.7 targeted regression (2026-10-15 UTC)

After deployment of commit `155507b290cf0755f3fcb83b6fcf96b5fb81c835`, I repeated the AlgMap-13.1 issue in a cloud Chromium tab at the verified URL `https://erasmus-ctm.github.io/stack-sympy/corpus.html?release=155507b290cf0755f3fcb83b6fcf96b5fb81c835`. Its script tag referenced `site_libs/quarto-contrib/stack-sympy-0.1.7/stack-sympy.js`. The initial canonical tab had briefly served v0.1.6 HTML; a normal reload then showed the v0.1.7 script at the separately verified canonical URL `https://erasmus-ctm.github.io/stack-sympy/corpus.html`. I repeated the same transition there as well.

| Tested URL | Input and action | Observed outcome |
| --- | --- | --- |
| Query URL above, v0.1.7 script | `t/(t-1)`; Validate, then Check | Parsed preview and enabled Check. Check displayed `Could not check this answer: AlgMap-13.1: prt[prt1]/node[0]: FacForm supports only numeric denominators`. No traceback. |
| Query URL above | Edit to `(8-t)*(4*t-1)`; Validate, then Check | The previous error and preview cleared on edit; Check disabled, then re-enabled on validation. Check displayed `Correct.` |
| Canonical URL above after reload, v0.1.7 script | `t/(t-1)`; Validate, then Check | Parsed preview and enabled Check. Check displayed the same concise numeric-denominator error, with no traceback. |
| Canonical URL above after reload | Edit to `(8-t)*(4*t-1)`; Validate, then Check | Previous result and preview cleared; Check disabled until validation. Check displayed `Correct.` |

The v0.1.6 traceback finding above is historical and resolved in this targeted v0.1.7 browser regression. The full 28-scenario matrix was not repeated on v0.1.7.
