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
    "unsupported_import": "Unsupported at import",
    "unsupported_instantiate": "Unsupported at instantiation",
    "unsupported_qtest": "Unsupported in test replay",
    "timeout": "Replay timed out",
    "error": "Replay error",
}


def generate() -> str:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    baseline = json.loads((CORPUS / "baseline.json").read_text(encoding="utf-8"))
    entries = manifest["questions"]
    reports = {row["id"]: row for row in baseline["questions"]}
    assert len(entries) == len(reports) == 30
    assert {entry["id"] for entry in entries} == set(reports)
    assert all(entry["file"] == reports[entry["id"]]["file"] for entry in entries)
    counts = baseline["summary"]["stages"]
    passing = [e for e in entries if reports[e["id"]]["status"] == "qtests_pass"]
    mismatched = [e for e in entries if reports[e["id"]]["status"] == "qtests_mismatch"]
    blocked = [e for e in entries if reports[e["id"]]["status"] not in {"qtests_pass", "qtests_mismatch"}]
    source_root = manifest["source_base_url"]
    repository_url = f"https://github.com/{manifest['repository']}"
    commit_url = f"{repository_url}/commit/{manifest['commit']}"
    out = [
        '---\ntitle: "Question corpus"\nsubtitle: "Thirty unchanged STACK exports, with a measured adapter boundary"\n---',
        "",
        "These are 30 native STACK XML questions from the upstream library. Each question below has a local XML download, its pinned upstream source, and a result from the current adapter. **Only the six questions whose authored tests passed on all three replayed seeds have interactive cards.** The others remain available for inspection, with the observed mismatch or unsupported feature shown explicitly.",
        "",
        f"The [reproducible baseline](questions/corpus/baseline.json) reports **{len(passing)} passed**, **{len(mismatched)} with test mismatches**, and **{len(blocked)} blocked** ({counts.get('unsupported_import', 0)} at import, {counts.get('unsupported_instantiate', 0)} at instantiation). It retained **{sum(e['qtest_count'] for e in entries)} authored test cases** and replayed **{baseline['summary']['replayed_cases']} seed/case combinations** across {baseline['summary']['instantiated_all_seeds']} instantiated questions; {baseline['summary']['failed_cases']} combinations disagreed. Passing those bounded checks is evidence for the listed seeds, not complete STACK/Maxima parity.",
        "",
        f"**Attribution and reuse.** Questions are from [STACK / maths/moodle-qtype_stack]({repository_url}), pinned at commit [`{manifest['commit']}`]({commit_url}). The unchanged question exports carry the [CC BY-SA 4.0 license]({source_root}samplequestions/COPYING.txt), also [included locally](questions/corpus/COPYING.txt); see each pinned source link below. The [manifest](questions/corpus/manifest.json) records the exact upstream path and SHA-256 for every XML file.",
        "",
        "## Browse all 30",
        "",
        "| Question | Topic | Adapter status | Original XML |",
        "|---|---|---|---|",
    ]
    for entry in entries:
        row = reports[entry["id"]]
        name = html.escape(entry["question_name"])
        topic = html.escape(entry["topic"].replace("-", " ").replace("_", " "))
        out.append(f"| [{name}](#{entry['id']}) | {topic} | {LABELS[row['status']]} | [Download](questions/corpus/{entry['file']}) |")
    out += [
        "",
        "## Ready to try",
        "",
        "These six cards use the first seed from each three-seed replay. Press **Validate answers**, then **Check answer**. **Run author tests** replays the original XML test cases on the displayed seed; the [baseline](questions/corpus/baseline.json) covers all three recorded seeds. Their source panels start closed and expose both the authored block and unchanged STACK XML.",
        "",
    ]
    for entry in passing:
        row = reports[entry["id"]]
        out += [
            f"### {entry['question_name'].replace('*', r'\*')} {{#{entry['id']}}}",
            "",
            f"{entry['topic'].replace('-', ' ').replace('_', ' ')} · {entry['input_count']} input{'s' if entry['input_count'] != 1 else ''} · {entry['qtest_count']} authored tests · baseline seeds {', '.join(f'`{s}`' for s in row['seeds'])}.",
            "",
            "```{.stack-question}",
            f"#| file: questions/corpus/{entry['file']}",
            f"#| question: {entry['question_name']}",
            f"#| seed: {row['seeds'][0]}",
            "#| review: true",
            "```",
            "",
            f"[Download original XML](questions/corpus/{entry['file']}) · [Pinned upstream source]({entry['source_url']})",
            "",
        ]
    out += [
        "## Authored test mismatches",
        "",
        "These six questions import and instantiate, but the adapter's replay disagrees with outcomes authored in the XML. Their grading is therefore not presented as a working exercise. The [baseline JSON](questions/corpus/baseline.json) lists every failed seed, input, PRT, expected result, and observed result.",
        "",
    ]
    for entry in mismatched:
        row = reports[entry["id"]]
        sample = row["mismatches"][0]
        check = sample["checks"][0]
        expected, actual = check["expected"], check["actual"]
        inputs = ", ".join(f"{k} = {v}" for k, v in sample["inputs"].items())
        out += [
            f"### {entry['question_name'].replace('*', r'\*')} {{#{entry['id']}}}",
            "",
            f"{entry['topic'].replace('-', ' ').replace('_', ' ')} · **{row['failed_cases']} failed of {row['replayed_cases']} replayed seed/case combinations.** For seed `{sample['seed']}`, case `{sample['testcase']}`, input `{inputs}`: `{check['prt']}` expected score `{expected['score']}` and answer note `{expected['note']}`, but produced score `{actual['score']}` and answer note `{actual['note']}`.",
            "",
            f"[Download original XML](questions/corpus/{entry['file']}) · [Pinned upstream source]({entry['source_url']}) · [Full replay](questions/corpus/baseline.json)",
            "",
        ]
    out += [
        "## Unsupported by this adapter",
        "",
        "These original questions remain inspectable. Each reason is the first recorded failure at the indicated import or instantiation stage; later features have not been assessed.",
        "",
    ]
    for entry in blocked:
        row = reports[entry["id"]]
        diagnostic = row.get("diagnostic", {})
        location = diagnostic.get("location", "replay")
        reason = diagnostic.get("reason", diagnostic.get("message", "No diagnostic recorded"))
        seed = f" at seed `{diagnostic['seed']}`" if "seed" in diagnostic else ""
        out += [
            f"### {entry['question_name'].replace('*', r'\*')} {{#{entry['id']}}}",
            "",
            f"{entry['topic'].replace('-', ' ').replace('_', ' ')} · **{LABELS[row['status']]}{seed}.** `{location}`: {html.escape(reason)}.",
            "",
            f"[Download original XML](questions/corpus/{entry['file']}) · [Pinned upstream source]({entry['source_url']}) · [Replay record](questions/corpus/baseline.json)",
            "",
        ]
    return "\n".join(out).rstrip() + "\n"


if __name__ == "__main__":
    PAGE.write_text(generate(), encoding="utf-8")
