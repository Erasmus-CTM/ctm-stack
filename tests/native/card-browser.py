#!/usr/bin/env python3
"""Exercise a rendered native expansion card through the real browser worker.

The HTML must be rendered by Quarto with the installed component and actual
checker payload. No evaluation endpoint or substitute grade function is added.
"""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright


def run(project,output,*,engine='chromium',executable=None):
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
                page.add_init_script('''(() => {
                  const Original=window.Worker;
                  window.nativeWorkers=[];
                  window.Worker=class extends Original {
                    constructor(url,options){super(url,options);const item={url:String(url),types:[],scores:[],terminated:false};nativeWorkers.push(item);
                      this.addEventListener('message',({data})=>{if(typeof data.result?.score==='number')item.scores.push(data.result.score);});
                      const send=this.postMessage.bind(this);this.postMessage=(message,...rest)=>{item.types.push(message.type);return send(message,...rest);};
                      const stop=this.terminate.bind(this);this.terminate=()=>{item.terminated=true;return stop();};}
                  };
                })();''')
                page.goto(f'http://127.0.0.1:{server.server_port}/index.html',wait_until='domcontentloaded')
                assert page.evaluate('crossOriginIsolated') is False
                assert page.evaluate('typeof SharedArrayBuffer')=='undefined'
                report['checks'].append('non-isolated page, no SharedArrayBuffer')
                card=page.locator('.ctm-stack[data-backend="maxima"]').first
                control=page.locator('.ctm-stack[data-backend="sympy"] .stack-answer').first
                if control.count():control.fill('x+1')
                card.locator('.stack-answer').wait_for()
                data=json.loads(card.locator('.ctm-stack-data').text_content())
                page.wait_for_function('el=>!!el.dataset.stackVariantId',arg=card.element_handle())

                def selected():
                    identity=card.get_attribute('data-stack-variant-id')
                    return next(row for row in data['variants'] if row['id']==identity)

                def answer(text,state,grade=None):
                    card.locator('.stack-answer').fill(text)
                    card.locator('.stack-validate').click()
                    card.locator('.stack-result[data-state="'+state+'"]').wait_for(timeout=180000)
                    if grade:
                        card.locator('.stack-check').click()
                        card.locator('.stack-result[data-state="'+('correct' if grade=='correct' else 'retry')+'"]').wait_for(timeout=60000)
                        expected={'correct':1,'partial':.5,'incorrect':0}[grade]
                        assert page.evaluate('nativeWorkers.filter(w=>w.url.includes("card-worker.js")).at(-1).scores.at(-1)')==expected

                answer(selected()['plan']['teachers']['ans']['source'],'valid','correct')
                report['checks'].append('native teacher validates and earns full marks')
                env=selected()['plan']['env']
                answer('(x+'+env['a']+')*(x+'+env['b']+')','valid','partial')
                report['checks'].append('equivalent factored response earns partial marks')
                answer('0','valid','incorrect')
                report['checks'].append('wrong response earns zero')
                for source in ['load("evil")','block([x],x:1)','1.2']:
                    answer(source,'invalid')
                    assert card.locator('.stack-check').is_disabled()
                answer(selected()['plan']['teachers']['ans']['source'],'valid','correct')
                report['checks'].append('forbidden calls, assignment and floats rejected; valid response recovers')
                card.locator('.stack-tests').click()
                page.wait_for_function('el=>el.textContent.includes("All question tests passed")',arg=card.locator('.stack-result').element_handle(),timeout=60000)
                assert 'undefined' not in card.locator('.stack-result').inner_text()
                report['checks'].append('all XML tests pass with the correct seed labels')
                if len(data['variants'])>1:
                    old_id=selected()['id']
                    page.once('dialog',lambda dialog:dialog.accept())
                    card.locator('.stack-new-variant').click()
                    page.wait_for_function('({el,id})=>el.dataset.stackVariantId!==id',arg={'el':card.element_handle(),'id':old_id})
                    answer(selected()['plan']['teachers']['ans']['source'],'valid','correct')
                    workers=page.evaluate('nativeWorkers.filter(w=>w.url.includes("card-worker.js"))')
                    assert len(workers)>=2 and workers[-2]['terminated'],workers
                    report['checks'].append('variant change retires the old heap and grades in a new worker')
                assert not errors,errors
                if control.count():
                    assert control.input_value()=='x+1'
                    report['checks'].append('native operations preserve the other backend card answers')
                assert not any('pyodide.asm' in url or url.endswith('.whl') for url in requests)
                report['checks'].append('no page errors, Pyodide VM or checker-wheel download')
                report.update(browser=browser.version,workers=page.evaluate('nativeWorkers'),passed=True)
            finally:browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'checks':report['checks']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--browser',choices=('chromium','firefox','webkit'),default='chromium')
    parser.add_argument('--executable')
    args=parser.parse_args()
    run(args.project,args.output,engine=args.browser,executable=args.executable)
