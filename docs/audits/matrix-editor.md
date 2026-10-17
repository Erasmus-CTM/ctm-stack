# Vendored matrix editor audit

The editor source is math-exercise commit `f238da6d9a43d58d1fdf9ad592ac6223225268e0` (companion PR #20). JavaScript and CSS are copied unchanged; the vendoring manifest records source URLs, SHA-256 hashes and AGPL-3.0-or-later licensing. STACK captures the supplied constructor at startup and owns parsing, validation, grading and feedback policy.

An independent Sol xhigh audit reviewed this integration before its pull request. Findings were resolved: isolate scalar/action CSS from editor controls; correct the provenance license; reject explicit author dimensions excluding the teacher; publish the provenance resource; and retain the pinned constructor across later global replacements. The shared engine shape check and its new regressions received a separate Sol xhigh re-review. Render assertions follow Quarto's actual asset URLs rather than assuming source subdirectories are retained.

Final local checks passed: one actual Quarto site asset/provenance test (31.23 seconds) and one real Worker/Pyodide browser test (32.41 seconds). The browser exercises raw expressions and incomplete cells, structural breakout rejection, resizing, validation/check invalidation, AI evidence, reset, variants, constructor isolation and authored qtests. Syntax and focused parser/input checks also passed during the independent review. Full site/browser and native compliance checks remain enforced by the PR GitHub Actions workflow.

Only input validity is projected onto the editor. PRTs retain responsibility for scoring, and no cell, row or column partial credit is inferred from presentation states. Matrix operations and additional answer tests remain outside the documented bounded contract.
