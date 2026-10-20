"""Exercise the actual Quarto filter, CLI and copied browser assets.

The site builds against CTM Assessment's parts (tests/ctm_parts.py): ctm-libs
and ctm-checkers installed in this repository (or named by
CTM_LIBS_EXTENSION / CTM_CHECKERS_EXTENSION), as a component development
build (CTM_COMPONENT_DEV=1); questions/ is ctm-checkers' examples/stack
(scripts/fetch-examples.py, Quarto's pre-render).
"""
from __future__ import annotations

from functools import cache
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import pytest

import ctm_parts
from rendered_html import Document


ROOT = Path(__file__).resolve().parents[1]
QUESTION = ROOT / "questions/polynomial-expansion.xml"


@cache
def render_site(project: Path = ROOT) -> Path:
    quarto = os.environ.get("QUARTO", "quarto")
    result = subprocess.run([quarto, "render"], cwd=project, env=ctm_parts.render_env(),
                            text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return project / "_site"


def test_project_renders_cards_and_deployable_assets():
    site = render_site()
    total = 0
    for qmd in question_pages():
        page = site / qmd.relative_to(ROOT).with_suffix(".html")
        doc = Document(page.read_text())
        authored = question_blocks(qmd)
        cards = doc.find(css_class="stack-sympy")
        assert len(cards) == len(authored), qmd
        assert not doc.find(css_class="stack-diagnostic"), qmd
        total += len(cards)
        for card in cards:
            payloads = list(card.find("script", "stack-sympy-data"))
            assert len(payloads) == 1
            assert json.loads(payloads[0].text)["question"]["name"]
        scripts = [node.attrs["src"].split("?", 1)[0] for node in doc.find("script")
                   if "stack-sympy.js" in node.attrs.get("src", "")]
        assert len(scripts) == 1, qmd
        asset = page.parent / scripts[0]
        assert asset.is_file(), asset
        for sibling in ("worker.js",):
            assert (asset.parent / sibling).is_file(), sibling
        # The grader's Python: ctm-libs' runtime and ctm-checkers' page scripts
        # with the STACK engine, in the head (the worker loads them by URL),
        # each with the wheel it installs.
        head_scripts = [Path(node.attrs["src"].split("?", 1)[0]).name for node in doc.find("script")
                        if node.attrs.get("src")]
        for script in ("pyodide-runtime.js", "ctm-checkers.js", "ctm-checkers-stack.js"):
            assert head_scripts.count(script) == 1, (qmd, script)
        assert head_scripts.index("ctm-checkers.js") < head_scripts.index("ctm-checkers-stack.js")
        assert head_scripts.index("ctm-checkers-stack.js") < head_scripts.index("stack-sympy.js")
        # Quarto may flatten registered scripts/stylesheets. Follow the HTML
        # references rather than assuming dependency-resource paths for them.
        page_scripts = [node.attrs['src'].split('?', 1)[0] for node in doc.find('script')
                        if node.attrs.get('src')]
        editor_scripts = [src for src in page_scripts if Path(src).name == 'matrix-input.js']
        editor_styles = [node.attrs['href'].split('?', 1)[0] for node in doc.find('link')
                         if Path(node.attrs.get('href', '').split('?', 1)[0]).name == 'matrix-input.css']
        assert len(editor_scripts) == len(editor_styles) == 1
        assert page_scripts.index(editor_scripts[0]) < page_scripts.index(scripts[0])
        for reference in editor_scripts + editor_styles:
            deployed = page.parent / reference
            pinned = ROOT / '_extensions/stack-sympy/vendor' / Path(reference).name
            assert deployed.is_file(), deployed
            assert deployed.read_bytes() == pinned.read_bytes(), deployed
    assert total > 0, "the published site should demonstrate at least one question"


def test_vendored_matrix_editor_matches_audited_source_manifest():
    import hashlib
    vendor = ROOT / '_extensions/stack-sympy/vendor'
    manifest = json.loads((vendor / 'matrix-input-provenance.json').read_text())
    assert manifest['commit'] == 'f238da6d9a43d58d1fdf9ad592ac6223225268e0'
    assert manifest['license'] == 'AGPL-3.0-or-later'
    for record in manifest['files']:
        assert hashlib.sha256((vendor / record['file']).read_bytes()).hexdigest() == record['sha256']
        assert '/' + manifest['commit'] + '/' in record['source']


def question_blocks(qmd):
    # A displayed Markdown example may contain a question fence inside a longer
    # outer fence. Only top-level question fences produce live cards.
    blocks, current = [], []
    fence, question = None, False
    for line in qmd.read_text().splitlines():
        if fence is None:
            opening = re.fullmatch(r' {0,3}(`{3,}|~{3,})(.*)', line)
            if opening:
                fence = opening[1]
                question = bool(re.fullmatch(r'\{[^}]*\.stack-question[^}]*\}', opening[2].strip()))
                current = [line]
        else:
            current.append(line)
            closing = line.strip()
            if len(closing) >= len(fence) and set(closing) == {fence[0]}:
                if question:
                    blocks.append('\n'.join(current))
                fence = None
    return blocks


def question_pages():
    # Editorial pages may add, remove, reorder or move cards between sections.
    site = render_site()
    sources = [ROOT / page.relative_to(site).with_suffix(".qmd")
               for page in site.rglob("*.html")]
    return sorted(qmd for qmd in sources if qmd.is_file() and question_blocks(qmd))


def test_rendered_questions_show_authored_block_and_original_xml():
    site = render_site()
    for qmd in question_pages():
        doc = Document((site / qmd.relative_to(ROOT).with_suffix(".html")).read_text())
        groups = doc.find(css_class="stack-question-group")
        authored = question_blocks(qmd)
        assert len(groups) == len(authored)
        for group, block in zip(groups, authored):
            panels = list(group.find("details", "stack-source"))
            assert len(panels) == 2
            codes = [list(panel.find("code"))[0] for panel in panels]
            by_language = {code.attrs["class"]: code for code in codes}
            # Pandoc normalizes fence attributes; their order is not content.
            source = by_language["language-markdown"].text
            assert source.split("\n", 1)[1] == block.split("\n", 1)[1]
            assert set(re.findall(r'[#.][\w-]+', source.split("\n", 1)[0])) == set(
                re.findall(r'[#.][\w-]+', block.split("\n", 1)[0]))
            path = re.search(r"^#\| file: (.+)$", block, re.M).group(1)
            xml = by_language["language-xml"]
            # Pandoc code blocks add a terminal newline and may retain an
            # additional blank line already present in the source export.
            # Only display-terminal LF is normalized; all other content must
            # agree. Corpus byte provenance is checked independently by SHA.
            assert xml.text.rstrip("\n") == (qmd.parent / path).read_text().rstrip("\n"), path
            assert not list(xml.find("quiz")), "XML should be escaped as code"


def test_corpus_page_tracks_manifest_baseline_and_only_passing_cards():
    from scripts.generate_corpus_page import generate, teaching_source

    manifest = json.loads((ROOT / "questions/corpus/manifest.json").read_text())
    baseline = json.loads((ROOT / "questions/corpus/baseline.json").read_text())
    entries = manifest["questions"]
    reports = {row["id"]: row for row in baseline["questions"]}
    authored = (ROOT / "corpus.qmd").read_text()
    assert authored == generate(), "regenerate with python scripts/generate_corpus_page.py"
    output = (render_site() / "corpus.html").read_text()
    doc = Document(output)
    assert any(re.search(r'(?:^|/)corpus\.html$', a.attrs.get("href", ""))
               for nav in doc.find("nav") for a in nav.find("a"))
    assert {entry["id"] for entry in entries} == reports.keys()
    passing = [entry for entry in entries if reports[entry["id"]]["status"] == "qtests_pass"]
    # One markup-only teaching derivative is deliberately separate from the
    # unchanged-export baseline, where its original remains unsupported.
    assert len(doc.find("script", "stack-sympy-data")) == len(passing) + 1
    assert not doc.find(css_class="stack-diagnostic")
    panels = doc.find("details", "stack-source")
    assert len(panels) == 2 * (len(passing) + 1)
    assert all("open" not in panel.attrs for panel in panels)
    rendered_xml = [code.text for panel in panels for code in panel.find("code", "language-xml")]
    assert len(rendered_xml) == len(passing) + 1
    matrix_copy = ROOT / "questions/corrected/7-3-26-(Write-sim-eqns-with-matrices).xml"
    assert rendered_xml[0].rstrip("\n") == matrix_copy.read_text().rstrip("\n")
    for entry, source in zip(passing, rendered_xml[1:]):
        assert source.rstrip("\n") == (ROOT / teaching_source(entry)[0]).read_text().rstrip("\n"), entry["file"]
    for entry in entries:
        assert f'id="{entry["id"]}"' in output
        assert f'questions/corpus/{entry["file"]}' in output
        assert (render_site() / "questions/corpus" / entry["file"]).is_file()
    assert "CC BY-SA 4.0" in output
    assert 'id="sources"' in output
    assert (render_site() / "questions/corpus/manifest.json").is_file()
    assert (render_site() / "questions/corpus/baseline.json").is_file()


def test_unsupported_question_stops_quarto_build():
    # An independent project avoids mutating the built site's website cache.
    with tempfile.TemporaryDirectory(dir=ROOT, prefix="invalid_stack_") as temporary:
        project = Path(temporary)
        shutil.copytree(ROOT / "_extensions/stack-sympy", project / "_extensions/stack-sympy")
        ctm_parts.install(project)
        (project / "_quarto.yml").write_text("project:\n  type: default\nfilters:\n  - stack-sympy\n")
        (project / "test.qmd").write_text("```{.stack-question}\n#| file: missing.xml\n"
                                           "#| question: Missing\n```\n")
        result = subprocess.run([os.environ.get("QUARTO", "quarto"), "render"],
                                cwd=project, env=ctm_parts.render_env(), text=True, capture_output=True, timeout=60)
        assert result.returncode != 0, "unsupported XML silently rendered"
        assert "could not render missing.xml / Missing" in result.stdout + result.stderr, (
            result.stdout + "\n" + result.stderr)


def _fixture_render(source: str, *, parts: bool = True, checkers: bool = True, owner: str = "",
                    filters: tuple[str, ...] = ("stack-sympy",),
                    files: dict[str, str | None] | None = None,
                    env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess, str]:
    """Renders test.qmd in a project with stack-sympy and (`parts`) ctm-libs and
    (`checkers`) ctm-checkers, flat or under an `owner` folder as `quarto add` installs them;
    `files` are written last, so they can replace installed files."""
    with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix="stack_feedback_render_") as temporary:
        project = Path(temporary)
        ext = project / "_extensions"
        ext.mkdir()
        shutil.copytree(ROOT / "_extensions/stack-sympy", ext / owner / "stack-sympy")
        if parts:
            ctm_parts.install(project, owner, checkers=checkers)
        (project / "_quarto.yml").write_text(
            "project:\n  type: default\n" + ("filters:\n" + "".join(
                f"  - {name}\n" for name in filters) if filters else "filters: []\n"))
        (project / "test.qmd").write_text(source)
        for name, content in (files or {}).items():
            destination = project / name
            if content is None:
                destination.unlink()
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        result = subprocess.run([os.environ.get("QUARTO", "quarto"), "render"], cwd=project,
                                env=env or ctm_parts.render_env(), text=True, capture_output=True, timeout=90)
        output = (project / "test.html").read_text() if (project / "test.html").exists() else ""
        return result, output


def _card(feedback: str = "", extra: str = "") -> str:
    return ("```{.stack-question}\n"
            f"#| file: {QUESTION}\n"
            "#| question: Expand a product (form-sensitive)\n"
            f"{feedback}{extra}```\n")


def _feedback_cards(output: str) -> list[dict]:
    return [json.loads(html.unescape(encoded)) for encoded in
            re.findall(r'data-stack-feedback="([^"]+)"', output)]


INSTALL = "quarto add https://erasmus-ctm.github.io/ctm-assessment/ctm-assessment.tar.gz"


def test_feedback_is_optional():
    result, output = _fixture_render("# Question\n\n" + _card())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "data-stack-feedback" not in output
    assert "feedback-core.js" not in output
    assert output.count("ctm-checkers-stack.js") == 1


def test_feedback_cards_in_a_build_without_ai():
    # CTM_FEEDBACK=off: no AI feedback on the page; the card works without it
    # (stack-sympy.js adds no Feedback button when AIFeedback is missing).
    result, output = _fixture_render("# Question\n\n" + _card("#| feedback: true\n"),
                                     env={**ctm_parts.render_env(), "CTM_FEEDBACK": "off"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "feedback-core.js" not in output
    assert output.count("ctm-checkers-stack.js") == 1


def test_missing_ctm_assessment_stops_the_render_with_the_install_command():
    # stack-sympy is part of CTM Assessment: without the package (and outside a
    # component development build), or without ctm-libs, the bootstrap stops.
    production = {key: value for key, value in os.environ.items() if key != "CTM_COMPONENT_DEV"}
    result, _ = _fixture_render("# Question\n\n" + _card(), env=production)
    assert result.returncode != 0
    assert "stack-sympy is part of CTM Assessment, which is not installed" in result.stdout + result.stderr
    assert INSTALL in result.stdout + result.stderr
    result, _ = _fixture_render("# Question\n\n" + _card(), parts=False)
    assert result.returncode != 0
    assert "needs its library ctm-libs, which is not installed" in result.stdout + result.stderr
    # ctm-libs without ctm-checkers, the STACK engine's home.
    result, _ = _fixture_render("# Question\n\n" + _card(), checkers=False)
    assert result.returncode != 0
    assert "needs ctm-checkers, the checker library of CTM Assessment" in result.stdout + result.stderr


def test_an_older_ctm_assessment_stops_the_render_with_the_update_command():
    # A ctm-libs from before ctm.checkers (consolidation step 2).
    result, _ = _fixture_render("# Question\n\n" + _card(), files={"_extensions/ctm-libs/lua/checkers.lua": None})
    assert result.returncode != 0
    assert "needs ctm-checkers, which the ctm-libs in" in result.stdout + result.stderr
    assert "Update CTM Assessment: " + INSTALL in result.stdout + result.stderr
    # A ctm-checkers without the STACK engine (0.1).
    manifest = json.loads((ctm_parts.CTM_CHECKERS / "checkers.json").read_text())
    del manifest["parts"]
    result, _ = _fixture_render("# Question\n\n" + _card(), files={
        "_extensions/ctm-checkers/checkers.json": json.dumps(manifest)})
    assert result.returncode != 0
    assert "has no stack part (it comes with ctm-checkers 0.2)" in result.stdout + result.stderr


def test_shared_feedback_context_and_policy_are_emitted_once_per_page():
    source = ("---\nlang: de\n---\n"
              "# Exercise\n\nImplicit lesson context before the card.\n\n"
              "::: {.callout-note .ai-feedback-ignore}\nConfidential example answer in hidden callout.\n:::\n\n"
              + _card("#| feedback: true\n", "#| feedback-language: es\n")
              + "\n::: {#explanation .ai-context}\nUse $x^2$ in this explicit context.\n:::\n\n"
              + _card("#| feedback: true\n", "#| context: explanation\n#| label: policy-key\n")
              + "\n" + _card("#| feedback: true\n", "#| context: none\n"))
    # Flat or under an owner folder; alone, or after ctm-libs' own filter (as
    # the CTM Assessment package lists it), whose preparation stack-sympy repeats.
    for owner, filters in (("", ("stack-sympy",)),
                           ("Erasmus-CTM", ("stack-sympy",)),
                           ("", ("ctm-libs", "stack-sympy"))):
        result, output = _fixture_render(source, owner=owner, filters=filters)
        assert result.returncode == 0, result.stdout + result.stderr
        cards = _feedback_cards(output)
        assert len(cards) == 3
        assert output.count('feedback-core.js') == 1
        assert cards[0]["context"]["mode"] == "auto"
        assert "Implicit lesson context" in cards[0]["context"]["text"]
        assert "Confidential example answer" not in cards[0]["context"]["text"]
        assert cards[0]["language"] == "es"
        assert cards[0]["uiLanguage"] == "de"
        assert cards[1]["context"]["mode"] == "explicit"
        assert cards[1]["context"]["refs"] == "explanation"
        assert cards[1]["policySelection"]["exercise"] == "policy-key"
        assert cards[2]["context"]["mode"] == "none"
        assert "ai-feedback-ignore" in output
        assert "data-ai-feedback-context=&quot;" not in output
        assert "data-stack-feedback&quot;" not in output  # source panes are authored only


def test_named_policy_uses_shared_yaml_selection():
    source = ("---\nai-feedback:\n  page-policy-files: feedback/chapter.yml\n---\n"
              + _card("#| feedback: true\n", "#| label: expansion-practice\n#| feedback-policy: short-hints\n"))
    policy = ("ai-feedback:\n  policies:\n    course:\n"
              "      base-prompt: Preserve the course notation.\n"
              "      max-words: 120\n    short-hints:\n"
              "      extends: course\n      steps:\n"
              "        - step-prompt: Ask for the next step.\n")
    result, output = _fixture_render(source, files={"feedback/chapter.yml": policy})
    assert result.returncode == 0, result.stdout + result.stderr
    assert _feedback_cards(output)[0]["policySelection"] == {
        "exercise": "expansion-practice", "name": "short-hints"}
    assert "short-hints" in output  # shared policy payload is emitted on the page
    result, _ = _fixture_render(source.replace("short-hints", "missing"),
                                files={"feedback/chapter.yml": policy})
    assert result.returncode != 0
    assert "unknown feedback-policy missing" in result.stdout + result.stderr


@pytest.mark.parametrize("policy, diagnostic", [
    ("policies:\n    old:\n      prompt: Ask a question.", "base-prompt"),
    ("policies:\n    old:\n      steps:\n        - prompt: Ask a question.", "step-prompt"),
    ("integrations:\n    math-exercise:\n      max-words: 80", "only define policies"),
    ("policies:\n    child:\n      extends: missing", "Unknown parent"),
    ("policies:\n    a:\n      extends: b\n    b:\n      extends: a", "Circular"),
])
def test_invalid_shared_policies_stop_rendering(policy, diagnostic):
    source = ("---\nai-feedback:\n  page-policy-files: invalid.yml\n---\n"
              + _card("#| feedback: true\n"))
    result, _ = _fixture_render(source, files={"invalid.yml": "ai-feedback:\n  " + policy + "\n"})
    assert result.returncode != 0
    assert diagnostic in result.stdout + result.stderr
