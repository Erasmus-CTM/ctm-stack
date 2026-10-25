# Live corpus exercise checks

Tested 2026-10-15 UTC against deployed commit `5c16adbc250e39f909639152c9d51ca3d701893c` in a cloud Chromium browser. The browser tab's verified URL was `https://erasmus-ctm.github.io/ctm-stack/corpus.html`. I interacted with each rendered input and its **Validate answers** and **Check answer** controls; the outcomes below are observed UI results, not inferred from unit tests. All six initial Check buttons were disabled. For a valid input, Validate displayed an “Interpreted as …” preview, enabled Check, and displayed “Inputs parsed. Review them, then check your answer.” The table uses “retry” for the UI's “Not quite” result state.

| Exercise | Entered answer(s) | Observed validation and grade |
| --- | --- | --- |
| AlgMap-1-6 | `16` | Parsed; **Correct.** |
| AlgMap-1-6 | `17` | Parsed; **retry**. |
| AlgMap-1-6 | empty | “Enter an answer”; Check disabled. |
| AlgMap-1-6 | `2**` | “Expected an expression”; Check disabled. |
| AlgMap-7-1 | `x^2-64` | Parsed; **Correct.** |
| AlgMap-7-1 | `x^2-63` | Parsed; **retry**. |
| AlgMap-7-1 | `(x-8)(x+8)` | “Missing * for multiplication (this input requires an explicit *)”; Check disabled. |
| AlgMap-7-1 | `(x-8)*(x+8)` | Parsed; **retry**. Its authored answer test requires the expanded form, so this is expected form-sensitive grading despite algebraic equivalence. |
| AlgMap-7-1 | empty | “Enter an answer”; Check disabled. |
| AlgMap-7-1 | `x^2+` | “Expected an expression”; Check disabled. |
| AlgMap-9-1 | `-1/2` | Parsed; **Correct.** |
| AlgMap-9-1 | `0` | Parsed; **retry**. |
| AlgMap-9-1 | `1/0` | “Division by zero”; Check disabled. |
| AlgMap-9-1 | empty | “Enter an answer”; Check disabled. |
| AlgMap-9-6 | `35/4` | Parsed; **Correct.** |
| AlgMap-9-6 | `9` | Parsed; **retry**. |
| AlgMap-9-6 | `8.75` | “Decimal numbers are forbidden”; Check disabled. |
| AlgMap-9-6 | `70/8` | “Write fractions in lowest terms”; Check disabled. |
| AlgMap-9-6 | `1/0` | “Division by zero”; Check disabled. |
| AlgMap-9-6 | empty | “Enter an answer”; Check disabled. |
| AlgMap-11-1 | `ans1=c/b`, `ans2=c/a` | Both parsed; **Correct.** |
| AlgMap-11-1 | `ans1=c/b`, `ans2=c/b` | Both parsed; **Partially correct (50%).** |
| AlgMap-11-1 | `ans1=c/b`, `ans2=` empty | First parsed, second “Enter an answer”; Check disabled. |
| AlgMap-11-1 | both empty | Both “Enter an answer”; Check disabled. |
| AlgMap-11-1 | `ans1=c/b`, `ans2=c/a+` | First parsed, second “Expected an expression”; Check disabled. |
| AlgMap-11-8 | `a^2/b^2` | Parsed; **Correct.** |
| AlgMap-11-8 | `(a/b)^2` | Parsed; **Correct.** Equivalent alternate form accepted. |
| AlgMap-11-8 | `a/b^2` | Parsed; **retry**. |
| AlgMap-11-8 | `a^2+` | “Expected an expression”; Check disabled. |
| AlgMap-11-8 | empty | “Enter an answer”; Check disabled. |

I additionally edited AlgMap-1-6's graded `16` to `17`: the prior grade and validation preview cleared and Check became disabled. After Validate and Check, the new answer graded retry. On AlgMap-11-1 I moved from both correct to one wrong (50%), then an empty second answer (validation blocked Check), then restored both correct (Correct). This exercised revalidation and multi-input state transitions in the live page.

No adapter defect surfaced in these 30 entered-answer scenarios. The rejected unexpanded AlgMap-7-1 answer follows its upstream form-sensitive answer test; the source question requests expansion. The decimal and lowest-terms restrictions on AlgMap-9-6 likewise match the authored question options.
