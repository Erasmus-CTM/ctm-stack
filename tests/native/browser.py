"""Real direct-call v3 replay without COOP/COEP or a SharedArrayBuffer."""
import argparse
import functools
import gzip
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def run(runtime, output, executable=None, engine='chromium'):
    runtime = runtime.resolve()
    spec = (runtime / 'package.json').read_bytes()
    expected_hash = hashlib.sha256(spec).hexdigest()
    programs = json.loads(gzip.decompress((ROOT / 'tests/native/accepted-programs.json.gz').read_bytes()))['programs']
    report = {'schema': 1, 'programs': [], 'packageHash': expected_hash, 'passed': False}
    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, name):
            parts = name.split('?', 1)[0].split('/')
            if '..' in parts: return '/missing'
            if parts[1] == 'package': return str(runtime.joinpath(*parts[2:]))
            if parts[1] == 'native': return str((ROOT / '_extensions/ctm-stack/native').joinpath(*parts[2:]))
            return super().translate_path(name)
        def log_message(self, *args): pass
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, 'index.html').write_text('<!doctype html><title>Native transport qualification</title>')
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=directory))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as p:
                browser = getattr(p, engine).launch(**({'executable_path': executable} if executable else {}))
                page = browser.new_page(); page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
                report['browser'] = browser.version
                assert page.evaluate('crossOriginIsolated') is False
                assert page.evaluate('typeof SharedArrayBuffer') == 'undefined'
                page.evaluate('''() => {
                  window.child = new Worker('/native/browser-worker.js');
                  let sequence=0; const pending=new Map();
                  child.onmessage=({data})=>{const p=pending.get(data.id);if(p){clearTimeout(p.timer);pending.delete(data.id);p.resolve(data);}};
                  child.onerror=event=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error(event.message));}pending.clear();};
                  window.call=(data)=>new Promise((resolve,reject)=>{
                    const id=++sequence;
                    const timer=setTimeout(()=>{pending.delete(id);child.terminate();reject(new Error('Native test watchdog'));},180000);
                    pending.set(id,{resolve,reject,timer});child.postMessage({...data,id});
                  });
                }''')
                initialized = page.evaluate('(hash)=>call({type:"init",baseURL:"/package/",packageHash:hash})', expected_hash)
                assert initialized['ok'], initialized
                for index, row in enumerate(programs):
                    actual = page.evaluate('(expression)=>call({type:"evaluate",expression})', row['expression'])
                    assert actual['ok'] and actual['result'] == row['expected'], (index, actual)
                    report['programs'].append({'index': index, 'exact': True})
                value = page.evaluate('(expression)=>call({type:"evaluate",expression})', '"æøå−π😀"')
                assert value['ok'] and value['result'] == 'æøå−π😀', value
                error = page.evaluate('(expression)=>call({type:"evaluate",expression})', 'error("intentional domain error")')
                assert not error['ok'] and error['error']['kind'] == 'cas' and not error['poisoned'], error
                assert page.evaluate('()=>call({type:"evaluate",expression:"6*7"})')['result'] == 42
                report.update(nonIsolated=True, sharedArrayBuffer=False, casErrorRecovery=True, passed=True)
                page.evaluate('child.terminate()'); browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--executable')
    parser.add_argument('--browser', choices=('chromium', 'firefox', 'webkit'), default='chromium')
    args = parser.parse_args()
    run(args.runtime, args.output, args.executable, args.browser)
