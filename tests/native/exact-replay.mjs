// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {NodeMaximaSession} from '../../_extensions/ctm-stack/native/node-session.mjs';
const require=createRequire(import.meta.url),{Engine}=require('../../_extensions/ctm-stack/native/question-engine.js');
const STACK=require('../../_extensions/ctm-stack/native/stack-pin.js');
const [root,output]=process.argv.slice(2),session=new NodeMaximaSession(root);
const question={simplify:true,inputs:[],native:{schema:1,stackRevision:STACK,questionHash:'a'.repeat(64),compiled:{
  prts:{},variables:{references:{write:{fpprintprec:true,a:true,b:true}},
    statement:"(fpprintprec:12,a:1/3.0,b:'((x+1)^2),true)"},inputTeachers:{},texts:{},math:'[]',grading:'[\"stack_map\"]',testInputs:'[]',authoredInputs:'[]'}}};
const variant={schema:1,questionHash:question.native.questionHash,seed:1,
  env:{fpprintprec:'12',a:'0.333333333333',b:'expanded_or_rounded_placeholder'}};
const engine=new Engine(s=>session.evaluate(s),{stackCommit:STACK});
try{
  await session.start();
  const actual=await session.evaluate(engine.program(question,variant,[
    '["stack_map",["precision",is(a=1/3.0)],["structure",is(string(b)=string(\'((x+1)^2)))]]']));
  assert.deepEqual(actual,{precision:true,structure:true});
  const prepared=await engine.prepare({...question,qtests:[]},1);
  assert.equal(prepared.env.fpprintprec,'12','Printing must not shadow a variable being serialized');
  assert.equal(prepared.env.a,'0.3333333333333333');
  await fs.writeFile(output,JSON.stringify({passed:true,fpprintprec:12,source:'1/3.0',serialization:prepared.env,actual},null,2)+'\n');
}finally{await session.stop();}
