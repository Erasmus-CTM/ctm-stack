"""The real controller against a future backend; no CAS or provider substitute."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

import ctm_parts

ROOT = Path(__file__).resolve().parents[1]


def browser_for(pw):
    name = os.getenv('CTM_STACK_BROWSER', 'chromium')
    options = {'headless': True}
    if name == 'chromium' and os.getenv('STACK_SYMPY_CHROMIUM'):
        options['executable_path'] = os.environ['STACK_SYMPY_CHROMIUM']
    return getattr(pw, name).launch(**options)


def mount(page, behavior='valid', *, stop_after=20, store=False):
    inputs = '<input class="stack-answer" data-name="a"><span class="stack-validation" data-name="a"></span>'
    data = {'version': 2, 'id': 'future-card', 'common': {'inputs': [{'name': 'a'}], 'qtests': [], 'checker': None},
            'backend': {'id': 'future-backend', 'question': {'opaque': 'question'}},
            'variants': [{'n': 7, 'id': 'seed=9', 'hash': '0123456789abcdef',
                          'display': {'question_html': inputs}, 'plan': {'opaque': 'plan'}}], 'review': False}
    descriptor = {'id': 'future-backend', 'version': 'test', 'adapter': 'future-adapter.js', 'requires': {'isolation': False}}
    page.set_content('<script type="application/json" class="ctm-stack-backend" data-backend="future-backend">'
        + json.dumps(descriptor) + '</script><section class="ctm-stack" data-stack-id="future-card" data-backend="future-backend" '
        + 'data-lang="en" data-ctm-id="future-card" data-ctm-source="0123456789abcdef" data-stop-after="' + str(stop_after) + '">'
        + '<div class="stack-prompt">' + inputs + '</div><div class="stack-actions">'
        + '<button class="stack-validate">Validate</button><button class="stack-check" disabled>Check</button></div>'
        + '<div class="stack-result"></div><script type="application/json" class="ctm-stack-data">'
        + json.dumps(data) + '</script></section>')
    for file in ['ctm-locale.js', 'common.js', 'ctm-stack.js']:
        page.add_script_tag(path=str(ctm_parts.CTM_LIBS / 'locales' / file))
    page.evaluate('''({behavior, store}) => {
      window.probe = {requests: [], restarts: 0, stops: 0, results: [], clears: 0};
      window.mainPyodide = {publishedSentinel: true};
      window.MathJax = {typesetPromise: async () => {}, typesetClear: () => {}};
      window.MathExerciseRuntime = {loadScript: async () => {}};
      window.CTMStackAdapters = {'future-backend': () => ({
        isolationRequired: false, start: async () => {if(behavior==='startup-pending')await new Promise(resolve=>{probe.ready=resolve;});},
        request: async request => {
          probe.requests.push(request);
          if (behavior === 'pending' || behavior === 'startup-pending') return new Promise(resolve => { probe.finish = resolve; });
          if (behavior === 'author' || behavior === 'runtime') return {ok:false,error:{kind:behavior,code:'controlled',message:'controlled failure'}};
          return {ok:true,result:{status:request.type === 'grade' ? 'graded' : 'valid',score:1,inputs:{a:{valid:true,latex:request.answers.a}},prts:{}}};
        },
        stop: async () => { probe.stops++; probe.finish({ok:false,error:{kind:'runtime',code:'interrupt',message:'interrupted'}}); return {restarted:false}; },
        restart: async () => { probe.restarts++; behavior='valid'; }
      })};
      if (store) window.CTMStore = {register: options => {
        probe.storeOptions=options;
        return {restore:()=>{},changed:()=>{},flush:()=>{},result:value=>probe.results.push(value)};
      }};
    }''', {'behavior': behavior, 'store': store})
    # Serve exact production bytes through a local route, with a real script URL.
    page.route('https://ctm.test/ctm-stack.js', lambda route: route.fulfill(content_type='application/javascript',
        body=(ROOT / '_extensions/ctm-stack/ctm-stack.js').read_text()))
    page.add_script_tag(url='https://ctm.test/ctm-stack.js')


def test_future_backend_opaque_plans_and_store_result():
    with sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            mount(page, store=True)
            page.locator('.stack-answer').fill('x+1')
            page.locator('.stack-validate').click()
            page.locator('.stack-result[data-state=valid]').wait_for()
            page.locator('.stack-check').click()
            page.locator('.stack-result[data-state=correct]').wait_for()
            requests = page.evaluate('probe.requests')
            assert [item['type'] for item in requests] == ['validate', 'grade']
            assert all(item['question'] == {'opaque': 'question'} and item['variant'] == {'opaque': 'plan'} for item in requests)
            assert all(item['answers'] == {'a': 'x+1'} for item in requests)
            assert page.evaluate('probe.results') == [{'score': 1, 'status': 'correct', 'variant': {'n': 7, 'id': 'seed=9', 'hash': '0123456789abcdef'}}]
            assert page.evaluate('probe.storeOptions.read()') == {'answers': {'a': 'x+1'}, 'matrices': {}}
            assert page.locator('.stack-answer').get_attribute('aria-describedby')
        finally:
            browser.close()


def test_author_failure_keeps_session_and_runtime_failure_can_retry():
    with sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            for kind in ['author', 'runtime']:
                mount(page, behavior=kind)
                page.locator('.stack-answer').fill('keep me')
                page.locator('.stack-validate').click()
                page.locator('.stack-result[data-state=error]').wait_for()
                assert page.locator('.stack-answer').input_value() == 'keep me'
                assert page.evaluate('probe.restarts') == 0
                assert page.locator('.stack-retry').count() == (kind == 'runtime')
                if kind == 'runtime':
                    page.locator('.stack-retry').click()
                    page.locator('.stack-result[data-state=valid]').wait_for()
                    assert page.evaluate('probe.restarts') == 1
        finally:
            browser.close()


def test_stop_routes_to_adapter_and_keeps_the_published_runtime():
    with sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            mount(page, behavior='pending', stop_after=.01)
            page.locator('.stack-answer').fill('keep me')
            page.locator('.stack-validate').click()
            page.locator('.stack-stop').click()
            page.locator('.stack-result[data-state=error]').wait_for()
            assert page.locator('.stack-result').inner_text() == 'Stopped.'
            assert page.locator('.stack-answer').input_value() == 'keep me'
            assert page.evaluate('probe.stops') == 1
            assert page.evaluate('probe.restarts') == 0
            assert page.evaluate('mainPyodide.publishedSentinel') is True
        finally:
            browser.close()


def test_sympy_adapter_scopes_shared_stop_to_its_private_proxy():
    with sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            for isolated in [False, True]:
                page.goto('about:blank')
                page.add_script_tag(path=str(ctm_parts.CTM_LIBS / 'runtime/pyodide-runtime.js'))
                page.add_script_tag(path=str(ROOT / '_extensions/ctm-stack/backends/sympy.js'))
                result = page.evaluate('''async isolated => {
                  Object.defineProperty(window,'crossOriginIsolated',{value:isolated,configurable:true});
                  const published={published:true}; window.mainPyodide=published;
                  const p={starts:[],restarts:0,interrupts:0,loaded:[],calls:[]};
                  window.CTMCheckersStack={marker:true};
                  MathExerciseRuntime.ensureCheckers=async(py,stack)=>{if(!stack.marker)throw Error('wrong part');};
                  MathExerciseRuntime.callCheckers=async(py,name,request)=>{p.calls.push({name,request});return JSON.stringify({ok:true,result:{status:'valid'}});};
                  window.CTMWorker={start:async options=>{
                    p.starts.push(options.publish);
                    const py={loadPackage:async name=>p.loaded.push(name),interruptBuffer:isolated?new Int32Array(1):null,
                      interrupt:()=>{p.interrupts++;},clearInterrupt:()=>{},whenIdle:async()=>{},
                      restart:()=>{p.restarts++;const next=CTMWorker.start(options);options.onRestart(next);return next;}};
                    return py;
                  }};
                  const adapter=CTMStackAdapters.sympy();await adapter.start();
                  const before=await adapter.request({type:'validate',question:{opaque:1},variant:{opaque:2},answers:{a:'x'}});
                  const stopped=await adapter.stop('unit stop');await adapter.start();
                  return {...p,stopped,publishedUnchanged:mainPyodide===published,before};
                }''', isolated)
                assert result['publishedUnchanged'] is True
                assert result['starts'] == ([False] if isolated else [False, False])
                assert result['interrupts'] == int(isolated)
                assert result['restarts'] == int(not isolated)
                assert result['stopped'] == {'restarted': not isolated}
                assert result['calls'] == [{'name': 'stack.validate', 'request': {'question': {'opaque': 1}, 'variant': {'opaque': 2}, 'answers': {'a': 'x'}}}]
        finally:
            browser.close()


def test_sympy_late_failed_startup_cannot_replace_the_retry_session():
    with sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            page.add_script_tag(path=str(ROOT / '_extensions/ctm-stack/backends/sympy.js'))
            result = page.evaluate('''async () => {
              let finish, calls=0; const released=[];
              window.CTMCheckersStack={};
              window.MathExerciseRuntime={loadTimeout:20,ensureCheckers:async()=>{},callCheckers:async py=>JSON.stringify({ok:true,result:py.id})};
              window.CTMWorker={start:async()=>{
                const id=++calls;return {id,loadPackage:async()=>{if(id===1)await new Promise(resolve=>{finish=resolve;});},terminate:()=>released.push(id)};
              }};
              const adapter=CTMStackAdapters.sympy();let code;
              try {await adapter.start();}catch(error){code=error.code;}
              MathExerciseRuntime.loadTimeout=1000;
              await adapter.start();finish();await new Promise(resolve=>setTimeout(resolve,0));
              const reply=await adapter.request({type:'validate',question:{},variant:{},answers:{}});
              return {code,calls,released,reply};
            }''')
            assert result['code'] == 'pyodide-timeout'
            assert result['calls'] == 2
            assert result['released'] and set(result['released']) == {1}
            assert result['reply'] == {'ok': True, 'result': 2}
        finally:
            browser.close()


def test_loading_does_not_consume_the_calculation_stop_clock():
    with sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            mount(page, behavior='startup-pending', stop_after=.01)
            page.locator('.stack-answer').fill('x')
            page.locator('.stack-validate').click()
            page.wait_for_function('typeof probe.ready === "function"')
            page.wait_for_timeout(50)
            assert page.locator('.stack-stop').count() == 0
            assert page.evaluate('probe.requests.length') == 0
            page.evaluate('probe.ready()')
            page.locator('.stack-stop').wait_for()
            page.locator('.stack-stop').click()
            page.locator('.stack-result[data-state=error]').wait_for()
        finally:
            browser.close()


def test_superseded_queued_request_never_reaches_a_backend():
    with sync_playwright() as pw:
        browser = browser_for(pw)
        try:
            page = browser.new_page()
            mount(page, behavior='pending')
            answer = page.locator('.stack-answer')
            answer.fill('first')
            page.locator('.stack-validate').click()
            page.wait_for_function('probe.requests.length === 1')
            for value in ['superseded', 'latest']:
                answer.fill(value)
                page.locator('.stack-validate').dispatch_event('click')
            page.evaluate("probe.finish({ok:true,result:{status:'valid',inputs:{a:{valid:true,latex:'first'}}}})")
            page.wait_for_function('probe.requests.length === 2')
            assert [item['answers']['a'] for item in page.evaluate('probe.requests')] == ['first', 'latest']
            page.evaluate("probe.finish({ok:true,result:{status:'valid',inputs:{a:{valid:true,latex:'latest'}}}})")
            page.locator('.stack-result[data-state=valid]').wait_for()
            assert 'latest' in page.locator('.stack-validation').inner_text()
            assert page.locator('.stack-check').is_enabled()
        finally:
            browser.close()
