// SPDX-License-Identifier: AGPL-3.0-or-later
// Checker execution only. Mathematical preparation remains in native Maxima.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

export function pythonChecker(configuration){
  return request=>new Promise((resolve,reject)=>{
    const fail=(message,code='python-checker-runtime')=>Object.assign(new Error(message),{kind:'runtime',code});
    const child=spawn(configuration.executable||'python3',['-I',fileURLToPath(new URL('./python-checker.py',import.meta.url))],{stdio:['pipe','pipe','pipe']});
    const chunks=[];let bytes=0,errors='',settled=false;
    const finish=(error,result)=>{if(settled)return;settled=true;clearTimeout(timer);if(error)child.kill('SIGKILL');error?reject(error):resolve(result);};
    const timer=setTimeout(()=>{child.kill('SIGKILL');finish(fail('Python checker exceeded its deadline','python-checker-timeout'));},10000);
    child.on('error',error=>finish(fail(error.message)));
    child.stdout.on('data',chunk=>{bytes+=chunk.length;if(bytes>2*1024*1024){child.kill('SIGKILL');finish(fail('Python checker output exceeds its bound'));}else chunks.push(chunk);});
    child.stderr.on('data',chunk=>{errors+=chunk.toString();if(errors.length>2*1024*1024){child.kill('SIGKILL');finish(fail('Python checker diagnostics exceed their bound'));}});
    child.on('close',code=>{
      if(code!==0){finish(fail('Python checker process failed: '+errors.slice(-4000)));return;}
      try{
        let reply;
        try{reply=JSON.parse(Buffer.concat(chunks).toString());}
        catch{throw fail('Python checker returned malformed JSON');}
        if(!reply||typeof reply.ok!=='boolean')throw fail('Python checker returned a malformed envelope');
        if(reply.ok!==true)throw Object.assign(new Error(reply.errorDetail?.message||reply.error||'Python checker failed'),reply.errorDetail||{kind:'author'});
        finish(null,reply.result);
      }catch(error){finish(error);}
    });
    child.stdin.on('error',error=>finish(fail(error.message)));
    child.stdin.end(JSON.stringify({paths:configuration.paths,request}));
  });
}
