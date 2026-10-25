# Live browser UI review — FacForm corpus release

2026-10-15 UTC · deployed commit `6590df2295e3b0b7c5c535138540e597b0e2b3d8` (v0.1.6) · Chrome cloud browser · verified URL <https://erasmus-ctm.github.io/ctm-stack/corpus.html> (home <https://erasmus-ctm.github.io/ctm-stack/>).

The deployed page displayed all 30 corpus rows and **14 interactive cards**, with **14 passed, 0 authored-test mismatches, and 16 unsupported** (8 import, 8 instantiation). The page stated 84 native author-test combinations across recorded seeds and no mismatch. At a 1363-pixel desktop viewport, the 1348-pixel document fit without horizontal overflow. MathJax rendered the exercise expressions (37 `mjx-container` elements observed). This is a live UI review; the 84-case baseline and CI results are separate evidence.

I clicked **Run author tests** on every one of the 14 cards, then inspected each visible verdict and displayed-seed result. All **28 displayed-seed authored cases passed**, with the following exact card counts:

| Card | Passes on displayed seed | Card | Passes on displayed seed |
| --- | ---: | --- | ---: |
| AlgMap-1.5 | 2/2 | AlgMap-1.6 | 2/2 |
| AlgMap-2.1 | 2/2 | AlgMap-4.1 | 2/2 |
| AlgMap-6.4 | 3/3 | AlgMap-6.7 | 2/2 |
| AlgMap-7.1 | 2/2 | AlgMap-8.5 | 4/4 |
| AlgMap-9.1 | 1/1 | AlgMap-9.6 | 1/1 |
| AlgMap-10.1 | 2/2 | AlgMap-11.1 | 1/1 |
| AlgMap-11.8 | 2/2 | AlgMap-13.1 | 2/2 |

| Live interaction | Observed result |
| --- | --- |
| Corpus card navigation and visual render | TOC/table links reached exact fragment URLs including `#algmap-1-5`, `#algmap-2-1`, `#algmap-6-4`, `#algmap-6-7`, `#algmap-8-5`, and `#algmap-13-1`. `AlgMap-1.5` displayed `c⁶ · c⁷` as separate unsimplified factors; `6.4` retained `cᵃ · cᵇ`; `6.7` rendered the grouped `(5·x)³`; `8.5` showed a legible stacked fraction `(−a+b)/(a−b)`; `2.1` stated “Factorise 2520 into primes” with powers-of-primes guidance; `13.1` showed `−4t²+33t−8`. Card buttons and input stayed readable. |
| `AlgMap-8.5` and `AlgMap-13.1` source panels | Both `Show source` and `Show STACK source` initially closed. Each opened independently. The former showed the `.stack-question` directive and native XML path/seed; the latter showed the original `<?xml ...?><quiz><question type="stack">` content. Both closed on a second click. |
| `AlgMap-10.1` form answer | The primary agent independently entered `18*(1-x)` for `18−18x`, clicked Validate, saw parsed preview, then clicked Check and saw “Correct.” The companion [live mathematical grading report](facform-live-math.md) covers additional form-sensitive cases, including `13.1`. |
| Home polynomial regression | On variant 1, `(x+5)(x+3)`, entered `x^2+8x+15`; Validate showed an interpreted polynomial and enabled Check. Check displayed “Correct: the expression is expanded and collected.” and “Correct.” |
| Home Feedback and state reset | Feedback in default Copy prompt mode displayed Hint 1 and “Paste this prompt into your chosen AI chat,” with the generated prompt visible. No API credentials or calls were used. Editing the response to `x^2+8*x+14` removed the previous grade and hint and disabled Check. Selecting variant 2 changed the factors to `(x+3)(x+2)`, cleared the answer, and left Check disabled. |

The earlier [corpus UI report](corpus-live-ui.md) covers broader table/link and More examples behavior from the preceding release. Direct baseline JSON navigation had produced a cloud-browser `ERR_BLOCKED_BY_CLIENT` policy rejection in that review, so I did not retry it here or claim a browser download. The unrelated `oaistatsig.com` telemetry errors in this cloud browser did not interrupt target-site interactions. No product source was changed during this review.
