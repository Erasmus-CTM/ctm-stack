# Live checks of rational-form exercises

Tested 2026-10-15 UTC in a cloud Chromium browser against deployed v0.1.9 code commit `582e91ed3c210f957fe3daf10997f12bd2d98830`. The browser tab's verified URL was `https://erasmus-ctm.github.io/ctm-stack/corpus.html`; its script tag referenced `site_libs/quarto-contrib/ctm-stack-0.1.9/ctm-stack.js`. The page showed 16 interactive cards. I directly exercised the two newly supported answer tests, AlgMap-2.5 `LowestTerms` and AlgMap-4.13 `SingleFrac`, on their first displayed variants. The former displayed `-6/60` (correct reduced value `-1/10`); the latter displayed `2*x+2+3/(x+1)` (correct combined value `(2*x^2+4*x+5)/(x+1)`).

For every valid answer below, Check was disabled after input, Validate displayed an “Interpreted as …” mathematical preview and enabled Check, and Check gave the recorded result. `retry` means the visible “Not quite. Try again.” state.

| Exercise | Entered answer | Observed result | Interpretation |
| --- | --- | --- | --- |
| 2.5 | `-1/10` | **Correct.** | Correct reduced value. |
| 2.5 | `1/(-10)` | **Correct.** | Equivalent sign placement. |
| 2.5 | `-6/60` | **retry**; “Your answer is equivalent to the correct answer, but is not in the correct form!” | Original unreduced value. |
| 2.5 | `-2/20` | **retry**; same equivalent-but-wrong-form feedback. | Another equivalent unreduced value. |
| 2.5 | `-2/22` | **retry**. | Wrong value and unreduced form. |
| 2.5 | `1` | **Correct.** | Wrong value, but reduced form. |
| 2.5 | `-1/11` | **Correct.** | Wrong value, but reduced form. |
| 2.5 | `2/3` | **Correct.** | Wrong value, but reduced form. |
| 4.13 | `(2*x^2+4*x+5)/(x+1)` | **Correct.** | Correct single fraction. |
| 4.13 | `((2*x+2)*(x+1)+3)/(x+1)` | **Correct.** | Equivalent single fraction with unexpanded numerator. |
| 4.13 | `-(-(2*x^2+4*x+5)/(x+1))` | **Correct.** | Equivalent double-negated fraction. |
| 4.13 | `2*x+2+3/(x+1)` | **retry**. | Equivalent but still an uncombined sum. |
| 4.13 | `(2*x^2+4*x+5)*(1/(x+1))` | **retry**. | Equivalent product with a reciprocal, not a single fraction; native comparison fixture confirms this form rejection. |
| 4.13 | `(2*x^2+4*x+6)/(x+1)` | **retry**. | Single fraction with wrong value. |

Validation and state transitions were checked separately:

| Exercise | Action | Observed outcome |
| --- | --- | --- |
| 2.5 | Empty input, Validate | **invalid**; “Enter an answer”; Check disabled. |
| 2.5 | `2*x+(`, Validate | **invalid**; “Expected an expression”; Check disabled. |
| 4.13 | Empty input, Validate | **invalid**; “Enter an answer”; Check disabled. |
| 4.13 | `2*x+(`, Validate | **invalid**; “Expected an expression”; Check disabled. |
| 2.5 | Grade `-1/10` Correct, edit to `-6/60` | Previous preview and result text cleared; Check disabled until revalidation. |
| 4.13 | Grade `(2*x^2+4*x+5)/(x+1)` Correct, edit to `2*x+2+3/(x+1)` | Previous preview and result text cleared; Check disabled until revalidation. |

There were **18 distinct entered-answer scenarios** (14 parsed and checked, four invalid on validation), plus two edit-invalidation transitions. The numerical false positives on 2.5 follow the original STACK response tree, which checks `LowestTerms` form before equivalence. The live page explicitly warns: “A reduced answer with the wrong value can receive full credit.” The original XML and authored tests are unchanged. This is an authored grading limitation, not a newly introduced adapter discrepancy. The other 14 interactive cards were outside this focused release check; prior live reports cover the earlier additions.
