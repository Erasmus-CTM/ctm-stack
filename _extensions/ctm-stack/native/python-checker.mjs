// SPDX-License-Identifier: AGPL-3.0-or-later
// One supervised host CPython process per question; H1 namespaces stay fresh.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

export function pythonChecker(configuration){
  let child,ready,resolveReady,rejectReady,active,timer,closed=false,sequence=0,buffer=Buffer.alloc(0),errors='';
  let chain=Promise.resolve();
  const fault=(message,code='python-checker-runtime')=>Object.assign(new Error(message),{kind:'runtime',code});
  function retire(error){
    if(closed)return;closed=true;clearTimeout(timer);child?.kill('SIGKILL');
    rejectReady?.(error);if(active){active.reject(error);active=null;}
  }
  function bound(){clearTimeout(timer);timer=setTimeout(()=>retire(fault('Python checker exceeded its deadline','python-checker-timeout')),10000);}
  function message(reply){
    if(!ready||closed)return;
    if(resolveReady){
      if(reply?.type!=='ready'||!Array.isArray(reply.version)||typeof reply.sympyVersion!=='string')throw fault('Malformed Python checker identity');
      clearTimeout(timer);const resolve=resolveReady;resolveReady=null;rejectReady=null;resolve({version:reply.version,sympyVersion:reply.sympyVersion});return;
    }
    if(!active||reply?.id!==active.id||typeof reply.ok!=='boolean')throw fault('Malformed or stale Python checker envelope');
    clearTimeout(timer);const current=active;active=null;
    if(reply.ok)current.resolve(reply.result);
    else current.reject(Object.assign(new Error(reply.errorDetail?.message||reply.error||'Python checker failed'),reply.errorDetail||{kind:'author'}));
  }
  function start(){
    if(closed)return Promise.reject(fault('Python checker has been retired'));
    if(ready)return ready;
    ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
    child=spawn(configuration.executable||'python3',['-I',fileURLToPath(new URL('./python-checker.py',import.meta.url))],{stdio:['pipe','pipe','pipe']});
    bound();
    child.on('error',error=>retire(fault(error.message)));
    child.on('close',()=>retire(fault('Python checker process stopped: '+errors.slice(-4000))));
    child.stdin.on('error',error=>retire(fault(error.message)));
    child.stderr.on('data',chunk=>{errors+=chunk.toString();if(errors.length>2*1024*1024)retire(fault('Python checker diagnostics exceed their bound'));});
    child.stdout.on('data',chunk=>{
      buffer=Buffer.concat([buffer,chunk]);
      try{
        if(buffer.length>2*1024*1024)throw fault('Python checker output exceeds its bound');
        let at;while((at=buffer.indexOf(10))>=0){
          const line=buffer.subarray(0,at);buffer=buffer.subarray(at+1);
          let reply;try{reply=JSON.parse(line.toString());}catch{throw fault('Python checker returned malformed JSON');}
          message(reply);
        }
      }catch(error){retire(error);}
    });
    child.stdin.write(JSON.stringify({paths:configuration.paths})+'\n');
    return ready;
  }
  const run=request=>{
    const result=chain.then(async()=>{
      await start();
      if(closed)throw fault('Python checker has been retired');
      return new Promise((resolve,reject)=>{
        const id=++sequence;active={id,resolve,reject};bound();
        const encoded=JSON.stringify({id,request})+'\n';
        if(Buffer.byteLength(encoded)>2*1024*1024){retire(fault('Python checker request exceeds its bound'));return;}
        child.stdin.write(encoded);
      });
    });
    chain=result.catch(()=>{});return result;
  };
  run.identity=start;run.stats=()=>({processes:child?1:0,calls:sequence});
  run.close=async()=>{if(!child||child.exitCode!==null||child.signalCode!==null){closed=true;return;}const ended=new Promise(resolve=>child.once('close',resolve));retire(fault('Python checker closed'));await ended;};
  return run;
}
