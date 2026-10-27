# Upstream compiler adversarial audit — 2026-10-27

Audited STACK revision: [`33383047af39c204bf4442802a058f8b918b2b1b`](https://github.com/maths/moodle-qtype_stack/tree/33383047af39c204bf4442802a058f8b918b2b1b), library version `2026101500`.
These results concern this exact pin; upstream HEAD has not been retested.
No upstream source files were modified. PHP is a **test oracle only**, with
upstream API emulation; mathematical evaluation uses the owned runtime-v3.
Nothing has been submitted upstream by this audit.

## Findings to send upstream

| ID | Finding | Suggested severity | Status |
|---|---|---|---|
| U1 | CASText static placeholders overwrite literal author content | Medium, content correctness | Reproduced through compilation, native evaluation and upstream rendering |
| U2 | Escaped Markdown equation endings leave math mode enabled | Medium, rendering correctness | Reproduced in upstream parser with passing HTML and Markdown controls |
| U3 | Public PRT score API perturbs already rounded decimal scores | Low, numerical precision | Confirmed behavior; intent/compatibility discussion needed before calling it a defect |

Severity describes the demonstrated effect. No security exploit or broad grading
failure is asserted for U1/U2. U3 is not a demonstrated question-test failure.

### U1 — CASText static placeholder collides with literal text

**Suggested issue title:** CASText static extraction replaces literal `//CT2S0//` with unrelated text

Author text:

```text
A sufficiently long static prefix {@x@} literal //CT2S0//
```

Set `x:1`. Compile with a fresh `castext2_static_replacer`, evaluate in Maxima,
restore static strings using the same replacer, then call
`castext2_parser_utils::postprocess_parsed`.

Expected:

```text
A sufficiently long static prefix \({1}\) literal //CT2S0//
```

Actual:

```text
A sufficiently long static prefix \({1}\) literal A sufficiently long static prefix
```

The extractor allocates `//CT2S0//` for the initial long static prefix. It avoids
extracting text that already contains `//CT2S`, but `replace()` subsequently
replaces that literal occurrence anyway. This is a collision between an internal
marker and valid author content, without malformed input or a modified compiler.
Changing the literal to `KEEP` is a passing control. Nested array replacement and
the final upstream renderer both reproduce the corruption.

Relevant source: [`castext2_static_replacer.class.php`](https://github.com/maths/moodle-qtype_stack/blob/33383047af39c204bf4442802a058f8b918b2b1b/stack/cas/castext2/castext2_static_replacer.class.php),
`extract`, `add_to_map` and `replace`. Allocated markers explicitly assume that
the spelling never occurs in normal content.

Suggested direction: reserve/escape literal markers before extraction, or use
typed placeholder nodes rather than global string replacement. A randomized
prefix alone needs a collision check across all source text and consideration of
runtime strings. Add a round-trip assertion preserving literal marker spellings.
Our compiler uses a deterministic per-question prefix checked against all author
source, and has a regression for this literal-author collision; arbitrary
runtime-generated collisions are a separate boundary.

### U2 — Escaped Markdown environment ending does not clear math mode

**Suggested issue title:** CASText math_paint sets math mode to true on escaped Markdown `end` environments

Call `castext2_parser_utils::parse($source, FORMAT_MARKDOWN)` with the following
literal text (two backslashes before `begin` and `end`, one before each brace):

```text
\\begin\{equation\}{@1@}\\end\{equation\} outside {@2@}
```

Inspect `mathmode` on the two parsed `latex` blocks. Expected `[true, false]`;
actual `[true, true]`. Escaping only the opening brace reproduces the same error:

```text
\\begin\{equation}{@1@}\\end\{equation} outside {@2@}
```

Controls both return `[true, false]`:

```text
HTML:     \begin{equation}{@1@}\end{equation} outside {@2@}
Markdown: \\begin{equation}{@1@}\\end{equation} outside {@2@}
```

Relevant source: [`castext2/utils.php`](https://github.com/maths/moodle-qtype_stack/blob/33383047af39c204bf4442802a058f8b918b2b1b/stack/cas/castext2/utils.php),
`math_paint`, escaped Markdown `end\\{...` branches: both set `$mathmode = true`,
where the ordinary `end{...}` branch sets it to false. `latex.block.php` uses
this flag to decide whether it must add inline math delimiters, so subsequent
text expressions are compiled as if already inside mathematics.

Suggested fix: change both escaped `end` assignments to false, with regression
tests covering escaped opening brace, both braces, and the two controls above.
Use the actual `FORMAT_MARKDOWN` constant in reproductions: the API emulation
declares string constants whereas Moodle's constants are integers. Passing a
hard-coded integer to emulation introduces a harness mismatch and is not this
finding. Our initial harness had that mismatch; it was corrected before these
observations were recorded.

### U3 — Continued-fraction conversion perturbs three-decimal PRT scores

**Suggested discussion title:** Should `prt_evaluatable::get_score()` preserve the PRT compiler's rounded decimal score?

Minimal public-API reproduction after upstream bootstrap:

```php
$p = new prt_evaluatable('prt_audit()', 1, new castext2_static_replacer([]), []);
$p->set_cas_evaluated_value('[[],0.618,0.1,"",[]]');
$p->set_cas_status([], [], []);
var_dump($p->get_score()); // 0.6179775280898876, rather than 0.618
```

Other examples: `0.123` becomes `0.12307692307692308`; `0.142` becomes
`0.1419753086419753`. Across every `i/1000`, `i=0..1000`, **761/1,001** scores
change by more than `1e-12`; the maximum absolute change is approximately
`0.000098901098901108`.

The PRT compiler already clips and rounds scores to three decimal places.
`prt_evaluatable::unpack` then calls
`stack_utils::fix_to_continued_fraction(..., 4)`, which deliberately accepts a
rational approximation within `1e-4`. `get_fraction()` multiplies the returned
score by the weight, so the discrepancy is externally observable. Whether this
is intended legacy behavior should be established with upstream maintainers.

**Correction to the initial investigation:** exceeding the question-test
comparison tolerance does **not** imply a failing upstream question test.
`stack_question_test_result::get_prt_states` applies `round_prt_scores` to both
expected and actual scores first. Repeating that exact normalization gives
**zero mismatches across all 1,001 samples**. We must not report this as a
question-test failure. Our new compiler keeps the native three-decimal value;
that is an explicit compatibility difference pending discussion, not proof that
upstream intended a different result.

## Passing coverage and independent checks

- **120 acyclic PRT graphs, 2,572 complete verdict assignments**: the upstream
  PHP compiler's emitted programs match an independent path-walking, Decimal
  arithmetic reference for score, penalty, visited nodes and branch notes.
  Tests exercise branches that skip nodes, converge, terminate early, and use
  `=`, `+`, `-`, `*`, clipping and rounding. There are **zero mismatches**.
- The clean Python PRT compiler independently passed the same 2,572 assignments
  against that reference in runtime-v3. Neither compiler is the other's oracle.
- The native graph audit stubs `ATAlgEquiv` verdicts deliberately. It tests the
  compiler and score calculation, **not the mathematical correctness of answer
  tests**. Earlier mathematical findings on older pins are not silently carried
  forward as newly verified findings.
- CASText controls preserve ordinary text, Unicode including emoji, and the
  transition out of `\(...\)` math. Dollar-delimiter behavior is recorded but
  is not promoted to a defect without establishing its upstream contract.
- Our frontend regressions cover the literal-marker collision, exact large
  integers beyond JavaScript's safe-integer range, closing inline math, and
  rejection of author execution/scope mutation. Those checks supplement the
  Python graph tests. Bugs fixed in our pre-merge frontend are not attributed
  to upstream.

This audit does not certify the entire Moodle integration, all CASText blocks,
all answer tests, PythonCheckers, or resource-exhaustion resistance. It supports
a clean Python PRT implementation with upstream comparison and independent
semantic references; it does not justify a blind translation.

## Reproduction and raw evidence

From the repository root, with Node, a project Python test environment, the
pinned STACK checkout and the verified owned runtime-v3 package:

```sh
python tests/native/oracle/run-adversarial.py \
  --stack-source /path/to/pinned-stack \
  --runtime /path/to/runtime-v3-package \
  --output /path/to/new-audit-output
```

PHP needs `intl` and `mbstring`. Alternatively add `--docker-image IMAGE` for an
existing PHP image containing those extensions. The runner uses `--pull=never`
and `--network none`; source mounts are read-only. The image is test
infrastructure and is not shipped in the author build or browser runtime.
Runtime verification remains enforced by `NodeMaximaSession`.

The runner rejects another STACK revision or tracked source modifications,
creates a temporary API configuration from upstream's sample, runs unmodified
upstream PHP, evaluates its programs in runtime-v3, and calls the upstream
replacer and renderer. It records raw inputs, compiled programs, native results,
rendered strings, versions, runtime identity and SHA-256 hashes of compressed
raw evidence in `summary.json`.

Checked-in evidence is under
[`upstream-compiler-2026-10-27/`](upstream-compiler-2026-10-27/summary.json).
The reproducible graph corpus and reference are in `tests/native/oracle/` and
`tests/native/test_prt_compiler.py`.
