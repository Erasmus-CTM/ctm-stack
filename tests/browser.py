"""Full browser integration through Quarto HTML, Worker, Pyodide and SymPy."""
from __future__ import annotations

from contextlib import contextmanager
from fractions import Fraction
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
from threading import Thread

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from test_render import ROOT, question_pages, render_site
from ctm_parts import engine_data


def card_data(card):
    try:
        card.page.wait_for_function("element => !!element.dataset.stackVariantId",arg=card.element_handle())
    except PlaywrightTimeoutError:
        # A card that never renders a variant means its initialization threw; name the page errors.
        raise AssertionError(f"card {card.get_attribute('data-stack-id')} has no variant; page errors: {getattr(card.page, 'ctm_errors', 'not collected')}")
    payload=json.loads(card.locator('.ctm-stack-data').text_content())
    current=card.get_attribute('data-stack-variant-id')
    payload['variants'].sort(key=lambda v:v['id']!=current)
    return engine_data(payload)


def correct_expansion(card):
    return card_data(card)['variants'][0]['env']['ta']


def next_variant(card):
    card.page.once('dialog',lambda dialog:dialog.accept())
    card.locator('.stack-new-variant').click()


CORPUS = Path(__file__).resolve().parents[1] / "questions/corpus"


def test_browser_python_checker_source_parity_feedback_and_card_isolation(browser_site):
    """Author source executes in real Pyodide, separately for each card/call."""
    from ctm_checkers.stack.engine import run_question_tests
    with serve(browser_site) as url, sync_playwright() as pw:
        options = {"headless": True}
        if os.getenv("CTM_STACK_BROWSER", "chromium") == "chromium" and os.environ.get("STACK_SYMPY_CHROMIUM"):
            options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = getattr(pw, os.getenv('CTM_STACK_BROWSER', 'chromium')).launch(**options)
        try:
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url + '/custom.html', wait_until='domcontentloaded')
            card = page.locator('[data-stack-id="custom-multiple"]')
            other = page.locator('[data-stack-id="custom-other"]')
            payload = card_data(card)
            assert 'python_checkers' not in payload['question']
            assert 'def check(response, symbols):' in payload['question']['checker']
            assert payload['question']['checker_value'] == 1
            divisor = int(payload['variants'][0]['env']['d'])
            other_divisor=int(card_data(other)['variants'][0]['env']['d'])

            def check(item, answer, state):
                item.locator('.stack-answer').fill(str(answer))
                item.locator('.stack-validate').click()
                item.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                item.locator('.stack-check').click()
                item.locator(f'.stack-result[data-state="{state}"]').wait_for(timeout=180000)

            check(card, divisor * 3, 'correct')
            check(card, 'x', 'invalid')
            assert 'Enter an integer value.' in card.inner_text()
            assert card.locator('.stack-answer').get_attribute('aria-invalid') == 'true'
            check(other, other_divisor + 1, 'correct')
            assert '<b>Literal custom diagnostic</b>' in other.inner_text()
            assert other.locator('.stack-prt-feedback b, .stack-feedback b').count() == 0
            check(card, divisor + 1, 'retry')
            check(other, other_divisor + 1, 'correct')  # fresh module globals on every call
            check(card, divisor * 2, 'correct')
            card.locator('.stack-tests').click()
            card.locator('.stack-result[data-state="correct"]').wait_for(timeout=180000)
            assert 'All question tests passed' in card.inner_text()
            # Independently compare complete qtest results, not only UI labels.
            actual = page.evaluate(r"""async payload => {
              const descriptor = JSON.parse(document.querySelector('.ctm-stack-backend').textContent);
              const script = [...document.scripts].find(x => /\/ctm-stack-[^/]+\/ctm-stack.js/.test(x.src));
              await MathExerciseRuntime.loadScript(new URL(descriptor.adapter, script.src).href);
              const adapter = CTMStackAdapters[descriptor.id](descriptor);
              await adapter.start();
              return await adapter.request({type:'tests',question:payload.question,variant:payload.variants[0],answers:{}});
            }""", payload)
            assert actual['ok'], actual
            expected = run_question_tests(payload['question'], variants=[payload['variants'][0]])
            assert actual['result'] == expected
            # Custom source and diagnostics must not enter optional AI hints.
            card.locator('.stack-feedback-button').click()
            prompt = card.locator('.ai-feedback-prompt').inner_text()
            for forbidden in ('CHECKERS', 'def check(', 'python_checkers',
                              'Enter an integer value.', 'positive integer multiple of the given number.'):
                assert forbidden not in prompt
            card.locator('.stack-answer').fill('1')
            assert card.locator('.stack-check').is_disabled()
            card.locator('.stack-reset').click()
            assert card.locator('.stack-answer').input_value() == ''
            next_variant(card)
            assert card.locator('.stack-answer').input_value() == ''
            spd = page.locator('[data-stack-id="custom-spd"]')
            cells = spd.locator('input[data-matrix-row]')
            for values, state in (([2, 1, 1, 2], 'correct'),
                                  ([-1, 0, 0, -1], 'retry'),
                                  ([2, 1, 0, 2], 'retry'),
                                  ([2, '%i', '-%i', 2], 'correct'),
                                  ([1, '%i', '%i', 1], 'retry')):
                for cell, value in zip(cells.all(), values):
                    cell.fill(str(value))
                spd.locator('.stack-validate').click()
                spd.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                spd.locator('.stack-check').click()
                spd.locator(f'.stack-result[data-state="{state}"]').wait_for(timeout=180000)
            spd.locator('.stack-tests').click()
            spd.locator('.stack-result[data-state="correct"]').wait_for(timeout=180000)
            assert 'All question tests passed' in spd.inner_text()
            separate = page.locator('[data-stack-id="custom-spd-prt"]')
            cells = separate.locator('input[data-matrix-row]')
            for values, state in (([2, 1, 1, 2], 'correct'),
                                  ([1, 2, 2, 1], 'retry'),
                                  ([2, 1, 0, 2], 'retry'),
                                  ([0, 1, 0, 0], 'retry'),
                                  ([2, '%i', '-%i', 2], 'correct'),
                                  ([1, '%i', '%i', 1], 'retry')):
                for cell, value in zip(cells.all(), values):
                    cell.fill(str(value))
                separate.locator('.stack-validate').click()
                separate.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                separate.locator('.stack-check').click()
                separate.locator(f'.stack-result[data-state="{state}"]').wait_for(timeout=180000)
                assert 'symmetr' in separate.inner_text().lower()
                assert 'positive' in separate.inner_text().lower()
            separate.locator('.stack-tests').click()
            separate.locator('.stack-result[data-state="correct"]').wait_for(timeout=180000)
            assert 'All question tests passed' in separate.inner_text()
            assert not errors, errors
        finally:
            browser.close()


def test_browser_python_basis_and_ordinary_matrix_questions(browser_site):
    """Actual bundled Python tests, alternate bases, colors and stale state."""
    with serve(browser_site) as url, sync_playwright() as pw:
        options = {"headless": True}
        if os.getenv("CTM_STACK_BROWSER", "chromium") == "chromium" and os.environ.get("STACK_SYMPY_CHROMIUM"):
            options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = getattr(pw, os.getenv('CTM_STACK_BROWSER', 'chromium')).launch(**options)
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url + "/bases.html", wait_until="domcontentloaded")
            card = page.locator('[data-stack-id="course-c-nullspace"]')
            host = card.locator(".stack-matrix")
            cells = host.locator("input[data-matrix-row]")

            def fill(values):
                assert cells.count() == len(values)
                for cell, value in zip(cells.all(), values):
                    cell.fill(str(value))

            def check(expected):
                card.locator(".stack-validate").click()
                card.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                # Validation has not assessed basis correctness.
                assert host.locator("input.math-input-ok, input.math-input-dependent, input.math-input-wrong").count() == 0
                card.locator(".stack-check").click()
                card.locator(f'.stack-result[data-state="{expected}"]').wait_for(timeout=180000)

            fill([-2, 1, 0])  # independent but incomplete
            check("retry")
            assert host.locator("input.math-input-ok").count() == 3
            assert "span" in card.locator(".stack-feedback").inner_text()
            assert "%" not in card.locator(".stack-verdict").inner_text()
            host.locator('[data-dynamic-action="add-col"]').click()
            assert host.locator("input.math-input-ok").count() == 0
            assert card.locator(".stack-check").is_disabled()
            fill([-2, -4, 1, 2, 0, 0])
            check("retry")
            assert host.locator("input.math-input-dependent").count() == 6
            fill([-2, 1, 1, 0, 0, 0])
            check("retry")
            assert host.locator("input.math-input-ok").count() == 3
            assert host.locator("input.math-input-wrong").count() == 3
            fill([-5, -1, 1, -1, 1, 1])  # a different, mixed basis
            check("correct")
            assert host.locator("input.math-input-ok").count() == 6
            cells.first.fill("x")
            assert host.locator("input.math-input-ok").count() == 0
            assert card.locator(".stack-result").inner_text() == ""
            card.locator(".stack-validate").click()
            card.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
            # The common parser accepts symbols; the supplied checker reports
            # its rational-entry domain when grading runs.
            card.locator(".stack-check").click()
            card.locator('.stack-result[data-state="invalid"]').wait_for(timeout=180000)
            assert "real integers or exact fractions" in card.inner_text()
            fill([-5, -1, 1, -1, 1, 1])
            card.locator(".stack-validate").click()
            card.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
            card.locator(".stack-check").click()
            cells.first.fill("0")  # discard a grading result after an edit
            page.wait_for_timeout(1000)
            assert card.locator(".stack-result").inner_text() == ""
            assert host.locator("input.math-input-ok").count() == 0
            card.locator(".stack-reset").click()
            assert cells.count() == 3
            assert cells.evaluate_all("xs => xs.map(x => x.value)") == ["", "", ""]
            for identifier in ("course-b-nullspace", "course-c-nullspace", "course-b-rank-pivots", "determinant-one"):
                item = page.locator(f'[data-stack-id="{identifier}"]')
                item.locator(".stack-tests").click()
                item.locator('.stack-result[data-state="correct"]').wait_for(timeout=180000)
                assert "All question tests passed" in item.locator(".stack-result").inner_text()
            determinant = page.locator('[data-stack-id="determinant-one"]')
            determinant_cells = determinant.locator("input[data-matrix-row]")
            for values, state in (([1, 0, 0, 1], "retry"), ([2, 1, 1, 1], "correct")):
                for cell, value in zip(determinant_cells.all(), values):
                    cell.fill(str(value))
                determinant.locator(".stack-validate").click()
                determinant.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                determinant.locator(".stack-check").click()
                determinant.locator(f'.stack-result[data-state="{state}"]').wait_for(timeout=180000)
            # A later input's invalid domain clears earlier vector colors too.
            pair = page.locator('[data-stack-id="matrix-pair"]')
            pair_cells = pair.locator('input[data-matrix-row]')
            for second, state in ((1, 'correct'), (-1, 'invalid')):
                pair_cells.nth(0).fill('1')
                pair_cells.nth(1).fill(str(second))
                pair.locator('.stack-validate').click()
                pair.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                pair.locator('.stack-check').click()
                pair.locator(f'.stack-result[data-state="{state}"]').wait_for(timeout=180000)
                assert pair.locator('input.math-input-ok').count() == (1 if second > 0 else 0)
            assert 'Enter a positive entry.' in pair.inner_text()
            assert pair_cells.nth(1).get_attribute('aria-invalid') == 'true'
            assert not errors, errors
        finally:
            browser.close()


def test_browser_bounded_matrix_editor_worker_and_stale_evidence(browser_site):
    """The vendored editor feeds raw cells to the real Worker/Pyodide grader."""
    with serve(browser_site) as url, sync_playwright() as pw:
        options = {"headless": True}
        if os.getenv("CTM_STACK_BROWSER", "chromium") == "chromium" and os.environ.get("STACK_SYMPY_CHROMIUM"):
            options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = getattr(pw, os.getenv('CTM_STACK_BROWSER', 'chromium')).launch(**options)
        try:
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url + '/matrices.html', wait_until='domcontentloaded')
            card = page.locator('[data-stack-id="bounded-matrices"]')
            host = card.locator('.stack-matrix')
            cells = host.locator('input[data-matrix-row]')
            assert cells.count() == 4
            control = host.locator('[data-dynamic-action="add-row"]')
            assert control.evaluate('(el) => parseFloat(getComputedStyle(el).paddingTop)') < 3
            assert host.evaluate('(el) => getComputedStyle(el).borderTopStyle') == 'none'
            payload = card_data(card)
            a = payload['variants'][0]['env']['a']

            def fill_correct():
                for cell, raw in zip(cells.all(), [str(a), 'x+x', '1/2', '1']):
                    cell.fill(raw)

            def validate():
                card.locator('.stack-validate').click()
                card.locator('.stack-result[data-state="valid"] .stack-verdict').wait_for(timeout=180000)

            def prompt():
                card.locator('.stack-feedback-button').click()
                text = card.locator('.ai-feedback-prompt').inner_text()
                return json.loads(text.split('\n\nUSER\n', 1)[1])

            fill_correct()
            assert cells.nth(1).input_value() == 'x+x'
            cells.first.fill('1),(2')
            card.locator('.stack-validate').click()
            card.locator('.stack-result[data-state="invalid"] .stack-verdict').wait_for(timeout=180000)
            assert cells.count() == 4
            fill_correct()
            validate()
            card.locator('.stack-check').click()
            card.locator('.stack-result[data-state="correct"] .stack-verdict').wait_for(timeout=180000)
            evidence = prompt()
            assert evidence['evidence']
            assert 'x+x' in evidence['responses'][0]['value']
            host.locator('[data-dynamic-action="add-row"]').click()
            assert cells.count() == 6
            assert cells.nth(1).input_value() == 'x+x'
            assert card.locator('.stack-check').is_disabled()
            assert card.locator('.stack-result').inner_text() == ''
            assert card.locator('.ai-feedback-output').inner_text() == ''
            assert prompt()['evidence'] == []
            card.locator('.stack-validate').click()
            card.locator('.stack-result[data-state="invalid"] .stack-verdict').wait_for(timeout=180000)
            assert card.locator('.stack-check').is_disabled()
            host.locator('[data-dynamic-action="remove-row"]').click()
            validate()
            card.locator('.stack-check').click()
            # An edit during grading must invalidate its eventual result.
            cells.first.fill('0.1')
            assert cells.first.input_value() == '0.1'
            assert card.locator('.stack-check').is_disabled()
            page.wait_for_timeout(1000)
            assert card.locator('.stack-result').inner_text() == ''
            assert prompt()['evidence'] == []

            card.locator('.stack-reset').click()
            assert cells.count() == 4
            assert cells.evaluate_all('(items) => items.map(item => item.value)') == ['', '', '', '']
            assert card.locator('.stack-result').inner_text() == ''
            assert card.locator('.stack-check').is_disabled()
            fill_correct()
            host.locator('[data-dynamic-action="add-col"]').click()
            assert cells.count() == 6
            page.evaluate("() => { window.savedMatrixInput = window.MatrixInput; window.MatrixInput = {create() { throw new Error('another extension editor'); }}; }")
            next_variant(card)
            page.evaluate('() => { window.MatrixInput = window.savedMatrixInput; delete window.savedMatrixInput; }')
            assert cells.count() == 4
            assert cells.evaluate_all('(items) => items.map(item => item.value)') == ['', '', '', '']
            assert card.locator('.ai-feedback-output').inner_text() == ''
            card.locator('.stack-tests').click()
            card.locator('.stack-result .stack-verdict').wait_for(timeout=180000)
            assert 'All question tests passed' in card.locator('.stack-result').inner_text()
            assert not errors, errors
        finally:
            browser.close()


@contextmanager
def serve(directory: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_browser_published_pages_mount_cards():
    """Smoke-test the real website without fixing its copy or example order."""
    site = render_site()
    with serve(site) as url, sync_playwright() as pw:
        options = {"headless": True}
        if os.getenv("CTM_STACK_BROWSER", "chromium") == "chromium" and os.environ.get("STACK_SYMPY_CHROMIUM"):
            options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = getattr(pw, os.getenv('CTM_STACK_BROWSER', 'chromium')).launch(**options)
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for qmd in question_pages():
                route = qmd.relative_to(ROOT).with_suffix(".html").as_posix()
                page.goto(f"{url}/{route}", wait_until="domcontentloaded")
                cards = page.locator(".ctm-stack")
                assert cards.count() > 0, route
                assert page.locator(".stack-diagnostic").count() == 0
                for card in cards.all():
                    card.locator(".stack-answer").first.wait_for()
                    assert card.locator(".stack-validate").count() == 1
                    assert card.locator(".stack-check").count() == 1
                    assert card.locator(".stack-check").is_disabled()
                    if card.get_attribute("data-stack-feedback"):
                        assert card.locator(".stack-feedback-button").count() == 1, (route, errors)
            assert not errors, errors
        finally:
            browser.close()


def test_browser_worker_grades_and_runs_authored_tests(browser_site):
    site = browser_site
    with serve(site) as url, sync_playwright() as pw:
        browser_options = {"headless": True}
        if os.getenv("CTM_STACK_BROWSER", "chromium") == "chromium" and os.environ.get("STACK_SYMPY_CHROMIUM"):
            browser_options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = getattr(pw, os.getenv('CTM_STACK_BROWSER', 'chromium')).launch(**browser_options)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url + "/index.html", wait_until="domcontentloaded")
        card = page.locator('[data-stack-id="expansion"]')
        assert card.count() == 1
        assert card.locator(".stack-answer").count() > 0
        card.locator(".stack-prompt mjx-container").first.wait_for(timeout=60000)

        # Exact tests from the imported XML must execute in the browser's
        # bundled Python engine, rather than a JavaScript imitation.
        card.locator(".stack-tests").click()
        card.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
        assert "All question tests passed" in card.locator(".stack-result").inner_text()

        card.locator(".stack-answer").first.fill("!!!")
        assert card.locator(".stack-check").is_disabled()
        card.locator(".stack-validate").click()
        card.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
        assert card.locator(".stack-result").get_attribute("data-state") == "invalid"
        assert card.locator(".stack-check").is_disabled()

        # S-01 (ctm-checkers 0.3.0): the teacher's answer variable is no answer,
        # alone or inside an expression; STACK's message, no preview.
        for answer in ("ta", "ta+0"):
            card.locator(".stack-answer").first.fill(answer)
            card.locator(".stack-validate").click()
            card.locator('.stack-validation[data-state="invalid"]').wait_for(timeout=120000)
            validation = card.locator(".stack-validation").first
            assert validation.inner_text() == "Forbidden variable or constant: ta.", answer
            assert not validation.get_attribute("data-latex"), answer
            assert card.locator(".stack-result").get_attribute("data-state") == "invalid"
            assert card.locator(".stack-check").is_disabled()

        # S-13 (ctm-checkers 0.6.0): STACK's rules for the text of an answer,
        # with STACK's messages; π is STACK's pi.
        for answer, message in (("sinx", "Forbidden variable or constant: sinx."),
                                ("x²+8x+15", "CAS commands may not contain the following characters: ²."),
                                ("x^2 + 8 x + 15", "Illegal spaces found in expression x^2+8_x+15."),
                                ("Sin(x)", "Input is case sensitive: Sin is an unknown function. Did you mean sin?")):
            card.locator(".stack-answer").first.fill(answer)
            card.locator(".stack-validate").click()
            card.locator('.stack-validation[data-state="invalid"]').wait_for(timeout=120000)
            validation = card.locator(".stack-validation").first
            assert validation.inner_text() == message, answer
            assert card.locator(".stack-check").is_disabled()
        card.locator(".stack-answer").first.fill("π")
        card.locator(".stack-validate").click()
        card.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
        assert card.locator(".stack-validation").first.get_attribute("data-latex") == r"\pi"

        # The demo opts into STACK's implied-multiplication input setting.
        # Validation must display the same polynomial without artificial
        # parentheses from the parser's left-associated addition tree.
        card.locator(".stack-answer").first.fill("x**2+8x+15")
        card.locator(".stack-validate").click()
        card.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
        preview = card.locator('.stack-validation').first
        preview.locator('mjx-container').first.wait_for(timeout=60000)
        assert preview.get_attribute('data-latex') == r'x^{2} + 8x + 15'
        card.locator('.stack-answer').first.fill(correct_expansion(card))
        card.locator('.stack-validate').click()
        card.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
        card.locator(".stack-check").click()
        card.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
        assert card.locator(".stack-result").get_attribute("data-state") == "correct"

        card.locator(".stack-answer").first.fill("x+x")
        card.locator(".stack-validate").click()
        card.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
        card.locator('.stack-validation mjx-container').first.wait_for(timeout=60000)
        assert card.locator('.stack-validation').first.get_attribute('data-latex') == 'x + x'
        assert card.locator(".stack-check").is_enabled()
        assert card.locator(".stack-result").get_attribute("data-state") == "valid"
        assert "score" not in card.locator(".stack-result").inner_text().lower()
        card.locator(".stack-check").click()
        card.locator(".stack-answer").first.fill("x+x+1")
        assert card.locator(".stack-check").is_disabled()
        page.wait_for_timeout(1000)  # old Worker result must not repaint the edited response
        assert card.locator(".stack-result").inner_text() == ""

        # A variant switch clears stale answers/results and updates CASText.
        next_variant(card)
        assert card.locator(".stack-answer").first.input_value() == ""
        assert card.locator(".stack-result").inner_text() == ""
        card.locator(".stack-prompt mjx-container").first.wait_for(timeout=60000)

        page.goto(url + "/examples.html", wait_until="domcontentloaded")
        cards = page.locator(".ctm-stack:not(.stack-diagnostic)")
        assert cards.count() > 0
        for index in range(cards.count()):
            example = cards.nth(index)
            assert example.locator(".stack-answer").count() > 0
            example.locator(".stack-tests").click()
            example.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
            assert "All question tests passed" in example.locator(".stack-result").inner_text(), index
        # Exercise held logic and new functions through validation and grading,
        # in addition to replaying their authored XML qtests above.
        for question_name, response, correct in (
            ("Hyperbolic equivalence", "tanh(x)/2+1/2", True),
            ("Zero product equations", "a=0 or b=0", True),
            ("Zero product equations", "a^3*b^3=0", False),
            ("Boolean equivalence", "not a or not b", True),
        ):
            example = next(cards.nth(i) for i in range(cards.count())
                           if engine_data(json.loads(cards.nth(i).locator(".ctm-stack-data").text_content()))["question"]["name"] == question_name)
            example.locator(".stack-answer").fill(response)
            example.locator(".stack-validate").click()
            example.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
            example.locator(".stack-check").click()
            example.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
            assert example.locator(".stack-result").get_attribute("data-state") == ("correct" if correct else "retry")
        collection = page.locator('[data-stack-id="finite-collections"]')
        payload = card_data(collection)
        a = payload['variants'][0]['env']['a']
        for name, response in {'sequence':f'[{a},x+x]', 'members':f'{{2*x,{a}}}',
                               'explained':f'{{{a},2*x,2*x}}'}.items():
            collection.locator(f'.stack-answer[data-name="{name}"]').fill(response)
        collection.locator('.stack-validate').click()
        collection.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        assert collection.locator('.stack-validation[data-name="explained"]').get_attribute('data-latex').count('2') >= 2
        collection.locator('.stack-check').click()
        collection.locator('.stack-result[data-state="correct"]').wait_for(timeout=120000)
        assert 'Repeated elements' in collection.locator('.stack-feedback[data-name="explained"]').inner_text()
        collection.locator('.stack-answer[data-name="explained"]').fill(f'{{{a},3*x}}')
        collection.locator('.stack-validate').click()
        collection.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        collection.locator('.stack-check').click()
        collection.locator('.stack-result[data-state="retry"]').wait_for(timeout=120000)
        text = collection.locator('.stack-feedback[data-name="explained"]').inner_text()
        assert 'Extra elements' in text and 'Missing elements' in text
        collection.locator('.stack-answer[data-name="sequence"]').fill('[[true]]')
        collection.locator('.stack-validate').click()
        collection.locator('.stack-result[data-state="invalid"]').wait_for(timeout=120000)
        assert collection.locator('.stack-check').is_disabled()
        nested = page.locator('[data-stack-id="nested-collections"]')
        data = card_data(nested)
        a = data['variants'][0]['env']['a']
        responses = {'nested':f'[[{a},x+x],{{{{3,2}},1}},[]]',
                     'families':f'{{[{a},2*x],{{2,1}},[{a},2*x]}}',
                     'form':'{[1,1+x],{2,x+x,2}}'}
        for name,response in responses.items():
            nested.locator(f'.stack-answer[data-name="{name}"]').fill(response)
        nested.locator('.stack-validate').click()
        nested.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        preview = nested.locator('.stack-validation[data-name="form"]')
        assert 'x + x' in preview.get_attribute('data-latex')
        nested.locator('.stack-check').click()
        nested.locator('.stack-result[data-state="correct"]').wait_for(timeout=120000)
        assert 'Repeated elements' in nested.locator('.stack-feedback[data-name="families"]').inner_text()
        nested.locator('.stack-answer[data-name="form"]').fill('{[1,1+x],{2,2*x,2}}')
        nested.locator('.stack-validate').click()
        nested.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        nested.locator('.stack-check').click()
        nested.locator('.stack-result[data-state="retry"]').wait_for(timeout=120000)
        assert 'written arithmetic' in nested.locator('.stack-feedback[data-name="form"]').inner_text()
        nested.locator('.stack-answer[data-name="form"]').fill('[[x+x,2,2],[1,x+1]]')
        nested.locator('.stack-validate').click()
        nested.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        nested.locator('.stack-check').click()
        nested.locator('.stack-result[data-state="retry"]').wait_for(timeout=120000)
        assert 'same outer collection type' in nested.locator('.stack-feedback[data-name="form"]').inner_text()
        nested.locator('.stack-answer[data-name="form"]').fill('setify([1,2])')
        nested.locator('.stack-validate').click()
        nested.locator('.stack-result[data-state="invalid"]').wait_for(timeout=120000)
        assert nested.locator('.stack-check').is_disabled()
        multi = page.locator('[data-stack-id="measurements"]')
        for answer in multi.locator(".stack-answer").all():
            answer.fill("0.00")
        multi.locator(".stack-validate").click()
        multi.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        assert multi.locator(".stack-check").is_enabled()
        multi.locator(".stack-check").click()
        multi.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
        assert multi.locator(".stack-result").get_attribute("data-state") == "retry"
        (ROOT / "test-results").mkdir(exist_ok=True)
        page.screenshot(path=str(ROOT / "test-results/example.png"), full_page=True)
        assert not errors, errors
        browser.close()


def _prime_power_answer(number: int) -> str:
    """Build a written prime product independently of the CAS's factor form."""
    assert number > 1
    factors = []
    divisor = 2
    while divisor * divisor <= number:
        exponent = 0
        while number % divisor == 0:
            number //= divisor
            exponent += 1
        if exponent:
            factors.append(f"{divisor}^{exponent}" if exponent > 1 else str(divisor))
        divisor += 1
    if number > 1:
        factors.append(str(number))
    assert len(factors) > 1, "the displayed integer should have multiple prime factors"
    return "*".join(factors)


def _check_corpus_answer(card, answer: str, expected_state: str) -> None:
    response = card.locator('.stack-answer[data-name="ans"]')
    assert response.count() == 1
    response.fill(answer)
    card.locator(".stack-validate").click()
    card.locator('.stack-result[data-state="valid"] .stack-verdict').wait_for(timeout=120000)
    assert card.locator(".stack-check").is_enabled(), answer
    card.locator(".stack-check").click()
    card.locator(f'.stack-result[data-state="{expected_state}"] .stack-verdict').wait_for(timeout=120000)


def test_browser_corpus_native_author_tests_and_form_sensitive_answers():
    """Exercise the actual published cards with the bundled Worker/Pyodide CAS."""
    from scripts.generate_corpus_page import teaching_source
    from ctm_checkers.stack.importer import import_xml

    baseline = json.loads((CORPUS / "baseline.json").read_text())
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    reports = {item["id"]: item for item in baseline["questions"]}
    expected = {
        item["question_name"]: (item, reports[item["id"]])
        for item in manifest["questions"] if reports[item["id"]]["status"] == "qtests_pass"
    }
    assert {"AlgMap-2.1", "AlgMap-2.5", "AlgMap-4.13", "AlgMap-10.1", "AlgMap-13.1"} <= expected.keys()

    site = render_site()
    with serve(site) as url, sync_playwright() as pw:
        browser_options = {"headless": True}
        if os.getenv("CTM_STACK_BROWSER", "chromium") == "chromium" and os.environ.get("STACK_SYMPY_CHROMIUM"):
            browser_options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = getattr(pw, os.getenv('CTM_STACK_BROWSER', 'chromium')).launch(**browser_options)
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.ctm_errors = errors
            page.goto(url + "/corpus.html", wait_until="domcontentloaded")
            cards = page.locator(".ctm-stack:not(.stack-diagnostic)")
            assert cards.count() == len(expected) + 1
            by_name = {}
            for index in range(cards.count()):
                card = cards.nth(index)
                payload = card_data(card)
                if payload["question"]["name"].endswith(" (presentation teaching copy)"):
                    assert payload["question"]["name"] == "7.3.26 (Write sim. eqns. with matrices) (presentation teaching copy)"
                    assert payload["variants"][0]["seed"] >= 1
                    assert card.locator(".stack-answer").count() == 2
                    card.locator(".stack-tests").click()
                    card.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
                    assert card.locator(".stack-result").get_attribute("data-state") == "correct"
                    assert "All question tests passed" in card.locator(".stack-result").inner_text()
                    assert len(card.locator(".stack-test-list li").all_inner_texts()) == 1
                    continue
                name = payload["question"]["name"].removesuffix(" (corrected teaching copy)")
                assert name in expected and name not in by_name, name
                entry, report = expected[name]
                assert payload["question"]["name"] == teaching_source(entry)[1]
                assert payload["variants"][0]["seed"] >= 1, name
                assert card.locator(".stack-answer").count() == entry["input_count"], name
                by_name[name] = (card, payload["variants"][0]["env"])

                prompt = card.locator(".stack-prompt")
                prompt.locator("mjx-container").first.wait_for(timeout=60000)
                assert prompt.locator("mjx-merror").count() == 0, name

                card.locator(".stack-tests").click()
                card.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
                assert card.locator(".stack-result").get_attribute("data-state") == "correct", name
                assert "All question tests passed" in card.locator(".stack-result").inner_text(), name
                cases = card.locator(".stack-test-list li").all_inner_texts()
                question = next(q for q in import_xml(CORPUS.parents[1] / teaching_source(entry)[0])
                                if q["name"] == teaching_source(entry)[1])
                assert len(cases) == len(question["qtests"]), name
                assert all(case.startswith("Pass · ") for case in cases), (name, cases)

            assert set(by_name) == set(expected)

            factor_card, env = by_name["AlgMap-10.1"]
            k, coefficient, variable = int(env["k1"]), int(env["cf1"]), env["v"]
            assert variable in {"x", "y", "z", "t"}
            common = math.gcd(k, coefficient)
            assert common > 1
            _check_corpus_answer(factor_card,
                                 f"{common}*({k // common}-{coefficient // common}*{variable})",
                                 "correct")
            _check_corpus_answer(factor_card, f"{k}-{coefficient}*{variable}", "retry")

            quadratic_card, env = by_name["AlgMap-13.1"]
            variable = env["v"]
            assert variable in {"x", "y", "z", "t"}
            response = quadratic_card.locator('.stack-answer[data-name="ans"]')
            response.fill(f"{variable}/({variable}-1)")
            quadratic_card.locator(".stack-validate").click()
            quadratic_card.locator('.stack-result[data-state="valid"] .stack-verdict').wait_for(timeout=120000)
            quadratic_card.locator(".stack-check").click()
            # ctm-checkers 0.10.0 (S-11): an answer outside FacForm's domain is not an
            # error of the question; the test is false and the tree takes its false branch.
            undecided = quadratic_card.locator('.stack-result[data-state="retry"]')
            undecided.locator(".stack-prt-feedback").wait_for(timeout=120000)
            undecided_text = undecided.inner_text()
            assert "This answer could not be checked automatically." in undecided_text
            assert all(fragment not in undecided_text for fragment in ("Traceback", 'File "', "PythonError", "FacForm supports"))

            # A corrected response recovers on the same card and Worker.
            first_coefficient, first_constant = int(env["cf1"]), int(env["a"])
            second_coefficient, second_constant = int(env["cf2"]), int(env["b"])
            factors = []
            for coefficient, constant in ((first_coefficient, first_constant),
                                          (second_coefficient, second_constant)):
                common = math.gcd(coefficient, constant)
                factors.append(f"{common}*({coefficient // common}*{variable}{constant // common:+d})")
            response.fill("*".join(factors))
            assert quadratic_card.locator(".stack-result").inner_text() == ""
            assert quadratic_card.locator(".stack-check").is_disabled()
            _check_corpus_answer(quadratic_card, response.input_value(), "correct")

            primes_card, env = by_name["AlgMap-2.1"]
            number = int(env["n"])
            _check_corpus_answer(primes_card, _prime_power_answer(number), "correct")
            _check_corpus_answer(primes_card, str(number), "retry")
            assert "not fully factored" in primes_card.locator(".stack-result .stack-prt-feedback").inner_text()

            lowest_card, env = by_name["AlgMap-2.5"]
            numerator, denominator, multiplier = int(env["a"]), int(env["b"]), int(env["c"])
            assert denominator != 0 and multiplier > 1
            reduced = Fraction(numerator, denominator)
            _check_corpus_answer(lowest_card, f"{reduced.numerator}/{reduced.denominator}", "correct")
            _check_corpus_answer(lowest_card, f"({numerator * multiplier})/({denominator * multiplier})", "retry")
            assert "cancel common factors" in lowest_card.locator(
                ".stack-result .stack-prt-feedback").inner_text()
            # The live teaching copy must check value before reduced form.
            assert reduced != 1  # odd a / even b cannot equal one
            _check_corpus_answer(lowest_card, "1", "retry")
            _check_corpus_answer(lowest_card, "123/127", "retry")
            assert "same value" in lowest_card.locator(".stack-result .stack-prt-feedback").inner_text()

            single_card, env = by_name["AlgMap-4.13"]
            linear, constant, fraction = int(env["A"]), int(env["B"]), int(env["C"])
            assert fraction > 0 and env["D"].replace(" ", "") == "x+1"
            _check_corpus_answer(single_card,
                                 f"({linear}*x^2+{linear + constant}*x+{constant + fraction})/(x+1)",
                                 "correct")
            _check_corpus_answer(single_card, f"{linear}*x+{constant}+{fraction}/(x+1)", "retry")
            assert not errors, errors
        finally:
            browser.close()
