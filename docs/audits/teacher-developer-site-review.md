# Teacher and developer website review

The full published site has nine content pages plus one legacy guide link.
General content pages now place teaching decisions and activities before
developer reference or evidence. The semantics page is the intentional exception:
it serves a third reader, STACK authors and maintainers, and retains its
questions-first organization. The other compatibility pages link directly to
it. The legacy `python-answer-tests` page remains a short
link to the combined guide. Navigation exposes the authoring guide, matrix
input, Python answer tests, the SPD walkthrough and semantics for STACK authors.

The SPD guide has one complete developer walkthrough. Its teacher section and
the worked-questions gallery contain live cards linked to that walkthrough.
Question sources remain at the ends of the example collections. Existing
exercise IDs and referenced section anchors are retained.

## Coverage map

| Feature group | Website explanation |
|---|---|
| Installation, Python selection, HTML/HTTP serving, first-use runtime download | `docs/authoring.qmd`: teacher start/publish and developer block reference |
| All 12 Quarto options, including context, policies and filename-selected checkers | `docs/authoring.qmd#question-block-options` |
| Validate, Check, variants, source panels, author tests, diagnostics | Teacher authoring workflow and developer option table |
| All ten native answer-test names, form/value distinctions, partial credit | Teacher choice table and developer form/PRT references; worked questions and corpus |
| Scalar functions, aliases and all author helpers | Developer notation and helper references in the authoring guide |
| Boolean operators/aliases, polynomial equations, multiplicity and unsupported forms | Developer collection/equation reference; worked logic questions |
| Lists, sets, nesting, repetitions, applicability and exact/decimal restrictions | Authoring reference and mathematical conventions |
| XML input settings, assumptions, simplification and CASText placeholders | `docs/authoring.qmd#input-and-xml-reference` |
| Fixed/resizable matrix input, dimensions, editing, reset and diagnostics | Teacher/developer matrix-input guide |
| Null/column/row-space choice, legacy span modes and automatic model generation | Combined Python answer-test guide |
| MatrixProperty expected value, its three conditions and PRT scoring | Combined Python answer-test guide and determinant example |
| SPD and custom checker filename, arguments/results, domain, feedback and testing | Teacher SPD activity plus one developer walkthrough and API reference |
| AI Feedback policies, inheritance, context modes, language, provider settings, privacy and reset | Teacher policy choices and developer configuration reference |
| Visual context and shared context aliases | Developer policy configuration reference |
| qtests, penalty/note interpretation, runtime, compatibility and contribution | Developer authoring reference and report pages |
| Domain/branch conventions, known differences, proof limits and saved evidence | Report interpretation for teachers, reproduction for developers, and a dedicated questions/evidence page for STACK authors |

A source-to-documentation inventory found all 13 answer-test names, 51 callable
names/aliases, nine logical operators/aliases and all 12 block options in the
public guides. This is a coverage check, not a claim that every option has a
separate live exercise. Form tests and column/row-space basis choices are
explained in the reference even where no dedicated live card is included.

## Review method

The site was rendered with Quarto 1.8.27 using the local JavaScript Sass
compiler, as in the earlier validation. The compliance pages were rendered
with the real saved public reports (2,303 imported cases and 170 project
regressions); no mathematical observations were invented or recomputed for
this presentation review. A combined-site scan checks local links/fragments,
header nesting and teacher/developer anchors, including the report subsite.

The render-test question-fence reader now distinguishes live question blocks
from literal Quarto examples inside longer Markdown fences. It retains the
checks that rendered cards, source panels, question payloads and assets match
what the pages actually author.

## Validation outcome

- 791 Python tests and 14 rendered-page tests passed; 1 skipped, 149 subtests passed.
- All ten website/report pages rendered. The final combined-site scan found no
  missing local link targets/fragments or skipped heading levels; teacher/developer
  anchors are present on the eight general content pages, with the semantics
  and legacy-link pages intentionally exempt.
- Corpus baseline replay and generator round-trip passed. The runtime source
  bundle remains consistent with the unchanged grader core.
- Browser interaction and native STACK checks are left to PR CI; local Chromium
  cannot start in this environment.
