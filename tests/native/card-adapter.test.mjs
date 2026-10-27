// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const code=await fs.readFile(new URL('../../_extensions/ctm-stack/backends/maxima.js',import.meta.url),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(overrides={}){
  const workers=[],timers=new Map();let timer=0;
  class Worker {
    constructor(url){this.url=String(url);this.sent=[];workers.push(this);}
    postMessage(message){this.sent.push(message);}
    terminate(){this.terminated=true;}
    reply(message){this.onmessage({data:{id:this.sent.at(-1).id,...message}});}
  }
  const context={URL,Worker,CTMStackNativeAssets:'https://course.test/native/',
    CTMCheckersStack:{scriptURL:'https://course.test/checkers.js'},
    setTimeout(fn,ms){const id=++timer;timers.set(id,{fn,ms});return id;},
    clearTimeout(id){timers.delete(id);}};
  Object.assign(context,overrides);
  vm.runInNewContext(code,context);
  return {adapter:context.CTMStackAdapters.maxima({runtimeHash:'a'.repeat(64)}),workers,timers};
}
function request(seed=1){return {type:'grade',question:{native:{questionHash:'q'}},
  variant:{questionHash:'q',seed},answers:{ans:'x+1'}};}
async function initialize(probe,seed=1){
  const preparing=probe.adapter.prepareRequest(request(seed));
  probe.workers.at(-1).reply({ok:true,result:{ready:true}});await preparing;
}

test('variant changes retire the previous heap and never send raw programs',async()=>{
  const p=setup();await initialize(p);const old=p.workers[0];
  const response=p.adapter.request(request());await tick();
  assert.equal(old.sent.at(-1).type,'grade');
  assert.equal(old.sent.at(-1).expression,undefined);
  old.reply({ok:true,result:{score:1}});assert.equal((await response).result.score,1);
  await initialize(p,2);assert.equal(old.terminated,true);assert.equal(p.workers.length,2);
  assert.equal(p.workers[1].sent.length,1);
});

test('native Python continuations use a private runtime and are never replayed',async()=>{
  const py={loadPackage:async()=>{},runPythonAsync:async()=> '1.13.3',terminate(){this.terminated=true;}},calls=[];
  const p=setup({CTMCheckers:{sha256:'b'.repeat(64)},CTMWorker:{start:async options=>{assert.equal(options.publish,false);return py;}},
    MathExerciseRuntime:{loadTimeout:1000,indexURL:'/py/',ensureCheckers:async()=>{},
      callCheckers:async(runtime,operation,request)=>{calls.push({runtime,operation,request});return {ok:true,result:{valid:true,status:'correct',score:1}};}}});
  const req=request();Object.assign(req.question.native,{python:true,pythonBaseWheelSha256:'b'.repeat(64),pythonIdentity:{browserSympyVersion:'1.13.3'}});
  req.question.checker='def check(response, symbols): return True';
  const ready=p.adapter.prepareRequest(req),child=p.workers[0];child.reply({ok:true,result:{ready:true}});await ready;
  const outcome=p.adapter.request(req);await tick();
  const callback={id:child.sent.at(-1).id,type:'python-check',call:1,request:{backend:'maxima',checker:req.question.checker,variant:{n:null,id:'seed=1'}}};
  child.onmessage({data:callback});await tick();
  assert.equal(calls.length,1);assert.equal(calls[0].operation,'stack.check');assert.equal(calls[0].runtime,py);
  assert.equal(child.sent.at(-1).type,'python-result');
  // A duplicate callback is a protocol fault, not another Python invocation.
  child.onmessage({data:callback});
  assert.equal((await outcome).error.kind,'runtime');assert.equal(calls.length,1);
  assert.equal(child.terminated,true);assert.equal(py.terminated,true);
});

test('Stop retires loading and ignores late replies',async()=>{
  const p=setup(),loading=p.adapter.prepareRequest(request()),old=p.workers[0];
  const rejected=assert.rejects(loading,/Stopped/);
  await p.adapter.stop();await rejected;old.reply({ok:true,result:{ready:true}});
  assert.equal(old.terminated,true);await initialize(p,2);assert.equal(p.workers.length,2);
});

test('a changed or absent browser SymPy identity retires both heaps before grading',async()=>{
  for(const expected of ['1.13.3',undefined]){
    const py={loadPackage:async()=>{},runPythonAsync:async()=> 'different',terminate(){this.terminated=true;}};
    const p=setup({CTMCheckers:{sha256:'b'.repeat(64)},CTMWorker:{start:async()=>py},
      MathExerciseRuntime:{loadTimeout:1000,indexURL:'/py/',ensureCheckers:async()=>{}}});
    const req=request();Object.assign(req.question.native,{python:true,pythonBaseWheelSha256:'b'.repeat(64),pythonIdentity:{browserSympyVersion:expected}});
    const loading=p.adapter.prepareRequest(req);p.workers[0].reply({ok:true,result:{ready:true}});
    await assert.rejects(loading,error=>error.code==='python-checker-identity');
    assert.equal(py.terminated,true);assert.equal(p.workers[0].terminated,true);
    assert.equal(p.workers[0].sent.some(m=>m.type==='grade'),false);
  }
});

test('load timeout and calculation timeout are separate, with no automatic replay',async()=>{
  const p=setup(),loading=p.adapter.prepareRequest(request());
  const rejected=assert.rejects(loading,error=>error.code==='maxima-load-timeout');
  assert.equal([...p.timers.values()][0].ms,180000);
  [...p.timers.values()][0].fn();await rejected;assert.equal(p.workers[0].terminated,true);
  await initialize(p);const response=p.adapter.request(request());await tick();
  const calculation=[...p.timers.values()].find(t=>t.ms===30000);assert.ok(calculation);
  calculation.fn();const failure=await response;
  assert.equal(failure.error.code,'maxima-call-timeout');assert.equal(failure.error.restarted,false);
  assert.equal(p.workers.length,2);assert.equal(p.workers[1].sent.filter(m=>m.type==='grade').length,1);
});

test('author failure keeps the heap; internal failure retires it',async()=>{
  const p=setup();await initialize(p);const child=p.workers[0];
  const first=p.adapter.request(request());await tick();
  child.reply({ok:false,error:{kind:'author',message:'bad author expression'},poisoned:false});
  assert.equal((await first).error.kind,'author');assert.equal(child.terminated,undefined);
  const second=p.adapter.request(request());await tick();
  child.reply({ok:false,error:{kind:'runtime',message:'native failure'},poisoned:true});
  assert.equal((await second).error.kind,'runtime');assert.equal(child.terminated,true);
});

test('a stale response cannot satisfy the new worker generation',async()=>{
  const p=setup();await initialize(p);const old=p.workers[0];
  await initialize(p,2);const response=p.adapter.request(request(2));await tick();
  old.reply({ok:true,result:{score:99}});
  p.workers[1].reply({ok:true,result:{score:.5}});
  assert.equal((await response).result.score,.5);
});

test('malformed worker messages fail closed and retire the heap',async()=>{
  const p=setup(),loading=p.adapter.prepareRequest(request()),child=p.workers[0];
  const rejected=assert.rejects(loading,/Malformed/);
  child.onmessage({data:null});await rejected;
  assert.equal(child.terminated,true);await initialize(p,2);
});

test('a changed assigned identity replaces a sealed heap even for the same seed',async()=>{
  const p=setup();await initialize(p);const old=p.workers[0];
  const req=request();Object.assign(req.variant,{n:7,id:'seed=1',hash:'b'.repeat(16)});
  const loading=p.adapter.prepareRequest(req);
  assert.equal(old.terminated,true);assert.equal(p.workers.length,2);
  p.workers[1].reply({ok:true,result:{ready:true}});await loading;
});
