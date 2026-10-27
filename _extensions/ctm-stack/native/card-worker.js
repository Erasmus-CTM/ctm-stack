// SPDX-License-Identifier: AGPL-3.0-or-later
// One sealed question/variant per heap. Only typed card operations are exposed;
// raw Maxima/Lisp programs are never accepted from a card request.
'use strict';
importScripts('stack-pin.js','direct-runtime.js','browser-package.js','feedback.js','question-engine.js');
const send=self.postMessage.bind(self);
let configured=false,engine,session,question,variant,queue=Promise.resolve();
let active=0,sequence=0;
const checks=new Map();
function python(request){
  return new Promise((resolve,reject)=>{
    const call=++sequence;checks.set(call,{resolve,reject,id:active});
    send({id:active,type:'python-check',call,request});
  });
}
async function handle(message){
  active=message.id;
  try{
    let result;
    if(message.type==='init'){
      if(configured)throw new Error('Native card worker configuration is immutable');
      configured=true;
      const checker=new URL(message.checkerURL,self.location.href);
      if(checker.origin!==self.location.origin)throw new Error('Native admission must use the installed same-origin checker payload');
      importScripts(checker.href);
      if(!self.CTMCheckersStack?.admission||CTMCheckersStack.sha256!==message.question?.native?.checkerWheelSha256)throw new Error('Native plan and shared admission wheel differ');
      question=message.question;variant=message.variant;
      if(question.native.packageHash!==message.packageHash)throw new Error('Native plan and runtime package differ');
      engine=new CTMMaximaQuestions.Engine(expression=>session.evaluate(expression),CTMCheckersStack.admission,python);
      engine.check(question,variant);
      session=await CTMMaximaPackage.open(message);
      self.onmessage=receive;
      result={packageHash:session.packageHash||message.packageHash,maximaVersion:session.maximaVersion};
    }else{
      if(!engine||!session||!['validate','grade','tests'].includes(message.type))throw new Error('Unknown or uninitialized native card operation');
      const answers=message.answers;
      if(message.type!=='tests'&&(!answers||typeof answers!=='object'||Array.isArray(answers)||Object.values(answers).some(v=>typeof v!=='string')))throw new Error('Expected a named text-only answer mapping');
      result=message.type==='tests'?await engine.tests(question,variant):await engine[message.type](question,variant,answers);
    }
    send({id:message.id,ok:true,result});
  }catch(error){
    const kind=error.kind==='author'||error.kind==='cas'?'author':'runtime';
    send({id:message.id,ok:false,error:{kind,code:error.code||'maxima-card',message:String(error.message||error)},poisoned:kind==='runtime'});
  }
}
function receive({data}){
  if(data?.type==='python-result'){
    const check=checks.get(data.call);
    if(!check||check.id!==data.id||data.id!==active)return;
    checks.delete(data.call);
    if(data.ok===true)check.resolve(data.result);
    else check.reject(Object.assign(new Error(data.error?.message||'Python checker failed'),data.error||{kind:'runtime'}));
  }else queue=queue.then(()=>handle(data));
}
self.onmessage=receive;
