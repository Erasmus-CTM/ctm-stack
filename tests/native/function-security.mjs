// SPDX-License-Identifier: AGPL-3.0-or-later
// Execute accepted data and rejected dynamic function rewrites in owned v3.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {compileIR} from '../../_extensions/ctm-stack/native/author-compiler.mjs';
import {NodeMaximaSession} from '../../_extensions/ctm-stack/native/node-session.mjs';
const require=createRequire(import.meta.url),{Engine}=require('../../_extensions/ctm-stack/native/question-engine.js');
const STACK=require('../../_extensions/ctm-stack/native/stack-pin.js');
const [root,output]=process.argv.slice(2),session=new NodeMaximaSession(root);
const engine=new Engine(s=>session.evaluate(s),{stackCommit:STACK});
async function execute(variables){
  const question={variables,simplify:true,inputs:[],prts:[],qtests:[],questiontext:'',generalfeedback:'',specificfeedback:'',questionnote:''};
  question.native={schema:1,stackRevision:STACK,questionHash:'a'.repeat(64),compiled:compileIR(question)};
  const result=await engine.prepare(question,1);
  return result.env;
}
const cases=[];
try{
  await session.start();
  for(const label of ['none','red','true','real','all','max','e','eval_string_lisp']){
    const actual=await execute(`s:["${label}"];a:map(lambda([t],t),s);b:subst("${label}",x,x);c:ev("${label}");`);
    assert.match(actual.a,new RegExp(label));assert.match(actual.b,new RegExp(label));
    cases.push({id:'data/'+label,passed:true});
  }
  const algebra=await execute('a:subst(2,x,x^2+1);b:subst(cos,sin,sin(x));c:substinpart(2,x+1,1);');
  assert.equal(algebra.a,'5');assert.equal(algebra.b,'cos(x)');cases.push({id:'mathematical-substitution',passed:true});
  for(const source of [
    'f:sin;g:eval_string_lisp;a:subst(g,f,sin("(+ 20 22)"));',
    'f:sin;a:subst("eval_string_lisp",f,sin("(+ 20 22)"));',
    'f:[sin];g:[eval_string_lisp];a:subst(first(g),first(f),sin("(+ 20 22)"));',
    'f:sin;a:subst("rand",f,sin(5));',
  ]){
    await assert.rejects(()=>execute(source));cases.push({id:'dynamic-rewrite/'+cases.length,passed:true});
  }
  assert.equal((await execute('a:40+2;')).a,'42');
  await fs.writeFile(output,JSON.stringify({passed:true,cases},null,2)+'\n');
}finally{await session.stop();}
