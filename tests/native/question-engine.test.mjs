// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
const {Engine,testAnswerNote,casttext}=createRequire(import.meta.url)('../../_extensions/ctm-stack/native/question-engine.js');

test('question test notes use ordered subsequences with explicit anchoring',()=>{
  for(const [expected,actual,passed] of [
    ['end',['start','end'],true],['start',['start','end'],false],
    ['start | end',['AT note','start','intermediate','end'],true],
    ['[ start | end ]',['AT note','start','end'],false],
    ['( start )',['AT note','start','end'],true],
    ['[ start | end ]',['start','end'],true],
    ['end | start',['start','end'],false],['a | a',['a'],false],
    ['()',['anything'],true],['NULL',[],true],['NULL',['x'],false],['',[],false],
  ])assert.equal(testAnswerNote(expected,actual),passed,JSON.stringify([expected,actual]));
});

test('six equally weighted full marks remain exactly full marks',async()=>{
  const prts=Array.from({length:6},(_,i)=>({name:'p'+i,value:1}));
  const compiled={prts:Object.fromEntries(prts.map(p=>[p.name,{sig:p.name+'()'}])),statics:{}};
  const question={prts,native:{compiled}};
  let fractions=[1,1,1,1,1,1];
  const engine=new Engine(async()=>Object.fromEntries(prts.map((p,i)=>[p.name,[[],fractions[i],0,'',[]]])));
  // Isolate the weighted grade contract from the separately qualified native
  // validation/emission path. These are the actual five-element PRT results.
  engine.validate=async()=>({status:'valid',inputs:{}});
  engine.admit=()=>({admitted:{}});engine.program=()=>'';
  assert.equal((await engine.grade(question,{},{})).score,1);
  fractions=[1,1,1,0,0,0];
  assert.equal((await engine.grade(question,{},{})).score,.5);
  fractions=[1,1,1,1,1,0];
  const partial=(await engine.grade(question,{},{})).score;
  assert.ok(partial<1&&Math.abs(partial-5/6)<1e-15);
});

test('Python feedback bypasses CASText marker expansion and is escaped once',()=>{
  const compiled={statics:{'//compiler-marker//':'author text'}};
  assert.equal(casttext('QMCHAR',compiled),'QMCHAR');
  const result=casttext(['%root','//compiler-marker// QMCHAR ',
    ['%root',['ctm_python_feedback','QMCHAR //compiler-marker// <plain> &lt;']]],compiled);
  assert.equal(result,'author text ? QMCHAR //compiler-marker// &lt;plain&gt; &amp;lt;');
});
