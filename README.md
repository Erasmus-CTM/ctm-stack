# STACK SymPy

Native Moodle STACK questions on interactive, static Quarto pages. Keep the exported XML and the authored question tests; this extension imports a documented subset, freezes seeded variants when Quarto builds the page, and checks student answers with SymPy in a browser worker. The [live example site](https://erasmus-ctm.github.io/stack-sympy/) starts with a form-sensitive algebra question and also shows algebraic equivalence and numerical grading.

This is for formative exercises and inspection of supported STACK material. It is not Moodle STACK, Maxima, or a substitute for a proctored assessment. Authoring features outside the subset fail visibly at build time. In `diagnostics: true` mode a diagnostic card appears instead, which is useful while adapting an export.

## Try the examples

The three new questions in [`questions/`](questions/) are ordinary Moodle `<quiz><question type="stack">…</question></quiz>` exports, with input settings, response trees, deployed seeds, and native `<qtest>` cases. [`questions/upstream/`](questions/upstream/) holds unchanged STACK sample questions with provenance and license details in [`sources.json`](questions/upstream/sources.json).

| Question | What it demonstrates |
|---|---|
| [Expand a product](questions/polynomial-expansion.xml) | Seeded coefficients; `EqualComAss` checks expanded/collected form, then `AlgEquiv` awards half credit for an equivalent expression still in factored form. |
| [Equivalent rational expression](questions/rational-equivalence.xml) | `AlgEquiv` accepts both simplified and unsimplified forms on the stated domain; a second PRT node gives reciprocal-specific feedback. |
| [Rectangle and triangle measurements](questions/numerical-measurement.xml) | Three weighted PRTs: `NumAbsolute` within 0.25 cm, `NumRelative` within 2%, and `NumDecPlaces` requiring `17.50` rather than `17.5`. |
| [Imported STACK samples](questions/upstream/) | Unmodified `AlgMap-6.1`, BODMAS, and rounding exports for testing adapter behavior against real files. |

## Install in a Quarto project

Install the extension with `quarto add Erasmus-CTM/stack-sympy`, or copy this repository's `_extensions/stack-sympy` folder into your project. In a project installed via `quarto add`, also run `python -m pip install 'sympy==1.13.3'` in the Python environment Quarto uses; that project does not receive this repository's requirements file. Build-time rendering uses Python 3.11+ and Quarto 1.4+. For a local checkout:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
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
```
````

A learner enters answers, presses **Validate answers** to inspect how each expression was parsed, then presses **Check answer** to grade the validated response. Editing a field clears its validation and requires another Validate step. The preview preserves the written form, so `x+x` still appears as `x+x`; this is important when an answer test checks form. Invalid input receives a validation message and cannot be graded until corrected.

Each rendered question also has closed **Show source** and **Show STACK source** panels below it. They show the authored Quarto fenced block and the original XML file, respectively, for inspection or copying. Opening either panel does not affect the question or its grading.

`file` and `question` are required. `variants` is 1–20 (default 1); `seed` is a signed integer (default 1). `review: true` exposes the authored qtests for inspection. `diagnostics: true` displays build errors in the rendered page during authoring. Remove diagnostics for publishing, so unsupported content fails the build. A seed produces repeatable variants in this adapter, but is **not** expected to match Maxima's random sequence for the same seed.

## Supported subset and grading behavior

| Feature | Current handling |
|---|---|
| Input types | Scalar `algebraic` and `numerical`; strict syntax, forbidden words/floats, lowest-term fractions, and validation flags within the implemented parser. |
| Expressions | Arithmetic, powers, scalar symbols, and a constrained allowlist of Maxima-like variable assignments and functions. Seeded `rand(n)` works for the examples. No arbitrary Maxima evaluation. |
| Answer tests | `AlgEquiv`, `EqualComAss`, `NumAbsolute`, `NumRelative`, `NumDecPlaces`. Blank options mean a 0.05 tolerance for the first two numeric tolerance tests; `NumDecPlaces` requires an explicit count from 1 to 50 decimal places. |
| PRTs | Acyclic graphs of answer-test nodes, branch scores with `=`, `+`, or `-`, feedback, answer notes, and weighted aggregation across response trees. |
| Author tests | Native `<qtest>` inputs with expected PRT score, penalty, and answer note. Test outcomes are available in review mode and the CLI. |
| CASText | Scalar `{@expression@}` plus `[[input:name]]`, `[[validation:name]]`, and `[[feedback:name]]` in sanitized HTML. |

`EqualComAss` requires its `sans` to be the direct input name so the raw student expression form survives validation; it checks that form up to commutative/associative reordering; `AlgEquiv` checks symbolic equivalence using SymPy transformations. Numerical tolerance is based on the mathematical value, while `NumDecPlaces` also examines the raw written decimal and its trailing zeros. The XML `penalty` is compared in an authored qtest as an initial-attempt expectation. The demo itself has no Moodle attempt state or persistence. The adapter does not claim all STACK tests, expression forms, domains, validation behaviors, question-level options, or Maxima semantics. It raises a question-and-field-specific error when it knows an author feature cannot be preserved. Authors should run the qtests, inspect rendered variants, and compare consequential questions in Moodle.

To check a file before rendering:

```sh
PYTHONPATH=_extensions/stack-sympy python -m stack_sympy.cli test --file questions/polynomial-expansion.xml
```

`quarto render` is also a validation step: errors in a selected question stop the build. For development, `PYTHONPATH=_extensions/stack-sympy python -m unittest discover -s tests -v` runs the Python regression suite. Browser integration checks require [`requirements-dev.txt`](requirements-dev.txt) and Playwright browsers; see the tests in [`tests/`](tests/). Quarto source pages are [`index.qmd`](index.qmd), [`examples.qmd`](examples.qmd), and the [authoring guide](docs/authoring.qmd).

## Design and contribution

Student input accepts explicit arithmetic `+ − * / ^` (and `**`), parentheses, scalar symbols and constants `%pi`, `%e`, `%i`, and the functions `sqrt`, `sin`, `cos`, `tan`, `exp`, `log`, and `abs`. Author assignments `name:expression;` additionally allow lists with 1-based indexing, `rand`, `rand_with_step`, `diff`, `expand`, `factor`, `ratsimp`, `cancel`, `ev(expr,simp)` and decimal/significant-figure display functions. The parser recognizes author `float(...)`, but floating-point question variables cannot be frozen into variants and are rejected at build time. Arbitrary functions, implicit multiplication, equations, units, matrices, and scripts are rejected. `questionsimplify=0` is accepted only when the adapter verifies that any `EqualComAss` teacher form survives frozen author variables; otherwise it fails the build. `insertstars` must be `0`, `strictsyntax` must be `1`, `allowwords` and input `options` must be empty, and branch-specific PRT penalties are unsupported. Unrecognized validation settings and unsupported HTML/CASText tags also fail the build.

The loader in `stack_sympy/importer.py` turns native XML into an explicit JSON-safe question model. `expressions.py`, `assessment.py`, and `engine.py` implement bounded parsing, answer tests, seeded variants, PRT grading, and qtest replay; `rendering.py` handles CASText. Quarto's Lua filter selects the XML question and generates the static card, and a Pyodide worker runs the Python core in the browser. The Pyodide loading script has been synchronized with math-exercise in [companion PR #12](https://github.com/Erasmus-CTM/math-exercise/pull/12) (pending merge). The parsing and grading core here is separable for future reuse in other Python or Quarto projects.

Please add an XML export and qtests with a bug report or a new feature. Avoid relaxing unsupported-feature checks without a test showing the semantics. This project uses the [GNU Affero General Public License version 3](LICENSE) for code. Newly authored example questions are by the CTM team under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); upstream samples retain their own [CC BY-SA 4.0 attribution and provenance](questions/upstream/sources.json) and [license](questions/upstream/COPYING.txt). SymPy, Pyodide, Quarto, and Moodle STACK are independent projects with their own licenses.
