#!/usr/bin/env python3
"""Actual sealed Maxima/Python workers: isolation, errors, Stop and replay."""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright


def run(project,output,engine='chromium',executable=None):
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(project)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    report={'schema':1,'passed':False,'checks':[]}
    try:
        with sync_playwright() as p:
            browser=getattr(p,engine).launch(**({'executable_path':executable} if executable else {}))
            try:
                page=browser.new_page();errors=[];requests=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request:requests.append(request.url))
                page.add_init_script('''(() => {const Original=Worker;window.probe={workers:[]};window.mainPyodide={sentinel:true};
                  window.Worker=class extends Original {constructor(url,options){super(url,options);
                    const item={url:String(url),terminated:false};probe.workers.push(item);
                    this.addEventListener('message',({data})=>{if(data?.type==='python-check'&&data.request?.inputs?.ans?.raw==='999')
                      probe.runawayCalls=(probe.runawayCalls||0)+1;});
                    const stop=this.terminate.bind(this);this.terminate=()=>{item.terminated=true;return stop();};}};
                })();''')
                page.goto(f'http://127.0.0.1:{server.server_port}/index.html',wait_until='domcontentloaded')
                assert page.evaluate('crossOriginIsolated') is False
                control=page.locator('[data-stack-id="sympy-control"] .stack-answer');control.fill('x+1')
                def payload(card):return json.loads(card.locator('.ctm-stack-data').text_content())
                def selected(card):
                    page.wait_for_function('el=>!!el.dataset.stackVariantId',arg=card.element_handle())
                    return next(row for row in payload(card)['variants'] if row['id']==card.get_attribute('data-stack-variant-id'))
                def answer(card,text,state='correct'):
                    card.locator('.stack-answer').fill(text);card.locator('.stack-validate').click()
                    card.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                    card.locator('.stack-check').click()
                    card.locator('.stack-result[data-state="'+state+'"]').wait_for(timeout=60000)
                ordinary=page.locator('[data-stack-id="plain-native"]')
                answer(ordinary,selected(ordinary)['plan']['teachers']['ans']['source'])
                assert not any('pyodide.asm' in url or url.endswith('.whl') for url in requests)
                report['checks'].append('ordinary native grading starts no Python interpreter')
                card=page.locator('[data-stack-id="native-python"]')
                answer(card,selected(card)['plan']['teachers']['ans']['source'])
                assert '<plain Python feedback>' in card.inner_text()
                assert card.locator('plain').count()==0
                report['checks'].append('native Python predicate and implicit checker use fresh namespaces and plain feedback')
                answer(card,'-1','retry');answer(card,'0','invalid')
                assert 'Use a nonzero answer.' in card.locator('.stack-validation').inner_text()
                answer(card,'666','error');assert card.locator('.stack-retry').count()==0
                answer(card,selected(card)['plan']['teachers']['ans']['source'])
                report['checks'].append('wrong, invalid and author-error outcomes remain distinct and recover')
                card.locator('.stack-tests').click()
                page.wait_for_function('el=>el.textContent.includes("All question tests passed")',arg=card.locator('.stack-result').element_handle(),timeout=60000)
                report['checks'].append('XML and native-resolved declarative tests pass in Pyodide')
                # A synchronous Python runaway must terminate only the two
                # workers owned by this backend, without replaying the attempt.
                card.locator('.stack-answer').fill('999');card.locator('.stack-validate').click()
                card.locator('.stack-result[data-state="valid"]').wait_for(timeout=60000)
                card.locator('.stack-check').click();card.locator('.stack-stop').wait_for(timeout=15000)
                page.wait_for_function('probe.runawayCalls===1',timeout=15000)
                card.locator('.stack-stop').click();card.locator('.stack-result[data-state="error"]').wait_for(timeout=15000)
                assert card.locator('.stack-answer').input_value()=='999'
                assert page.evaluate('probe.runawayCalls')==1
                answer(card,selected(card)['plan']['teachers']['ans']['source'])
                report['checks'].append('Stop interrupts a Python runaway, preserves answers and permits a fresh attempt')
                previous=card.get_attribute('data-stack-variant-id')
                page.once('dialog',lambda dialog:dialog.accept());card.locator('.stack-new-variant').click()
                page.wait_for_function('({el,previous})=>el.dataset.stackVariantId!==previous',arg={'el':card.element_handle(),'previous':previous})
                answer(card,selected(card)['plan']['teachers']['ans']['source'])
                assert page.evaluate('probe.workers.filter(w=>w.url.includes("card-worker.js")&&w.terminated).length')>=2
                report['checks'].append('variant changes replace the native/Python context')
                basis=page.locator('[data-stack-id="native-basis"]');host=basis.locator('.stack-matrix')
                def fill_basis(values):
                    cells=host.locator('input[data-matrix-row]');assert cells.count()==len(values)
                    for cell,value in zip(cells.all(),values):cell.fill(str(value))
                def check_basis(state):
                    basis.locator('.stack-validate').click()
                    basis.locator('.stack-result[data-state="valid"]').wait_for(timeout=180000)
                    assert host.locator('input.math-input-ok,input.math-input-dependent,input.math-input-wrong').count()==0
                    basis.locator('.stack-check').click()
                    basis.locator('.stack-result[data-state="'+state+'"]').wait_for(timeout=60000)
                fill_basis([0,0,1]);check_basis('correct')
                assert host.locator('input.math-input-ok').count()==3
                host.locator('[data-dynamic-action="add-col"]').click()
                fill_basis([0,0,0,0,1,2]);check_basis('retry')
                assert host.locator('input.math-input-dependent').count()==6
                host.locator('input[data-matrix-row]').first.fill('x')
                check_basis('invalid')
                assert host.locator('input.math-input-ok,input.math-input-dependent,input.math-input-wrong').count()==0
                report['checks'].append('basis column assessments match native validated dimensions and clear on invalidity')
                assert control.input_value()=='x+1' and page.evaluate('mainPyodide.sentinel') is True
                assert not errors,errors
                report.update(passed=True,browser=browser.version,workers=page.evaluate('probe.workers'))
                report['checks'].append('main interpreter and other backend answers remain untouched; no page errors')
            finally:browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--browser',default='chromium',choices=('chromium','firefox','webkit'));parser.add_argument('--executable')
    args=parser.parse_args();run(args.project,args.output,args.browser,args.executable)
