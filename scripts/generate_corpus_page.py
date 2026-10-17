"""Regenerate the browseable corpus page from pinned sources and replay results."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "questions/corpus"
PAGE = ROOT / "corpus.qmd"

LABELS = {
    "qtests_pass": "Passed authored tests",
    "qtests_mismatch": "Authored test mismatch",
    "unsupported_import": "Cannot import this question",
    "unsupported_instantiate": "Cannot prepare this variant",
    "unsupported_qtest": "Cannot replay its author tests",
    "timeout": "Test run timed out",
    "error": "Test run failed",
}

# Keep the pinned imports and their compatibility baseline unchanged. Live
# teaching cards may use an explicitly attributed correction instead.
CORRECTIONS = {
    "AlgMap-1-5.xml": "The worked explanation now uses multiplication in the exponent product rule, rather than the incorrect addition rule.",
    "AlgMap-6-4.xml": "The worked explanation now states c^a · c^b = c^(a+b); the original incorrectly used addition.",
    "AlgMap-2-5.xml": "A reduced answer with the wrong value can receive full credit. This defect belongs to the original response tree. The corrected card checks value equivalence before lowest-terms form and adds a wrong-value author test.",
}


def upstream_authoring_issue(entry: dict, row: dict) -> str | None:
    """Apply the reviewed diagnosis only to its reproduced failure pattern."""
    if entry["file"] != "AlgMap-8-10.xml" or row["status"] != "qtests_mismatch":
        return None
    failures = {(case["seed"], case["testcase"]) for case in row["mismatches"]}
    if failures != {(1856951054, "1"), (1856951054, "2")}:
        return None
    return (
        "**Upstream authoring bug in the PRT.** At the failing variant, "
        "`a=8`, `b=9`, `c=2`, and `d=3`, so the correct answer is "
        "`8*(t+y)/2 + 9*(t+y)/3 = 7*(t+y)`. Both authored model answers "
        "therefore have no fraction operator. The only full-credit branch "
        "requires `SingleFrac`, which rejects this product; every later branch "
        "awards zero. Authored tests 1 and 2 nevertheless expect full credit. "
        "The pinned native STACK test also rejects `7*(t+y)` under `SingleFrac`. "
        "The port's random choices expose a latent assumption in the original "
        "question; this diagnosis uses the fixed values above, rather than "
        "assuming Maxima generates those values for the same seed."
    )


def teaching_source(entry: dict) -> tuple[str, str]:
    if entry["file"] in CORRECTIONS:
        return f"questions/corrected/{entry['file']}", entry["question_name"] + " (corrected teaching copy)"
    return f"questions/corpus/{entry['file']}", entry["question_name"]


def generate() -> str:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    baseline = json.loads((CORPUS / "baseline.json").read_text(encoding="utf-8"))
    entries = manifest["questions"]
    reports = {row["id"]: row for row in baseline["questions"]}
    assert len(entries) == len(reports) == 35
    assert {entry["id"] for entry in entries} == set(reports)
    assert all(entry["file"] == reports[entry["id"]]["file"] for entry in entries)
    counts = baseline["summary"]["stages"]
    passing = [e for e in entries if reports[e["id"]]["status"] == "qtests_pass"]
    mismatched = [e for e in entries if reports[e["id"]]["status"] == "qtests_mismatch"]
    blocked = [e for e in entries if reports[e["id"]]["status"] not in {"qtests_pass", "qtests_mismatch"}]
    repository_url = f"https://github.com/{manifest['repository']}"
    commit_url = f"{repository_url}/commit/{manifest['commit']}"
    out = [
        '---\ntitle: "Question corpus"\nsubtitle: "Explore imported STACK questions and their current support"\n---',
        "",
        "Use the teacher track to choose and try a question. The [developer track](#for-developers) keeps replay details and adaptation issues together.",
        "",
        "## For teachers",
        "",
        f"These are 35 unchanged STACK XML questions from the upstream library. **The {len(passing)} questions whose authored tests passed on every replayed seed have interactive cards.** Each question has a local XML download and an observed result. One additional presentation teaching copy shows a matrix question whose original HTML is unsupported. Other originals remain available with the observed mismatch or unsupported feature shown explicitly.",
        "",
        f"In this snapshot, **{len(passing)} pass their author tests**, **{len(mismatched)} has a test mismatch**, and **{len(blocked)} cannot be fully checked here**. The [replay record](questions/corpus/baseline.json) gives the tested variants and exact results.",
        "",
        "The [worked matrix examples](examples.qmd#find-a-nonidentity-matrix-with-determinant-one) also include a determinant-one task and two basis questions. The [positive-definiteness example](examples.qmd#symmetric-positive-definite-matrix) adds a custom Python checker. These Python tests are separate from these unchanged exports and their baseline counts. See [Python answer tests](docs/python-checker-api.qmd).",
        "",
        "### Browse all 35",
        "",
        "| Question | Topic | Adapter status | Original XML |",
        "|---|---|---|---|",
    ]
    for entry in entries:
        row = reports[entry["id"]]
        name = html.escape(entry["question_name"])
        topic = html.escape(entry["topic"].replace("-", " ").replace("_", " "))
        label = "Original scoring-tree issue" if upstream_authoring_issue(entry, row) else LABELS[row['status']]
        out.append(f"| [{name}](#{entry['id']}) | {topic} | {label} | [Download](questions/corpus/{entry['file']}) |")
    out += [
        "",
        "### Five matrix-input problems",
        "",
        "The four elementary-row-operation problems below run directly from unchanged official exports: [row 2 plus a multiple of row 3](#linearalgebra-elementary-1), [row 1 plus a multiple of row 3](#linearalgebra-elementary-2), [row 2 plus a multiple of row 1](#linearalgebra-elementary-3), and [row 1 minus a multiple of row 2](#linearalgebra-elementary-4). Together their original tests pass all 24 recorded seed/case combinations. Each uses a fixed 3 by 3 matrix editor and whole-matrix algebraic equivalence; no automatic cell partial credit is added.",
        "",
        "The fifth asks learners to write a system of three linear equations as a coefficient matrix and a column vector. Its original XML is [preserved unchanged](questions/corpus/7-3-26-(Write-sim-eqns-with-matrices).xml) and remains blocked by an unsupported inline HTML style. This explicitly attributed presentation teaching copy removes that style and closes its list; variables, answers, PRT and authored qtest are unchanged. Its original qtest passes on the first three deployed seeds. This is a presentation adaptation, not evidence that the original export runs unchanged.",
        "",
        "```{.stack-question}",
        "#| file: questions/corrected/7-3-26-(Write-sim-eqns-with-matrices).xml",
        "#| question: 7.3.26 (Write sim. eqns. with matrices) (presentation teaching copy)",
        "#| seed: 1930245414",
        "#| review: true",
        "```",
        "",
        "[Download presentation teaching XML](questions/corrected/7-3-26-(Write-sim-eqns-with-matrices).xml) · [Adaptation and licensing](questions/corrected/README.md)",
        "",
        "### Ready to try",
        "",
        f"These {len(passing)} cards use a replayed variant of each question. Press **Validate answers**, then **Check answer**. **Run question tests** checks the displayed variant against the question's authored cases. Three cards use [corrected teaching copies](questions/corrected/README.md) for mathematical or grading defects in the originals. Each original remains downloadable; the [baseline](questions/corpus/baseline.json) records every tested variant.",
        "",
    ]
    for entry in passing:
        row = reports[entry["id"]]
        out += [
            f"#### {entry['question_name'].replace('*', r'\*')} {{#{entry['id']}}}",
            "",
            f"{entry['topic'].replace('-', ' ').replace('_', ' ')} · {entry['input_count']} answer field{'s' if entry['input_count'] != 1 else ''} · {entry['qtest_count']} author test{'s' if entry['qtest_count'] != 1 else ''}.",
            "",
        ]
        path, question_name = teaching_source(entry)
        if entry["file"] in CORRECTIONS:
            out += [
                "> **Corrected teaching copy:** " + CORRECTIONS[entry["file"]] + " The original XML is preserved unchanged; this card and its source panels use the corrected copy linked below.",
                "",
            ]
        out += [
            "```{.stack-question}",
            f"#| file: {path}",
            f"#| question: {question_name}",
            f"#| seed: {row['seeds'][0]}",
            "#| review: true",
            "```",
            "",
            f"[Download original XML](questions/corpus/{entry['file']})",
            *([f"[Download the corrected teaching XML]({path})"] if entry["file"] in CORRECTIONS else []),
            "",
        ]
    out += [
        "## For developers",
        "",
        "### Authored test mismatches",
        "",
        ("These cases disagree with expectations authored in the XML and are kept out of the interactive gallery. Reviewed causes are named below; an authored-test mismatch alone does not identify whether the cause is the port or the original question. The [baseline JSON](questions/corpus/baseline.json) retains the exact expected and observed results."
         if mismatched else "None among the questions replayed on every recorded seed. The [baseline JSON](questions/corpus/baseline.json) retains individual seed and test results; unsupported questions remain listed below."),
        "",
    ]
    for entry in mismatched:
        row = reports[entry["id"]]
        sample = row["mismatches"][0]
        check = sample["checks"][0]
        expected, actual = check["expected"], check["actual"]
        inputs = ", ".join(f"{k} = {v}" for k, v in sample["inputs"].items())
        out += [
            f"#### {entry['question_name'].replace('*', r'\*')} {{#{entry['id']}}}",
            "",
            *([upstream_authoring_issue(entry, row), ""] if upstream_authoring_issue(entry, row) else []),
            f"{entry['topic'].replace('-', ' ').replace('_', ' ')} · **{row['failed_cases']} failed of {row['replayed_cases']} replayed seed/case combinations.** For seed `{sample['seed']}`, case `{sample['testcase']}`, input `{inputs}`: `{check['prt']}` expected score `{expected['score']}` and answer note `{expected['note']}`, but produced score `{actual['score']}` and answer note `{actual['note']}`.",
            "",
            f"[Download original XML](questions/corpus/{entry['file']}) · [Full replay](questions/corpus/baseline.json)",
            "",
        ]
    out += [
        "### Unsupported by this adapter",
        "",
        "You can still download and inspect these original questions. Each explanation gives the first issue found while importing or preparing the question; other features may also need adaptation.",
        "",
    ]
    for entry in blocked:
        row = reports[entry["id"]]
        diagnostic = row.get("diagnostic", {})
        location = diagnostic.get("location", "replay")
        reason = diagnostic.get("reason", diagnostic.get("message", "No diagnostic recorded"))
        seed = f" at seed `{diagnostic['seed']}`" if "seed" in diagnostic else ""
        out += [
            f"#### {entry['question_name'].replace('*', r'\*')} {{#{entry['id']}}}",
            "",
            f"{entry['topic'].replace('-', ' ').replace('_', ' ')} · **{LABELS[row['status']]}{seed}.** `{location}`: {html.escape(reason)}.",
            "",
            f"[Download original XML](questions/corpus/{entry['file']}) · [Replay record](questions/corpus/baseline.json)",
            "",
        ]
    out += [
        "### How this gallery was checked",
        "",
        f"The [reproducible baseline](questions/corpus/baseline.json) records **{len(passing)} passed**, **{len(mismatched)} with test mismatches**, and **{len(blocked)} blocked** ({counts.get('unsupported_import', 0)} at import, {counts.get('unsupported_instantiate', 0)} while preparing a variant). It retained **{sum(e['qtest_count'] for e in entries)} authored test cases** and replayed **{baseline['summary']['replayed_cases']} seed/case combinations** across {baseline['summary']['instantiated_all_seeds']} prepared questions; {baseline['summary']['failed_cases']} combinations disagreed. Results for these variants do not establish complete STACK/Maxima agreement.",
        "",
        "### Sources",
        "",
        f"These unchanged questions come from the [STACK question library]({repository_url}) at its [pinned revision]({commit_url}) and retain [CC BY-SA 4.0](questions/corpus/COPYING.txt). The [source manifest](questions/corpus/manifest.json) links every question to its exact upstream file. The [presentation teaching copy](questions/corrected/README.md) records its limited HTML change and licensing; three other [corrected teaching copies](questions/corrected/README.md) record their mathematical or grading changes.",
        "",
    ]
    return "\n".join(out).rstrip() + "\n"


if __name__ == "__main__":
    PAGE.write_text(generate(), encoding="utf-8")
