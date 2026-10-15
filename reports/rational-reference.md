# Rational-form answer tests: native STACK reference

On 2026-10-15, the [`maxima-reference` CI job](https://github.com/Erasmus-CTM/stack-sympy/actions/runs/38772935336/job/116553163850) reported **49/49 matching cases** for repository commit [`582e91ed3c210f957fe3daf10997f12bd2d98830`](https://github.com/Erasmus-CTM/stack-sympy/commit/582e91ed3c210f957fe3daf10997f12bd2d98830). It executed official STACK answer-test functions from upstream commit `10d323311b7f39fb7b092dd10ce75f7d8632f525` with Maxima 5.46.0, and compared them with this adapter using SymPy 1.13.3. The [CI artifact](https://github.com/Erasmus-CTM/stack-sympy/actions/runs/38772935336/artifacts/11991893506) contains the full `maxima-reference.json` result; this report records the verified CI outcome, rather than reproducing that artifact locally.

| Native answer test | Compared cases |
|---|---:|
| `ATAlgEquiv` | 5 |
| `ATEqualComAss` | 13 |
| `ATFacForm` | 8 |
| `ATSingleFrac` | 10 |
| `ATLowestTerms` | 13 |
| **Total** | **49** |

The source-controlled [fixture](../tests/reference_cases.json) supplies the expressions and their provenance. The [runner](../scripts/compare_stack_maxima.py) loads upstream `stack/maxima/stacklocallinux.mac`, which loads `stackmaxima.mac`, then calls each native `AT*` function. It compares the native CAS test-applicability flag and correctness mark to the adapter's `cas_valid` (falling back to `valid`) and `correct`. The adapter's `valid` also describes student-input validation and is recorded separately as `adapter_input_valid`; a well-formed but wrong `EqualComAss` answer can have valid input while the native CAS test reports inapplicability. The CI [workflow](../.github/workflows/site.yml) pins the STACK checkout and makes site testing and publication depend on this comparison.

To rerun, install Maxima and this repository's pinned Python requirements, check out official `maths/moodle-qtype_stack` at the SHA above, then run:

```sh
python scripts/compare_stack_maxima.py --stack-source /path/to/moodle-qtype_stack
```

The runner writes `test-results/maxima-reference.json` and exits nonzero for disagreement, an incomplete native result, missing Maxima, or an incorrect upstream checkout. These 49 curated scalar cases establish agreement for those expressions and answer-test results. They do not establish complete Moodle STACK behavior, every Maxima expression or option, or parity of the adapter's seeded random variants with Maxima.

