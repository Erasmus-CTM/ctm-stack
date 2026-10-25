"""Hosted browser checks against the installed ai-feedback runtime, without a provider."""
from __future__ import annotations

import html
import json
import os
import re

from playwright.sync_api import sync_playwright

from browser import serve


def browser_for(pw):
    options = {"headless": True}
    if os.getenv("CTM_STACK_BROWSER", "chromium") == "chromium" and os.environ.get("STACK_SYMPY_CHROMIUM"):
        options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
    return getattr(pw, os.getenv('CTM_STACK_BROWSER', 'chromium')).launch(**options)


def prompt_data(card):
    card.locator(".stack-feedback-button").click()
    text = card.locator(".ai-feedback-prompt").inner_text()
    return json.loads(text.split("\n\nUSER\n", 1)[1])


def test_feedback_copy_prompt_and_context_modes(browser_site):
    site = browser_site
    with serve(site) as url, sync_playwright() as pw:
        browser = browser_for(pw)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url + "/index.html", wait_until="domcontentloaded")
        card = page.locator('[data-stack-id="expansion"]')
        assert card.locator(".stack-feedback-button").count() == 1
        assert card.locator(".ai-feedback-gear").count() == 1
        assert page.locator("#ai-feedback-settings").count() == 0
        card.locator(".ai-feedback-gear").click()
        assert page.locator("#ai-feedback-settings[open]").count() == 1
        page.locator("#ai-feedback-settings button").first.click()
        card.locator(".stack-answer").first.fill("x**2+8x+15")
        first = prompt_data(card)
        assert "[Answer " in first["task"]
        # Numeric TeX groups such as {5} preserve CAS expression boundaries.
        # Strip only those groups before checking the frozen product structure.
        task_without_numeric_groups = re.sub(r"\{(\d+)\}", r"\1", first["task"])
        assert re.search(r"\\\(\(x\+\d+\)\(x\+\d+\)\\\)", task_without_numeric_groups)
        assert "{@" not in first["task"]  # Frozen coefficients, not author CAS text.
        assert "<quiz>" not in json.dumps(first)
        assert "questionvariables" not in json.dumps(first)
        assert first["responses"][0]["value"] == "x**2+8x+15"
        assert first["evidence"] == []
        assert first["materials"] and "Visible course context for the expansion activity." in first["materials"][0]["text"]
        assert "CURRENT HINT LEVEL: 1 OF 4" in card.locator(".ai-feedback-prompt").inner_text()
        card.locator(".stack-answer").first.fill("x+1")
        assert card.locator(".ai-feedback-output").inner_text() == ""
        second = prompt_data(card)
        assert second["responses"][0]["value"] == "x+1"
        assert "CURRENT HINT LEVEL: 2 OF 4" in card.locator(".ai-feedback-prompt").inner_text()
        wrapped = page.evaluate("""() => {
          const group = document.querySelector('.stack-question-group');
          const context = document.createElement('div');
          context.className = 'ai-context';
          context.id = 'wrapped-stack-context';
          context.append(document.createTextNode('Visible course context.'));
          group.before(context);
          context.append(group);
          return window.AIFeedback.collectExplicitContexts('wrapped-stack-context');
        }""")
        assert len(wrapped) == 1
        assert wrapped[0]["content"] == "Visible course context."

        page.goto(url + "/examples.html", wait_until="domcontentloaded")
        cards = page.locator(".ctm-stack[data-stack-feedback]")
        assert cards.count() > 0
        seen_modes = set()
        assert page.locator("#ai-feedback-settings").count() == 0
        for index in range(cards.count()):
            card = cards.nth(index)
            card.locator(".stack-answer").first.fill("1")
            data = prompt_data(card)
            context = json.loads(card.get_attribute("data-stack-feedback"))["context"]
            seen_modes.add(context["mode"])
            if context["mode"] == "explicit":
                assert any("Visible measurement context" in m["text"] for m in data["materials"])
            elif context["mode"] == "none":
                assert data["materials"] == []
            assert "<quiz>" not in json.dumps(data)
            assert "expectedanswernote" not in json.dumps(data)
        assert seen_modes == {"auto", "explicit", "none"}
        assert not errors, errors
        browser.close()


def test_inherited_policy_steps_permissions_and_parent_changes(browser_site):
    site = browser_site
    with serve(site) as url, sync_playwright() as pw:
        browser = browser_for(pw)
        page = browser.new_page()
        page.goto(url + "/examples.html", wait_until="domcontentloaded")
        card = page.locator('[data-stack-id="rational"]')
        card.locator(".stack-answer").first.fill("x+1")
        prompt_data(card)
        first = card.locator(".ai-feedback-prompt").inner_text()
        assert "CURRENT HINT LEVEL: 1 OF 2" in first
        assert "at most 90 words" in first
        assert "Do not supply a complete rewritten response or finished solution" in first
        assert "Preserve every stated given" in first  # Shared mathematics base remains active.
        prompt_data(card)
        second = card.locator(".ai-feedback-prompt").inner_text()
        assert "CURRENT HINT LEVEL: 2 OF 2" in second
        assert "A complete rewrite or solution is permitted" in second
        assert "Give a concise worked explanation" in second
        prompt_data(card)
        assert "CURRENT HINT LEVEL: 2 OF 2" in card.locator(".ai-feedback-prompt").inner_text()

        # A changed inherited parent resets the dependent activity's progression.
        page.evaluate("""() => {
          window.__aiFeedbackPolicies.layers[0].policies['brief-mathematics']['max-words'] = 70;
        }""")
        prompt_data(card)
        changed = card.locator(".ai-feedback-prompt").inner_text()
        assert "CURRENT HINT LEVEL: 1 OF 2" in changed
        assert "at most 70 words" in changed
        assert "Do not supply a complete rewritten response or finished solution" in changed

        # A definition without an explicit selection does not override the page baseline.
        other = page.locator('[data-stack-id="measurements"]')
        other.locator(".stack-answer").first.fill("1")
        prompt_data(other)
        assert "CURRENT HINT LEVEL: 1 OF 4" in other.locator(".ai-feedback-prompt").inner_text()
        browser.close()


def test_explicit_diagram_context_uses_shared_collector(browser_site):
    site = browser_site
    output = (site / "index.html").read_text()
    match = re.search(r'data-stack-feedback="([^"]+)"', output)
    config = json.loads(html.unescape(match[1]))
    config["context"] = {"mode": "explicit", "refs": "jsxgraph:lesson-board,jsxgraph:lesson-board"}
    output = output[:match.start(1)] + html.escape(json.dumps(config), quote=True) + output[match.end(1):]
    # A real iframe implements the shared request/response protocol. No provider
    # or Python execution is involved in collecting this explicit context.
    image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
    frame = "<script>addEventListener('message', e => { const d = e.data; " + (
        "if (d.type !== 'request') return; parent.postMessage({...d, type:'response', "
        "payload:{radius:3}, ai:{summary:'Circle radius 3', image:" + json.dumps(image) + "}}, '*'); });</script>"
    )
    output = output.replace("</body>", '<iframe id="lesson-board" srcdoc="' + html.escape(frame, quote=True) + '"></iframe></body>')
    with serve(site) as url, sync_playwright() as pw:
        browser = browser_for(pw)
        page = browser.new_page()
        page.route("**/index.html", lambda route: route.fulfill(body=output, content_type="text/html"))
        page.goto(url + "/index.html", wait_until="domcontentloaded")
        card = page.locator('[data-stack-id="expansion"]')
        card.locator(".stack-answer").first.fill("x+1")
        card.locator(".stack-feedback-button").click()
        prompt = card.locator(".ai-feedback-prompt").inner_text()
        data, _ = json.JSONDecoder().raw_decode(prompt.split("\n\nUSER\n", 1)[1])
        assert len(data["materials"]) == len(data["attachments"]) == 1
        assert json.loads(data["materials"][0]["text"])["state"] == {"radius": 3}
        assert data["attachments"][0]["role"] == "context"
        assert "ATTACH THE ORIGINAL IMAGES" in prompt
        assert image not in prompt
        assert card.locator(".ai-feedback-images img").count() == 1
        assert card.locator(".stack-result").inner_text() == ""
        browser.close()


API_STUB = r"""
(() => {
  localStorage.setItem('ai-feedback-config-v1', JSON.stringify({
    mode: 'api', storage: 'local', baseUrl: 'https://feedback.example.invalid/v1',
    model: 'test-instruct', apiKey: 'local-fake-key'
  }));
  window.__requests = [];
  window.__pendingFeedback = [];
  const original = window.fetch.bind(window);
  window.fetch = (url, options) => {
    if (!String(url).startsWith('https://feedback.example.invalid/v1/')) return original(url, options);
    window.__requests.push(JSON.parse(options.body));
    return new Promise(resolve => window.__pendingFeedback.push(resolve));
  };
  window.__replyFeedback = () => {
    const resolve = window.__pendingFeedback.shift();
    resolve(new Response(JSON.stringify({ choices: [{ finish_reason: 'stop',
      message: { content: 'Consider the algebraic structure.' } }] }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }));
  };
})();
"""


def api_request(page, count):
    page.wait_for_function("count => window.__requests.length >= count", arg=count)
    return page.evaluate("count => window.__requests[count - 1]", count)


def user_data(request):
    return json.loads(request["messages"][-1]["content"])


def test_feedback_api_evidence_and_stale_cancellation(browser_site):
    site = browser_site
    with serve(site) as url, sync_playwright() as pw:
        browser = browser_for(pw)
        page = browser.new_page()
        page.add_init_script(API_STUB)
        page.goto(url + "/index.html", wait_until="domcontentloaded")
        card = page.locator('[data-stack-id="expansion"]')
        answer = card.locator(".stack-answer").first
        button = card.locator(".stack-feedback-button")
        answer.fill("x**2+8x+15")
        button.click()
        first = api_request(page, 1)
        assert user_data(first)["evidence"] == []
        assert card.locator(".stack-result").inner_text() == ""  # Feedback did not grade.
        answer.fill("x+1")
        page.evaluate("window.__replyFeedback()")
        button.wait_for(state="visible")
        page.wait_for_function("() => !document.querySelector('.stack-feedback-button').disabled")
        assert card.locator(".ai-feedback-output").inner_text() == ""

        card.locator(".stack-tests").click()
        card.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
        button.click()
        assert user_data(api_request(page, 2))["evidence"] == []
        page.evaluate("window.__replyFeedback()")
        card.locator(".ai-feedback-body").wait_for()

        # Neither authored tests nor Validate become provider-visible assessment.
        answer.fill("x**2+8x+15")
        card.locator(".stack-validate").click()
        card.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        button.click()
        assert user_data(api_request(page, 3))["evidence"] == []
        page.evaluate("window.__replyFeedback()")
        card.locator(".ai-feedback-body").wait_for()
        card.locator(".stack-check").click()
        card.locator('.stack-result[data-state="correct"]').wait_for(timeout=120000)
        button.click()
        checked = user_data(api_request(page, 4))
        assert "CURRENT HINT LEVEL: 1 OF 4" in api_request(page, 4)["messages"][0]["content"]
        assert checked["evidence"]
        evidence = json.loads(checked["evidence"][0]["text"])
        assert evidence["status"] == "graded"
        assert evidence["score"] == 1
        assert set(evidence) == {"status", "score"}
        assert "teacher" not in json.dumps(checked)
        assert "expected" not in json.dumps(checked)
        assert "<quiz>" not in json.dumps(checked)
        # A new Check cancels feedback even when the answer text is unchanged.
        card.locator(".stack-check").click()
        card.locator('.stack-result[data-state="correct"]').wait_for(timeout=120000)
        page.evaluate("window.__replyFeedback()")
        page.wait_for_function("() => !document.querySelector('.stack-feedback-button').disabled")
        assert card.locator(".ai-feedback-output").inner_text() == ""
        button.click()
        assert user_data(api_request(page, 5))["evidence"]
        answer.fill("x+1")
        page.evaluate("window.__replyFeedback()")
        page.wait_for_function("() => !document.querySelector('.stack-feedback-button').disabled")
        assert card.locator(".ai-feedback-output").inner_text() == ""
        button.click()
        assert user_data(api_request(page, 6))["evidence"] == []
        selector = card.locator(".stack-variant")
        selector.select_option(index=1)
        assert answer.input_value() == ""
        answer.fill("x+1")  # Same string on a different frozen variant remains stale.
        page.evaluate("window.__replyFeedback()")
        page.wait_for_function("() => !document.querySelector('.stack-feedback-button').disabled")
        assert card.locator(".ai-feedback-output").inner_text() == ""
        button.click()
        assert user_data(api_request(page, 7))["evidence"] == []
        assert "CURRENT HINT LEVEL: 1 OF 4" in api_request(page, 7)["messages"][0]["content"]
        page.evaluate("window.__replyFeedback()")
        card.locator(".ai-feedback-body").wait_for()
        browser.close()


def test_check_can_preserve_hints_but_variant_selection_always_resets(browser_site):
    site = browser_site
    with serve(site) as url, sync_playwright() as pw:
        browser = browser_for(pw)
        page = browser.new_page()
        page.goto(url + "/index.html", wait_until="domcontentloaded")
        # Override through the shared exercise namespace using the emitted card key.
        page.evaluate("""() => {
          const card = document.querySelector('[data-stack-feedback]');
          const key = JSON.parse(card.dataset.stackFeedback).policySelection.exercise;
          window.__aiFeedbackPolicies.layers.push({exercises: {'stack': {
            [key]: {'reset-on-run': false, language: 'nb', 'max-words': 80}
          }}});
        }""")
        card = page.locator('[data-stack-id="expansion"]')
        card.locator(".stack-answer").first.fill("x**2+8x+15")
        prompt_data(card)
        first = card.locator(".ai-feedback-prompt").inner_text()
        assert "CURRENT HINT LEVEL: 1 OF 4" in first
        assert "Write explanations in nb" in first
        assert "at most 80 words" in first
        card.locator(".stack-validate").click()
        card.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        card.locator(".stack-check").click()
        card.locator('.stack-result[data-state="correct"]').wait_for(timeout=120000)
        assert prompt_data(card)["evidence"]
        assert "CURRENT HINT LEVEL: 2 OF 4" in card.locator(".ai-feedback-prompt").inner_text()
        card.locator(".stack-variant").select_option(index=1)
        card.locator(".stack-answer").first.fill("x+1")
        assert prompt_data(card)["evidence"] == []
        assert "CURRENT HINT LEVEL: 1 OF 4" in card.locator(".ai-feedback-prompt").inner_text()
        browser.close()


# Controlled transport failure, with the real production Worker and frontend.
# Existing tests above continue to exercise real Pyodide and STACK grading.
INIT_FAILURE_PROBE = r"""
(() => {
  const set = window.setTimeout.bind(window), clear = window.clearTimeout.bind(window);
  const probe = window.__stackInitFailure = {workers: [], deadlines: []};
  window.setTimeout = function(callback, delay, ...args) {
    const id=set(callback,delay,...args); if (delay===1000) probe.deadlines.push({id,callback,cleared:false}); return id;
  };
  window.clearTimeout = function(id) { for (const timer of probe.deadlines) if (timer.id===id) timer.cleared=true; return clear(id); };
  probe.configure = function() {
    MathExerciseRuntime.loadTimeout=1000;
    MathExerciseRuntime.ensureCheckers=async()=>{};
    MathExerciseRuntime.callCheckers=async(py,name,data)=>JSON.stringify({ok:true,result:{status:'valid',inputs:Object.fromEntries(Object.keys(data.answers).map(key=>[key,{valid:true,latex:data.answers[key]}]))}});
    CTMWorker.start=async()=>{
      const record={terminated:false}, first=probe.workers.length===0; probe.workers.push(record);
      return {loadPackage:async()=>{if(first)throw Error('Controlled initial package failure');},terminate:()=>{record.terminated=true;}};
    };
  };
  probe.snapshot=()=>({workers:probe.workers.map(w=>({...w})),deadlines:probe.deadlines.map(t=>({cleared:t.cleared}))});
  probe.expireOriginalDeadline=()=>{const timer=probe.deadlines[0];if(!timer.cleared){clear(timer.id);timer.callback();}};
})();
"""


def test_worker_initial_message_failure_cleans_up_and_retry_stays_alive(browser_site):
    with serve(browser_site) as url, sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            page.add_init_script(INIT_FAILURE_PROBE)
            page.goto(url + "/index.html", wait_until="domcontentloaded")
            page.evaluate("window.__stackInitFailure.configure()")
            card = page.locator('[data-stack-id="expansion"]')
            card.locator(".stack-answer").first.fill("x+1")
            card.locator(".stack-validate").click()
            card.locator('.stack-result[data-state="error"]').wait_for()
            assert "Controlled initial package failure" in card.locator(".stack-result").inner_text()
            failed = page.evaluate("window.__stackInitFailure.snapshot()")
            assert len(failed["workers"]) == 1
            assert failed["workers"][0]["terminated"], failed
            assert failed["deadlines"] == [{"cleared": True}], failed

            card.locator(".stack-validate").click()
            card.locator('.stack-result[data-state="valid"]').wait_for()
            page.evaluate("window.__stackInitFailure.expireOriginalDeadline()")
            card.locator(".stack-validate").click()
            card.locator('.stack-result[data-state="valid"]').wait_for()
            retried = page.evaluate("window.__stackInitFailure.snapshot()")
            assert len(retried["workers"]) == 2, retried
            assert not retried["workers"][1]["terminated"], retried
            assert all(timer["cleared"] for timer in retried["deadlines"]), retried
            assert card.locator(".stack-check").is_enabled()
        finally:
            browser.close()
