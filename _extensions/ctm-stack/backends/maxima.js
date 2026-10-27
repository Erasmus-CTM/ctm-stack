// SPDX-License-Identifier: AGPL-3.0-or-later
// Page-side owner of a sealed, non-isolated native worker. Failed requests are
// never replayed; a new question/variant always starts with a fresh Wasm heap.
(function(root){
  'use strict';
  const registry=root.CTMStackAdapters=root.CTMStackAdapters||{};
  registry.maxima=function(descriptor){
    let child,ready,key,lastRequest,epoch=0,sequence=0;
    const pending=new Map();
    const fault=(message,code='maxima-runtime')=>Object.assign(new Error(message),{kind:'runtime',code});
    function retire(reason){
      epoch++;const old=child;child=null;ready=null;key=null;
      for(const item of pending.values()){clearTimeout(item.timer);item.reject(reason instanceof Error?reason:fault(String(reason)));}
      pending.clear();old?.terminate();
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
      const identity=JSON.stringify([request.question?.native?.questionHash,request.variant?.questionHash,request.variant?.seed]);
      if(ready&&key===identity)return ready;
      retire('Native question or variant changed');key=identity;
      const current=epoch;
      const base=root.CTMStackNativeAssets,checker=root.CTMCheckersStack;
      if(!base||!checker?.scriptURL)throw fault('Native runtime assets or shared admission are missing on this page');
      child=new Worker(new URL('card-worker.js',base));
      child.onmessage=({data})=>{
        if(current!==epoch)return;
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
      ready=rpc({type:'init',baseURL:new URL('runtime-v3/',base).href,packageHash:descriptor.runtimeHash,
        checkerURL:checker.scriptURL,question:request.question,variant:request.variant},180000).catch(error=>{
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
