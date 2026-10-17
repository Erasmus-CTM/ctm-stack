# STACK answer-test fixture inventory

`fixtures.json` transcribes **all 2,303 rows** of the static
`stack_answertest_test_data::$rawdata` array from
[`tests/fixtures/answertestfixtures.class.php`](https://github.com/maths/moodle-qtype_stack/blob/10d323311b7f39fb7b092dd10ce75f7d8632f525/tests/fixtures/answertestfixtures.class.php)
at upstream commit `10d323311b7f39fb7b092dd10ce75f7d8632f525`. The JSON
records the source byte SHA-256, original row order and source line, all seven
standard positional fields, and any trailing positional fields. The 2,303
rows span 41 distinct answer-test names. The expected score includes upstream
negative sentinel values (`-1`, `-2`, `-3`); these are fixture expectations,
not native checker verdicts.

This is the **static array inventory**, not the complete result of the PHP
`get_raw_test_data()` accessor. That accessor also appends dynamically generated
rows from `equivfixtures.class.php`. Those rows fall outside the supported native
checker families under review and are not represented in this inventory. The
`inventory.by_test` counts include every static family, regardless of whether
the native adapter implements it. An inventory row should not be read as a
claim of compatibility or a passing test.

`id` is the SHA-256 of the complete parsed positional row (compact UTF-8 JSON)
followed by a one-based occurrence suffix. This retains duplicate rows as
distinct cases while keeping content-based identity stable if rows move. `ordinal`
is one-based; `source_line` is the opening row's line in the pinned PHP source.
The import accepts only arrays, literal strings and numbers, literal booleans
and nulls, comments, unary minus on numbers, and literal string concatenation.
An unsupported PHP expression fails the import; no PHP is executed.

To regenerate from a **local checkout at the pinned revision**:

```sh
python scripts/import_stack_fixtures.py --upstream ../stack-upstream
python scripts/import_stack_fixtures.py --upstream ../stack-upstream --check
python -m unittest tests/test_fixture_import.py
```

`--check` verifies the local checkout revision, source byte hash and every
generated JSON field against the checked-in artifact. It makes no network
requests.

The upstream PHP file is part of STACK (`maths/moodle-qtype_stack`), copyright
2012 University of Birmingham, licensed under the GNU GPL version 3 or later.
See its original header and the accompanying [GNU GPL text](COPYING.txt).
The imported fixture values and explanatory source notes are attributed to
that file; this project’s own license does not replace upstream notices.
