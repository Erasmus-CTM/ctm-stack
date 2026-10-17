"""Build-time Quarto interface: emit a self-contained question fragment."""

from __future__ import annotations

import argparse
import html
import json
import sys

from .engine import instantiate, run_question_tests
from .importer import UnsupportedQuestion, import_xml


def _json_script(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render(path: str, question_name: str, identifier: str, count: int = 3,
           seed: int = 1, review: bool = False, diagnostics: bool = False,
           python_checkers: str | None = None) -> str:
    if count < 1 or count > 100:
        raise ValueError("Variants must be between 1 and 100")
    safe_id = html.escape(identifier, quote=True)
    try:
        questions = import_xml(path, python_checkers=python_checkers)
        matches = [q for q in questions if q["name"] == question_name]
        if len(matches) != 1:
            raise UnsupportedQuestion(question_name, "name", f"expected exactly one question, found {len(matches)}")
        question = matches[0]
        variants = [instantiate(question, seed + offset) for offset in range(count)]
        from .checkers import preflight
        preflight(question, variants)
        data = {"version": 1, "id": identifier, "question": question,
                "variants": variants, "review": review}
        choices = "".join(f'<option value="{index}">Variant {index + 1}</option>' for index in range(count))
        first = variants[0]
        return (f'<section class="stack-sympy" data-stack-id="{safe_id}">'
                f'<div class="stack-toolbar"><label>Variant '
                f'<select class="stack-variant" aria-label="Question variant">{choices}</select></label></div>'
                f'<div class="stack-prompt stack-question">{first["question_html"]}</div>'
                f'<div class="stack-actions"><button type="button" class="stack-validate">Validate answers</button>'
                f'<button type="button" class="stack-check" disabled>Check answer</button>'
                + ('<button type="button" class="stack-tests">Run question tests</button>' if review else '')
                + '</div><div class="stack-result" aria-live="polite"></div>'
                + '<div class="stack-generalfeedback" hidden></div>'
                + f'<script type="application/json" class="stack-sympy-data">{_json_script(data)}</script></section>')
    except (UnsupportedQuestion, ValueError, OSError) as exc:
        if not diagnostics:
            raise
        return (f'<section class="stack-sympy stack-diagnostic" data-stack-id="{safe_id}">'
                f'<strong>Unsupported STACK question</strong><p>{html.escape(str(exc))}</p></section>')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render native STACK XML as a Quarto question")
    sub = parser.add_subparsers(dest="command", required=True)
    render_parser = sub.add_parser("render", help="Emit one question as an HTML fragment")
    render_parser.add_argument("--file", required=True)
    render_parser.add_argument("--question", required=True)
    render_parser.add_argument("--id", required=True)
    render_parser.add_argument("--variants", type=int, default=3)
    render_parser.add_argument("--seed", type=int, default=1)
    render_parser.add_argument("--review", action="store_true")
    render_parser.add_argument("--diagnostics", action="store_true")
    render_parser.add_argument("--errors-to-stdout", action="store_true", help="Include errors in pandoc.pipe output")
    test_parser = sub.add_parser("test", help="Run XML author tests against frozen seeds")
    test_parser.add_argument("--file", required=True)
    test_parser.add_argument("--question")
    test_parser.add_argument("--seed", type=int, action="append")
    render_parser.add_argument("--python-checkers", help="Trusted author checker source (embedded in the public card)")
    test_parser.add_argument("--python-checkers", help="Trusted author checker source")
    args = parser.parse_args(argv)
    if args.command == "render":
        try:
            sys.stdout.write(render(args.file, args.question, args.id, args.variants,
                                    args.seed, args.review, args.diagnostics, args.python_checkers))
            return 0
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            if args.errors_to_stdout:
                print(str(exc), file=sys.stdout)
            return 2
    if args.command == "test":
        try:
            questions = import_xml(args.file, python_checkers=args.python_checkers)
            if args.question:
                questions = [q for q in questions if q["name"] == args.question]
                if len(questions) != 1:
                    raise ValueError(f"Expected one question named {args.question!r}")
            from .checkers import preflight
            results = []
            for q in questions:
                variants = [instantiate(q, seed) for seed in (args.seed or [1])]
                preflight(q, variants)
                results.append({"question": q["name"], **run_question_tests(q, variants=variants)})
            sys.stdout.write(json.dumps({"passed": all(r["passed"] for r in results), "questions": results}, indent=2) + "\n")
            return 0 if all(r["passed"] for r in results) else 1
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
