// SPDX-License-Identifier: AGPL-3.0-or-later
// Page-side owner of a sealed, non-isolated native worker. Failed requests are
// never replayed; a new question/variant always starts with a fresh Wasm heap.
(function(root){
  'use strict';
  const registry=root.CTMStackAdapters=root.CTMStackAdapters||{};
  registry.maxima=function(descriptor){
    let child,ready,key,lastRequest,python,epoch=0,sequence=0,lastCheck=0;
    const pending=new Map();
    const fault=(message,code='maxima-runtime')=>Object.assign(new Error(message),{kind:'runtime',code});
    function retire(reason){
      epoch++;const old=child;child=null;ready=null;key=null;lastCheck=0;
      for(const item of pending.values()){clearTimeout(item.timer);item.reject(reason instanceof Error?reason:fault(String(reason)));}
      pending.clear();old?.terminate();
      if(python){python.terminate(reason);python=null;}
    }
    function rpc(message,timeout){
      return new Promise((resolve,reject)=>{
        const id=++sequence;
        const timer=setTimeout(()=>retire(fault(message.type==='init'?'Maxima loading timed out':'Maxima calculation timed out',message.type==='init'?'maxima-load-timeout':'maxima-call-timeout')),timeout);
        pending.set(id,{resolve,reject,timer,type:message.type});
        try{child.postMessage({...message,id});}catch(error){retire(fault(error.message||'Native worker could not accept the request'));}
      });
    }
    async function prepareRequest(request){
      lastRequest=request;
      const identity=JSON.stringify([request.question?.native?.questionHash,request.variant?.questionHash,request.variant?.seed,request.variant?.n,request.variant?.id,request.variant?.hash]);
      if(ready&&key===identity)return ready;
      retire('Native question or variant changed');key=identity;
      const current=epoch;
      const base=root.CTMStackNativeAssets,checker=root.CTMCheckersStack;
      if(!base||!checker?.scriptURL)throw fault('Native runtime assets or shared admission are missing on this page');
      child=new Worker(new URL('card-worker.js',base));
      child.onmessage=({data})=>{
        if(current!==epoch)return;
        if(data?.type==='python-check'){
          const item=pending.get(data.id),request=data.request;
          const testResults=request?.operation==='test-results';
          if(!item||!['grade','tests'].includes(item.type)||!Number.isSafeInteger(data.call)||data.call!==lastCheck+1||!python
            ||request?.backend!=='maxima'||(testResults
              ?item.type!=='tests'||JSON.stringify(request.tests)!==JSON.stringify(lastRequest.question.authored_tests)
              :request.checker!==(lastRequest.question.checker||'')||request.variant?.id!==(lastRequest.variant.id||'seed='+lastRequest.variant.seed)
                ||request.variant.n!==(lastRequest.variant.n??null)||request.variant.hash!==lastRequest.variant.hash)){
            retire(fault('Malformed or stale PythonChecker continuation'));return;
          }
          lastCheck=data.call;
          Promise.resolve(root.MathExerciseRuntime.callCheckers(python,testResults?'stack.test-results':'stack.check',request,root.CTMCheckersStack)).then(reply=>{
            if(current!==epoch||!pending.has(data.id))return;
            const result=typeof reply==='string'?JSON.parse(reply):reply;
            child.postMessage({id:data.id,call:data.call,type:'python-result',ok:result.ok,
              result:result.result,error:result.errorDetail||{kind:'author',message:result.error||'Python checker failed'}});
          }).catch(error=>{if(current===epoch)retire(fault(error.message||'Python checker runtime failed'));});
          return;
        }
        if(!data||typeof data!=='object'||typeof data.ok!=='boolean'){
          retire(fault('Malformed native worker response'));return;
        }
        const item=pending.get(data.id);
        if(!item){retire(fault('Unexpected native worker response'));return;}
        clearTimeout(item.timer);pending.delete(data.id);
        if(data.ok===true)item.resolve(data.result);
        else{
          if(!data.error||!['author','runtime'].includes(data.error.kind)||typeof data.error.message!=='string'){
            item.reject(fault('Malformed native worker error'));retire(fault('Malformed native worker error'));return;
          }
          const error=Object.assign(new Error(data.error?.message||'Native worker failed'),data.error||{});
          item.reject(error);
          if(data.poisoned)retire(error);
        }
      };
      child.onerror=event=>{if(current===epoch)retire(fault(event.message||'Native worker failed'));};
      const native=rpc({type:'init',baseURL:new URL('runtime-v3/',base).href,packageHash:descriptor.runtimeHash,
        checkerURL:checker.scriptURL,question:request.question,variant:request.variant},180000);
      const checked=async()=>{
        if(!request.question.native.python)return;
        const R=root.MathExerciseRuntime,W=root.CTMWorker;
        if(!R||!W)throw fault('Python checker assets are missing');
        if(root.CTMCheckers?.sha256!==request.question.native.pythonBaseWheelSha256)throw fault('Native checker plan and base Python wheel differ');
        let timer;
        const loading=(async()=>{
          const py=await W.start({indexURL:R.indexURL,publish:false,loadTimeout:R.loadTimeout});
          const live=()=>{if(current!==epoch){py.terminate('Native checker startup superseded');throw fault('Native checker startup superseded');}};
          live();python=py;
          await py.loadPackage('sympy');live();
          await R.ensureCheckers(py,checker);live();
        })();
        const limit=new Promise((_,reject)=>{timer=setTimeout(()=>reject(fault('Python checker loading timed out','python-checker-load-timeout')),R.loadTimeout);});
        try{await Promise.race([loading,limit]);}finally{clearTimeout(timer);}
      };
      ready=Promise.all([native,checked()]).catch(error=>{
          if(current===epoch)retire(error);throw error;
        });
      return ready;
    }
    return {
      isolationRequired:false,
      start:async()=>{},
      prepareRequest,
      request:async request=>{
        try{
          await prepareRequest(request);
          if(!['validate','grade','tests'].includes(request.type))throw fault('Unknown native card request');
          return {ok:true,result:await rpc({type:request.type,answers:request.answers||{}},30000)};
        }catch(error){return {ok:false,error:{kind:error.kind==='author'?'author':'runtime',code:error.code||'maxima-card',message:String(error.message||error),restarted:false}};}
      },
      stop:async reason=>{retire(reason||'Stopped by the learner');return {restarted:false};},
      restart:async reason=>{const request=lastRequest;retire(reason||'Native runtime restart');if(request)await prepareRequest(request);}
    };
  };
})(globalThis);
