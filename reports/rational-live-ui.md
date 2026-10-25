# Live browser UI review — rational corpus release

2026-10-15 UTC · deployed code commit `582e91ed3c210f957fe3daf10997f12bd2d98830` (v0.1.9) · Chrome cloud browser · verified URL <https://erasmus-ctm.github.io/ctm-stack/corpus.html>. The live page loaded `ctm-stack-0.1.9/ctm-stack.js`.

The page displayed all 30 corpus rows and **16 interactive cards**. Its baseline summary reported 16 pass, 1 authored-test mismatch, and 13 unsupported (4 import, 9 instantiation), with 73 authored test cases and 114 recorded seed/case combinations across 17 instantiated exports; two combinations disagreed. These are page-reported baseline figures, distinct from the displayed-seed button results below. Desktop inspection showed MathJax-rendered exercise prompts (40 `mjx-container` elements) without horizontal document overflow.

I clicked **Run author tests** on each of the 16 interactive cards and inspected every visible verdict. All **34 authored cases on the cards' displayed seeds passed**:

| Card | Passes | Card | Passes |
| --- | ---: | --- | ---: |
| AlgMap-1.5 | 2/2 | AlgMap-1.6 | 2/2 |
| AlgMap-2.1 | 2/2 | AlgMap-2.5 | 2/2 |
| AlgMap-4.1 | 2/2 | AlgMap-4.13 | 4/4 |
| AlgMap-6.4 | 3/3 | AlgMap-6.7 | 2/2 |
| AlgMap-7.1 | 2/2 | AlgMap-8.5 | 4/4 |
| AlgMap-9.1 | 1/1 | AlgMap-9.6 | 1/1 |
| AlgMap-10.1 | 2/2 | AlgMap-11.1 | 1/1 |
| AlgMap-11.8 | 2/2 | AlgMap-13.1 | 2/2 |

| Live interaction | Observed result |
| --- | --- |
| New rational cards | The table/TOC reached [LowestTerms AlgMap-2.5](https://erasmus-ctm.github.io/ctm-stack/corpus.html#algmap-2-5) and [SingleFrac AlgMap-4.13](https://erasmus-ctm.github.io/ctm-stack/corpus.html#algmap-4-13); both URLs were returned by the browser after link clicks. The first card displayed a legible stacked `−6/60`; the second showed `2x+2+3/(x+1)` with its denominator grouped in a stacked fraction. Controls and pass results remained readable. |
| Upstream limitation | A visible callout before AlgMap-2.5 states that the original response tree tests lowest-terms form without first checking equivalence: a reduced answer with the wrong value can earn full credit. It explicitly says the native XML and authored tests are unchanged. |
| New cards' source panels | On both 2.5 and 4.13, `Show source` and `Show STACK source` started closed, opened independently to show the `.stack-question` directive with file/seed and the raw `<?xml ...?><quiz><question type="stack">` export respectively, then closed independently. |
| LowestTerms validation | `Check answer` was initially disabled. Entering `-1/10` for `−6/60` and pressing Validate rendered the interpreted stacked fraction and enabled Check. Check showed “Correct.” Editing to `1/10` cleared grade and preview and disabled Check again. |
| Mismatch and unsupported status | AlgMap-8.10 remained noninteractive with 2/12 seed/case disagreements, specifically seed `1856951054`, case 1, `ans = (7*(t + y))`, expected PRT score 1.0/note `1-0-T` versus produced 0.0/note `1-0-F | 1-1-F`. AlgMap-14.1 remained noninteractive with an instantiation diagnostic at seed `1720352247`: `Function gcd is not allowed; use gcd*(…) for multiplication.` Neither had an answer button. |
| Home regression | At the [home demo](https://erasmus-ctm.github.io/ctm-stack/), variant 1 `(x+5)(x+3)`, `x^2+8x+15` parsed with a whole-polynomial preview, then Check returned “Correct: the expression is expanded and collected.” and “Correct.” Feedback showed Hint 1, Copy prompt mode, a `Copy prompt` control, and the prior explanatory context. Editing to `x^2+8x+14` cleared the grade/hint and disabled Check. Switching to variant 2 changed the factors to `(x+3)(x+2)`, cleared the answer, and kept Check disabled. No API key or AI service was used. |

The [earlier corpus UI report](corpus-live-ui.md) covers broader links/downloads and More examples interactions. This pass did not replay all 114 recorded seed/case combinations in the browser, nor assert Maxima RNG seed parity. I did not retry direct baseline JSON navigation after the earlier cloud-browser `ERR_BLOCKED_BY_CLIENT` policy failure. Unrelated `oaistatsig.com` telemetry failures in the browser tooling did not block the deployed site's controls. No product source was edited during this review.
