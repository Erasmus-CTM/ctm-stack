"""Exercise the actual Quarto filter, CLI and copied browser assets."""
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

from rendered_html import Document


ROOT = Path(__file__).resolve().parents[1]
QUESTION = ROOT / "questions/polynomial-expansion.xml"


@cache
def render_site(project: Path = ROOT) -> Path:
    quarto = os.environ.get("QUARTO", "quarto")
    env = os.environ.copy()
    extension = project / "_extensions/stack-sympy"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(extension), env.get("PYTHONPATH", "")]))
    result = subprocess.run([quarto, "render"], cwd=project, env=env,
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
        for sibling in ("worker.js", "runtime-sources.js", "vendor/pyodide-runtime.js",
                        "vendor/matrix-input-provenance.json"):
            assert (asset.parent / sibling).is_file(), sibling
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
        assert "STACK_SYMPY_SOURCES" in (asset.parent / "runtime-sources.js").read_text()
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
    return re.findall(r'^```\{[^\n}]*\.stack-question[^\n}]*\}\n.*?\n```', qmd.read_text(), re.M | re.S)


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
            assert xml.text == (qmd.parent / path).read_text()
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
    assert len(doc.find("script", "stack-sympy-data")) == len(passing)
    assert not doc.find(css_class="stack-diagnostic")
    panels = doc.find("details", "stack-source")
    assert len(panels) == 2 * len(passing)
    assert all("open" not in panel.attrs for panel in panels)
    rendered_xml = [code.text for panel in panels for code in panel.find("code", "language-xml")]
    assert len(rendered_xml) == len(passing)
    for entry, source in zip(passing, rendered_xml):
        assert source == (ROOT / teaching_source(entry)[0]).read_text()
    for entry in entries:
        assert f'id="{entry["id"]}"' in output
        assert f'questions/corpus/{entry["file"]}' in output
        assert html.escape(entry["source_url"], quote=True) in output
        assert (render_site() / "questions/corpus" / entry["file"]).is_file()
    assert "CC BY-SA 4.0" in output
    assert (render_site() / "questions/corpus/manifest.json").is_file()
    assert (render_site() / "questions/corpus/baseline.json").is_file()


def test_unsupported_question_stops_quarto_build():
    # An independent project avoids mutating the built site's website cache.
    with tempfile.TemporaryDirectory(dir=ROOT, prefix="invalid_stack_") as temporary:
        project = Path(temporary)
        (project / "_extensions").symlink_to(ROOT / "_extensions", target_is_directory=True)
        (project / "_quarto.yml").write_text("project:\n  type: default\nfilters:\n  - stack-sympy\n")
        (project / "test.qmd").write_text("```{.stack-question}\n#| file: missing.xml\n"
                                           "#| question: Missing\n```\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "_extensions/stack-sympy"), env.get("PYTHONPATH", "")]))
        result = subprocess.run([os.environ.get("QUARTO", "quarto"), "render"],
                                cwd=project, env=env, text=True, capture_output=True, timeout=60)
        assert result.returncode != 0, "unsupported XML silently rendered"
        assert "could not render missing.xml / Missing" in result.stdout + result.stderr, (
            result.stdout + "\n" + result.stderr)


def _fixture_render(source: str, *, shared: str | None = None,
                    filters: tuple[str, ...] = ("stack-sympy",),
                    files: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess, str]:
    with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix="stack_feedback_render_") as temporary:
        project = Path(temporary)
        ext = project / "_extensions"
        ext.mkdir()
        shutil.copytree(ROOT / "_extensions/stack-sympy", ext / "stack-sympy")
        if shared:
            installed = ROOT / "_extensions/ai-feedback"
            assert installed.exists(), "install the shared AI Feedback extension before testing enabled cards"
            target = ext / "ai-feedback" if shared == "flat" else ext / "Erasmus-CTM/ai-feedback"
            target.parent.mkdir(exist_ok=True)
            shutil.copytree(installed, target)
        (project / "_quarto.yml").write_text(
            "project:\n  type: default\n" + ("filters:\n" + "".join(
                f"  - {name}\n" for name in filters) if filters else "filters: []\n"))
        (project / "test.qmd").write_text(source)
        for name, content in (files or {}).items():
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "_extensions/stack-sympy"), env.get("PYTHONPATH", "")]))
        result = subprocess.run([os.environ.get("QUARTO", "quarto"), "render"], cwd=project,
                                env=env, text=True, capture_output=True, timeout=90)
        output = (project / "test.html").read_text() if (project / "test.html").exists() else ""
        return result, output


@cache
def render_report_shell(name):
    """Render the actual report page instead of slicing its HTML at a marker."""
    result, output = _fixture_render(
        (ROOT / "compliance-report" / f"{name}.qmd").read_text(), filters=())
    assert result.returncode == 0, result.stdout + result.stderr
    return output


def _card(feedback: str = "", extra: str = "") -> str:
    return ("```{.stack-question}\n"
            f"#| file: {QUESTION}\n"
            "#| question: Expand a product (form-sensitive)\n"
            f"{feedback}{extra}```\n")


def _feedback_cards(output: str) -> list[dict]:
    return [json.loads(html.unescape(encoded)) for encoded in
            re.findall(r'data-stack-feedback="([^"]+)"', output)]


def test_feedback_is_optional_and_missing_dependency_errors_only_when_enabled():
    result, output = _fixture_render("# Question\n\n" + _card())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "data-stack-feedback" not in output
    assert "feedback-core.js" not in output
    result, _ = _fixture_render("# Question\n\n" + _card("#| feedback: true\n"))
    assert result.returncode != 0
    assert "Run: quarto add Erasmus-CTM/ai-feedback" in result.stdout + result.stderr


def test_shared_feedback_context_and_policy_are_emitted_once_per_page():
    source = ("---\nlang: de\n---\n"
              "# Exercise\n\nImplicit lesson context before the card.\n\n"
              "::: {.callout-note .ai-feedback-ignore}\nConfidential example answer in hidden callout.\n:::\n\n"
              + _card("#| feedback: true\n", "#| feedback-language: es\n")
              + "\n::: {#explanation .ai-context}\nUse $x^2$ in this explicit context.\n:::\n\n"
              + _card("#| feedback: true\n", "#| context: explanation\n#| label: policy-key\n")
              + "\n" + _card("#| feedback: true\n", "#| context: none\n"))
    for location, filters in (("flat", ("stack-sympy",)),
                              ("namespaced", ("stack-sympy", "ai-feedback")),
                              ("flat", ("ai-feedback", "stack-sympy"))):
        result, output = _fixture_render(source, shared=location, filters=filters)
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
    result, output = _fixture_render(source, shared="flat", files={"feedback/chapter.yml": policy})
    assert result.returncode == 0, result.stdout + result.stderr
    assert _feedback_cards(output)[0]["policySelection"] == {
        "exercise": "expansion-practice", "name": "short-hints"}
    assert "short-hints" in output  # shared policy payload is emitted on the page
    result, _ = _fixture_render(source.replace("short-hints", "missing"), shared="flat",
                                files={"feedback/chapter.yml": policy})
    assert result.returncode != 0
    assert "unknown feedback-policy missing" in result.stdout + result.stderr


def test_feedback_rejects_an_older_shared_extension():
    metadata = (ROOT / "_extensions/ai-feedback/_extension.yml").read_text()
    result, _ = _fixture_render(_card("#| feedback: true\n"), shared="flat", files={
        "_extensions/ai-feedback/_extension.yml": re.sub(r"(?m)^version:.*$", "version: 0.6.0", metadata)})
    assert result.returncode != 0
    assert "requires ai-feedback 0.8.0 or later" in result.stdout + result.stderr


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
    result, _ = _fixture_render(source, shared="flat", files={"invalid.yml": "ai-feedback:\n  " + policy + "\n"})
    assert result.returncode != 0
    assert diagnostic in result.stdout + result.stderr
