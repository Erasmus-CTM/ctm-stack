# One PythonChecker interface and supplied matrix functions

All Python mathematical checks use PythonChecker and the same trusted-file
loader. The existing XML testoptions field contains a JSON object with a
registered checker name and an optional options object. Functions receive
(student, teacher, options); omitted options become an empty dictionary.
Options may contain several named settings or nested JSON data and are not
evaluated as Python or CAS expressions.

The supplied questions/matrix-checkers.py file registers five functions:

- basis, with space set to nullspace, columnspace or rowspace;
- matrix_property, with property set to integer_entries, determinant or identity;
- is_hermitian, is_positive_definite and their conjunction is_hpd.

Quarto selects the file by filename at build time, exactly as for an author's
own checker. The supplied basis function reuses the vendored vector-feedback
helper. A defining matrix specifies the target space; PRT scores, answer notes
and diagnostic vector colors are preserved. Automatic author model helpers
remain in matrix_models.py, separate from assessment.

Common parser and XML settings handle input validation. The selected function
checks its mathematical domain during grading. Generic checker preflight
validates model grading and permits valid false branches. Question authors
should choose a suitable model and exercise intended scoring with qtests.
The supplied basis and elementary property checks retain their bounded real
rational domain. The positivity checks accept rational real and imaginary parts.

The PD guide gives a short definition, names Sylvester's criterion, retains
the four-case scoring table and demonstrates both PRT policies. All pages use
the common interface and current function choices.

## Verification

- 846 tests passed, 1 skipped and 149 subtests passed, including all rendered-page checks.
- All ten website/report pages rendered; 553 local links and heading levels checked with no issues.
- All seven live matrix cards include the same supplied checker file and valid JSON configuration.
- Source-bundle freshness and the corpus replay check passed; mathematical corpus results are unchanged.
- Browser coverage exercises filename-loaded basis, property and real/complex positivity checks through the common interface. Browser and native STACK jobs run in CI.
