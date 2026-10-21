# Handoff: Erasmus-CTM/stack-sympy

## Erasmus-CTM/stack-sympy — main 1b1d50f

- Since S1/S2: uses ctm-libs + ctm-checkers (STACK wheel); card HTML still built in Python (moves to Lua in step 6); no-AI builds follow `ctm.feedback.request`; site publishes the ctm-checkers compliance report (pins in `.github/pins.json` + `native-stack.yml@<pin>` in `site.yml` must move together).
- Next: pin PR for each ctm-checkers STACK set; S-14 source panels (`#| source-panels: true`, default hidden); **step 6**: `stack-sympy:` settings section, catalogue (S-17), shared matrix input (removes `vendor/matrix-input.*`), shared typesetting (S-16), shared runtime/worker with Stop, accessibility (S-18), packaging in CTM Assessment, H1 syntax.

---

## Common context (same in every repo)

This file hands the remaining work to another agent (e.g. Codex). Published designs live in `Erasmus-CTM/ctm-assessment` `docs/consolidation/` (the step-5 offline/exam design and the variants design are added there by the handoff branch of ctm-assessment).

## Where things stand

| Step | State |
|---|---|
| 1 ctm-libs (shared library, ai-feedback renamed) | merged |
| 2 ctm-checkers (all checker Python in one place) | merged; STACK fix chain in progress (S-01, S-02, S-13 merged; S-07/S-05/S-10/S-11 in progress) |
| 3 pyodide-interaktiv onto ctm-libs | merged (ctm-libs #27, math-exercise #26, py-exercise #9, pyodide-interaktiv #5, ctm-assessment #22); alias removal L3x/U3c not started |
| 4 UI (reveals, modes, tab links, autosave) | phase A merged; ctm-demo migrated; final set open (ctm-libs #30 + ctm-assessment #24); ingmat3a migration waits for AC to merge `linalg-branch` into ingmat3a `main`; phases B (store/progress/quizzes/export) and C (languages) not started |
| 5 runtime + offline/exam build | designed and approved (`ctm-assessment` `docs/consolidation/2026-10-step5-offline-exam.md`), not started; December exam is a target, not a constraint |
| 6 stack-sympy onto shared runtime, packaged | not started |
| 7 grading options | not started |
| 8 PR to pyodide-interaktiv `main` | not started (AC's members decide) |
| Variants redesign | designed and approved (`ctm-assessment` `docs/consolidation/2026-10-variants.md`), not started; after the question-tests PR |

Open PRs at hand-off: ctm-libs #30 and ctm-assessment #24 (one set, see their files); a ctm-checkers + stack-sympy STACK set may appear (S-07/S-05/S-10/S-11), opened by an agent still running at hand-off. **None of these has had its independent review yet.** Review before AC merges.

## Rules (binding, from AC)

- **AC merges everything.** Agents never merge, never force-push a published branch, never create release tags. Merge commits only.
- **Merge protocol for sets** (ctm-assessment `docs/consolidation`, step-1 §12.1): a set of cross-repo PRs pins its dependencies at the reviewed PR head commits (never merge commits), carries no review-ref trailers, every branch is up to date with its base, one combined CI run tests the whole set, and AC merges it in one sitting in a stated order. Before sending: head SHAs unchanged, not behind; after merging: merge tree equals head tree.
- **Commits** are authored AND committed as `Andrey Chesnokov <aacchhee@gmail.com>`. Add a trailer naming the agent that did the work (earlier commits used `Co-Authored-By: Claude … <noreply@anthropic.com>`); keep AC's identity as author/committer.
- **Independent review** of every PR (fresh reviewer, max effort) until nothing substantive remains; CI watched until green. Reviews before every merge request to AC.
- **No code duplication across repos.** One home per piece of code (ctm-libs: runtime/UI/bootstrap/feedback; ctm-checkers: all checker Python; components keep only their own Lua/JS/CSS). Generated copies (shipped ctm-libs copy in pyodide-interaktiv, bootstrap copies) must be produced and CI-checked by script.
- **No backwards-compatibility break without AC's approval.**
- **Licence:** AGPL-3.0-or-later for code. Question XML: CTM's own CC BY-SA 4.0; STACK fixtures GPL-3.0 with notice; HELM rows CC BY-NC (test data only, labelled).
- **No HTML in Markdown authoring.**
- **ingmat3a must build green and clean** (0 warnings). Course `main` branches change only through migration PRs that AC merges.
- **Wording rule (STACK):** two upstream STACK security issues were reported privately (feedback-variable names; question-variable names with Greek letters or underscores). In anything public, describe only what our engine does ("student answers may not use question- or feedback-variable names"); never describe STACK's behaviour on this.
- **Courses:** ingmat3a is pinned to ctm-assessment `9ed46a4` until its migration PR; ctm-demo follows `ref: main`.

## Environment notes (from this session; may differ for you)

- GitHub GraphQL, codeload.github.com and jsDelivr were blocked; Actions logs could not be downloaded (read check-run annotations instead). Browser tests that need CDN files route them to local copies (see `ctm-assessment` tools and the Pyodide dist notes).
- Only Chromium ran locally; Firefox and WebKit run in CI.
- Quarto 1.8.27; Pyodide 0.28.3 (0.27.2 also tested).

## Housekeeping for AC

- Delete branches: ctm-demo `stack-repro`, `stack-notes`; ctm-assessment `diag/s10-webkit`; ctm-libs `consolidation/2026-10-step3-review`, `probe/webkit-tabs`.
- Optional: delete ctm-demo Actions artifact 12325605804 (old PR #15 build).
- STACK author: send the "semantics page updated" note once https://erasmus-ctm.github.io/stack-sympy/compliance/semantics.html#author-attention shows eight rows (it was deployed; the CDN was still serving the old page at hand-off). Second private STACK report (question-variable names) is ready in `ctm-audit-2026-10/stack/private/stack-question-variable-names.zip` if not yet sent.
- jsxgraph-quarto PR #2 (fork aacchhee/jsxgraph-quarto `audit/2026-10`, head 0b64e98) bundles 1.14.1 and is ready; paste `jsxgraph/pr2-update-1.14.1.md` into its description and send `jsxgraph/reply-2026-10-21.txt`.
