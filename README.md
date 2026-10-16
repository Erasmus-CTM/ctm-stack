# STACK SymPy

Native Moodle STACK questions on interactive, static Quarto pages. Keep the exported XML and the authored question tests; this extension imports a documented subset, freezes seeded variants when Quarto builds the page, and checks student answers with SymPy in a browser worker. The [live example site](https://erasmus-ctm.github.io/stack-sympy/) starts with a form-sensitive algebra question and also shows algebraic equivalence and numerical grading.

This is for formative exercises and inspection of supported STACK material. It is not Moodle STACK, Maxima, or a substitute for a proctored assessment. Authoring features outside the subset fail visibly at build time. In `diagnostics: true` mode a diagnostic card appears instead, which is useful while adapting an export.

## Try the examples

The three new questions in [`questions/`](questions/) are ordinary Moodle `<quiz><question type="stack">…</question></quiz>` exports, with input settings, response trees, deployed seeds, and native `<qtest>` cases. [`questions/upstream/`](questions/upstream/) holds the original three unchanged STACK samples with provenance in [`sources.json`](questions/upstream/sources.json). The [30-question native corpus](questions/corpus/) is a cross-chapter compatibility target with a [per-file manifest](questions/corpus/manifest.json), unchanged exports, and authored qtests. See the [corpus page](corpus.qmd) for its compatibility status and original XML links.

| Question | What it demonstrates |
|---|---|
| [Expand a product](questions/polynomial-expansion.xml) | Seeded coefficients; `EqualComAss` checks expanded/collected form, then `AlgEquiv` awards half credit for an equivalent expression still in factored form. |
| [Equivalent rational expression](questions/rational-equivalence.xml) | `AlgEquiv` accepts both simplified and unsimplified forms on the stated domain; a second PRT node gives reciprocal-specific feedback. |
| [Rectangle and triangle measurements](questions/numerical-measurement.xml) | Three weighted PRTs: `NumAbsolute` within 0.25 cm, `NumRelative` within 2%, and `NumDecPlaces` requiring `17.50` rather than `17.5`. |
| [Imported STACK samples](questions/upstream/) | Unmodified `AlgMap-6.1`, BODMAS, and rounding exports for testing adapter behavior against real files. |

## Install in a Quarto project

Install the extension with `quarto add Erasmus-CTM/stack-sympy`, or copy this repository's `_extensions/stack-sympy` folder into your project. To use `#| feedback: true`, also install the independently maintained [AI Feedback extension](https://github.com/Erasmus-CTM/ai-feedback) once in the same project with `quarto add Erasmus-CTM/ai-feedback` (version 0.8.0 or newer; requires Quarto 1.8.27+). Questions without feedback do not require it. In a project installed via `quarto add`, also run `python -m pip install 'sympy==1.13.3'` in the Python environment Quarto uses; that project does not receive this repository's requirements file. Build-time rendering uses Python 3.11+ and Quarto 1.4+. CI validates AI Feedback 0.8.0 at `68abb6dc1d1e4770c44ad408b4972d689c9f42fc`. For a local checkout of this example site, install both extensions before rendering:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
quarto add Erasmus-CTM/ai-feedback
quarto render
python -m http.server --directory _site 8000
```

When the filter uses a different Python interpreter, set `STACK_SYMPY_PYTHON=/absolute/path/to/.venv/bin/python` for the render. A plain `file://` preview cannot reliably run browser workers; use an HTTP server. Browser grading downloads Pyodide and its packages on first use, so a learner needs network access. The site's authored XML files are retained as downloadable resources.

Add the filter to `_quarto.yml`:

```yaml
filters:
  - stack-sympy
```

In a `.qmd` file, use the exact XML question name:

````markdown
```{.stack-question}
#| file: questions/polynomial-expansion.xml
#| question: Expand a product (form-sensitive)
#| variants: 3
#| seed: 17
#| review: true
#| feedback: true
```
````

A learner enters answers, presses **Validate answers** to inspect how each expression was parsed, then presses **Check answer** to grade the validated response. Editing a field clears its validation and requires another Validate step. The preview preserves the written form, so `x+x` still appears as `x+x`; this is important when an answer test checks form. Invalid input receives a validation message and cannot be graded until corrected.

Each rendered question also has closed **Show source** and **Show STACK source** panels below it. They show the authored Quarto fenced block and the original XML file, respectively, for inspection or copying. Opening either panel does not affect the question or its grading.

`file` and `question` are required. `variants` is 1–20 (default 1); `seed` is a signed integer (default 1). `review: true` exposes the authored qtests for inspection. `diagnostics: true` displays build errors in the rendered page during authoring. Remove diagnostics for publishing, so unsupported content fails the build. A seed produces repeatable variants in this adapter, but is **not** expected to match Maxima's random sequence for the same seed.

## AI feedback and context

`feedback: true` enables optional AI hints for a card (default false). The shared `math-exercise` policy supplies the hint sequence and is the YAML integration namespace for STACK. `context: auto` is the default; `context: id1,id2` references tagged blocks; `context: none` omits context. `feedback-language` chooses the explanation language, defaulting to document `lang`. `feedback-policy` selects an existing named policy. Use `label` for a stable exercise key in policy YAML; otherwise the card ID is used.

Automatic context comes from visible prose in the preceding section. To share a specific concept, tag it and reference its ID instead:

````markdown
::: {#expansion-hint .ai-context}
Distributivity gives $a(b+c)=ab+ac$.
:::

```{.stack-question}
#| file: questions/polynomial-expansion.xml
#| question: Expand a product (form-sensitive)
#| feedback: true
#| context: expansion-hint
```
````

`context: none` turns context off for that card. `.ai-feedback-context` and legacy `.math-exercise-context` are aliases of `.ai-context`. The [live examples](https://erasmus-ctm.github.io/stack-sympy/examples.html) include all three modes. The shared resolver handles explicit aliases, LaTeX and context limits; STACK does not implement a second resolver.

AI Feedback 0.8 loads named definitions from `policy-files` and `page-policy-files`; loading a file alone activates nothing. Select `project-policy` or `page-policy` explicitly, either by name or with a `math-exercise` selector map. Policies support `extends`, `base-prompt`, and a replacement list of `step-prompt` entries. The old authored `defaults`, `integrations`, and `prompt` fields are rejected. Resolution follows shipped defaults, explicit project/page selections, exercise-ID overrides, the exercise's selected policy and its ancestry, then its current step. STACK delegates this resolution to the shared runtime. See the [working course policy](feedback/course.yml), [authoring example](docs/authoring.qmd#choose-a-teaching-policy), and [shared policy reference](https://github.com/Erasmus-CTM/ai-feedback/blob/main/docs/feedback-policies.md).

The default mathematics sequence has four steps: question, concept, procedure, and worked solution. Edits cancel stale replies and invalidate Check evidence while retaining progression. Check restarts hints when the effective `reset-on-run` is true; selecting another frozen variant always resets hints and evidence. Only a successful displayed reply or copy prompt advances a step. Explicit `jsxgraph:diagram-id` context references use the shared visual-context collector; diagrams are never attached implicitly.

The learner's current answer, visible question text and selected context form the feedback request. A preceding matching **Check answer** can supply minimal result status and a finite score as evidence. Original XML, source panels, teacher answers, qtests, grader configuration, feedback messages and answer notes are excluded. Feedback does not run or replace the deterministic grader. The shared settings panel defaults to copy-prompt mode and can use a learner-configured provider; provider keys are not embedded in the page. The shared extension owns the provider client, settings, policies and feedback UI. STACK SymPy supplies only its question/response adapter.

## Supported subset and grading behavior

| Feature | Current handling |
|---|---|
| Input types | Scalar `algebraic` and `numerical`; strict syntax, `<insertstars>0</insertstars>` (explicit `*`) or `<insertstars>1</insertstars>` (bounded adjacent implied multiplication), forbidden words/floats, lowest-term fractions, and validation flags. |
| Expressions | Arithmetic, powers, scalar symbols, and a constrained allowlist of Maxima-like variable assignments and functions. Seeded `rand(n)` works for the examples. No arbitrary Maxima evaluation. |
| Answer tests | `AlgEquiv`, `EqualComAss`, `FacForm`, `SingleFrac`, `LowestTerms`, `NumAbsolute`, `NumRelative`, `NumDecPlaces`. `FacForm` requires a single variable in `<testoptions>` and handles univariate polynomials with rational coefficients. Blank options mean a 0.05 tolerance for the two numeric tolerance tests; `NumDecPlaces` requires an explicit count from 1 to 50 decimal places. |
| PRTs | Acyclic graphs of answer-test nodes, branch scores with `=`, `+`, or `-`, feedback, answer notes, and weighted aggregation across response trees. |
| Author tests | Native `<qtest>` inputs with expected PRT score, penalty, and answer note. Test outcomes are available in review mode and the CLI. |
| CASText | Scalar `{@expression@}` or a displayed scalar equality `{@left=right@}`, plus `[[input:name]]`, `[[validation:name]]`, and `[[feedback:name]]` in sanitized HTML. |

`EqualComAss`, `FacForm`, `SingleFrac`, and `LowestTerms` require `sans` to be the direct input name so the student's written expression form survives validation. `EqualComAss` checks that form up to commutative/associative reordering: `cos(0)` and `1` have the same value but different written forms, as do `sqrt(3)` and `3^(1/2)`. It still accepts reordered terms such as `sqrt(x)+sin(x)` and `sin(x)+sqrt(x)`. `AlgEquiv` checks symbolic equivalence using SymPy transformations. `FacForm` checks equivalence **and** the student's written factorization, including whether its polynomial factors can be factored further over the rationals. It requires one polynomial variable in `<testoptions>` (including an author variable resolving to a symbol) and handles rational coefficients, nonnegative integer powers, and numeric denominators; it does not implement the full Maxima answer test. `SingleFrac` checks equivalence and a single written fraction, rejecting divisions nested through sums or products in its numerator or denominator; equivalent atomic answers are also accepted. Like the native helper, this form check does not inspect powers or function arguments for division. `LowestTerms` checks the student's written fractions without comparing the teacher value: it rejects reducible numeric integer fractions, a double negative, and supported irrational or complex denominators. It does not cancel symbolic polynomial factors. These two form checks cover scalar expressions in the parser's bounded syntax, not every Maxima expression or STACK option. With `questionsimplify=0` (`simp:false`), supported CASText expressions retain their authored arithmetic form, including grouping within existing TeX math. Numerical tolerance is based on the mathematical value, while `NumDecPlaces` also examines the raw written decimal and its trailing zeros. The XML `penalty` is compared in an authored qtest as an initial-attempt expectation. Authored answer notes use STACK-style ordered subsequence matching, including anchored beginning/end notes and `NULL`; an expected terminal note can pass when earlier nodes also ran. The demo itself has no Moodle attempt state or persistence. The adapter does not claim all STACK tests, expression forms, domains, validation behaviors, question-level options, or Maxima semantics. It raises a question-and-field-specific error when it knows an author feature cannot be preserved. Authors should run the qtests, inspect rendered variants, and compare consequential questions in Moodle.

The optional native reference check runs a source-controlled set of scalar answer-test cases through this adapter and the official STACK/Maxima answer-test functions from the pinned upstream checkout. It compares CAS test applicability and correctness; adapter input validation is recorded separately. Install Maxima and run `python scripts/compare_stack_maxima.py --stack-source /path/to/moodle-qtype_stack` against the exact commit specified by that script. CI runs this comparison before publishing the example site. Passing its selected cases does not imply that all STACK expressions, question settings, or random variants agree with Maxima.

The separate [native compliance report](https://erasmus-ctm.github.io/stack-sympy/compliance/) inventories all 2,303 static upstream answer-test rows from the pinned fixture and shows three independent checks: Python against authored desired results, Python against official STACK/Maxima, and Pyodide against CPython. It distinguishes unsupported cases, controlled errors, known native mathematical failures, reviewed Python defects, and unexplained differences. Native agreement compares CAS applicability and correctness, not whether STACK's mathematical result is correct. Ordinary feedback and answer notes are available for inspection but are not asserted equivalent; authored `-1` controlled-error cases separately check the error origin and exact STACK error note. The report covers this adapter's bounded scalar answer-test subset, not Moodle's PHP controller, question state, or every STACK feature; the upstream PHP fixture is parsed as data and never executed.

The [site workflow](.github/workflows/site.yml) invokes the [compliance workflow](.github/workflows/native-compliance.yml) on every supported push and pull request. Its single publication job waits for the existing site tests, the smaller native reference gate, and all three compliance checks, then publishes the tested site and independent report together. Main gets `/compliance/`; feature previews include their matching report at `previews/<branch>/compliance/`. Pull requests receive downloadable HTML and JSON artifacts, including failed runs with unavailable checks shown explicitly, but do not publish. An ordinary `quarto render` of this website does not rerun or replace the report. To reproduce locally using an official STACK checkout at `10d323311b7f39fb7b092dd10ce75f7d8632f525`, install `requirements-dev.txt`, Maxima and Playwright Chromium, then run:

```sh
python scripts/run_compliance_python.py
python scripts/run_compliance_maxima.py --stack-source /path/to/moodle-qtype_stack
python scripts/native_compliance/compatibility.py
python scripts/run_compliance_pyodide.py
python scripts/native_compliance/report.py
quarto render compliance-report
```

The generated page is `compliance-report/_site/index.html`; `compliance-report/report.json` is the downloadable report. Checkers produce independent JSON files under `test-results/compliance/`. Missing runner output, unexpected execution errors, and unexplained mismatches fail their corresponding CI checks while the report still renders for diagnosis. Rows deliberately outside the direct CAS scope remain visible as unavailable and do not fail a check solely for that reason. `tests/native_compliance/policy.json` records case-specific Python deviations; `native_policy.json` is the separate, case-specific approval list for native differences.

Serve a local render or an extracted pull-request HTML artifact over HTTP so its JSON fetch works:

```sh
python -m http.server --directory compliance-report/_site 8000
```

The original corpus question `AlgMap-2.5` grants full credit when `LowestTerms` accepts the written form before its `AlgEquiv` node runs. A reduced fraction with the wrong value can therefore receive full credit. Its passing authored qtests demonstrate replay of those specific tests, not that the upstream grading tree enforces mathematical correctness for every response. The [corpus gallery](corpus.qmd) flags this behavior beside the card.

To check a file before rendering:

```sh
PYTHONPATH=_extensions/stack-sympy python -m stack_sympy.cli test --file questions/polynomial-expansion.xml
```

`quarto render` is also a validation step: errors in a selected question stop the build. For development, `PYTHONPATH=_extensions/stack-sympy python -m unittest discover -s tests -v` runs the Python regression suite. Browser integration checks require [`requirements-dev.txt`](requirements-dev.txt) and Playwright browsers; see the tests in [`tests/`](tests/). Quarto source pages are [`index.qmd`](index.qmd), [`examples.qmd`](examples.qmd), and the [authoring guide](docs/authoring.qmd).

## Design and contribution

Student input accepts explicit arithmetic `+ − * / ^` (and `**`), parentheses, scalar symbols and constants `%pi`, `%e`, `%i`, and the functions `sqrt`, `sin`, `cos`, `tan`, `exp`, `log`, and `abs`. With `<insertstars>0</insertstars>` the learner must write multiplication as `*`; `<insertstars>1</insertstars>` additionally accepts adjacent unambiguous products such as `8x`, `2(x+1)`, `(x+1)(x-1)`, and `(x+1)x`. A multi-letter name such as `xy` remains one symbol, `x(y+1)` is rejected as an unknown function rather than guessed as a product, and `sin(x)` remains a function. Space-separated factors (`2 x`) and further insertion modes (2–7) are unsupported. This is a bounded subset of mode 1, not every STACK token-splitting rule. Author assignments `name:expression;` additionally allow lists with 1-based indexing, `rand`, `rand_with_step`, `diff`, `expand`, `factor`, `ratsimp`, `cancel`, integer `lcm(a,b)`, `ev(expr,simp)` and decimal/significant-figure display functions. `ratsimp` preserves a common-denominator form for the supported scalar expressions. The parser recognizes author `float(...)`, but floating-point question variables cannot be frozen into variants and are rejected at build time. Arbitrary functions, equations (outside the displayed CASText equality above), units, matrices, and scripts are rejected. `questionsimplify=0` is accepted only when the adapter verifies that any `EqualComAss` teacher form survives frozen author variables; otherwise it fails the build. `strictsyntax` must be `1`, `allowwords` and input `options` must be empty, and branch-specific PRT penalties are unsupported. Unrecognized validation settings and unsupported HTML/CASText tags also fail the build.

The loader in `stack_sympy/importer.py` turns native XML into an explicit JSON-safe question model. `expressions.py`, `assessment.py`, and `engine.py` implement bounded parsing, answer tests, seeded variants, PRT grading, and qtest replay; `rendering.py` handles CASText. Quarto's Lua filter selects the XML question and generates the static card, and a Pyodide worker runs the Python core in the browser. The Pyodide loading script has been synchronized with math-exercise in [companion PR #12](https://github.com/Erasmus-CTM/math-exercise/pull/12) (pending merge). The parsing and grading core here is separable for future reuse in other Python or Quarto projects.

Please add an XML export and qtests with a bug report or a new feature. Avoid relaxing unsupported-feature checks without a test showing the semantics. This project uses the [GNU Affero General Public License version 3](LICENSE) for code. Newly authored example questions are by the CTM team under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Upstream samples retain their respective licenses: the [individual provenance records](questions/upstream/sources.json) distinguish the [sample question license](questions/upstream/COPYING.txt) from the [HELM license](questions/upstream/HELM-COPYING.txt). The [new corpus](questions/corpus/README.md) contains only samples under CC BY-SA 4.0. SymPy, Pyodide, Quarto, and Moodle STACK are independent projects with their own licenses.
