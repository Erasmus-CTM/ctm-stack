// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {pythonChecker} from '../../_extensions/ctm-stack/native/python-checker.mjs';
async function processFor(t,body){
  const folder=await fs.mkdtemp(path.join(os.tmpdir(),'native-python-protocol-'));t.after(()=>fs.rm(folder,{recursive:true,force:true}));
  const executable=path.join(folder,'checker');
  const program=`const rl=require('node:readline').createInterface({input:process.stdin});let initialized=false;
    const send=value=>process.stdout.write(JSON.stringify(value)+'\\n');
    rl.on('line',line=>{const message=JSON.parse(line);if(!initialized){initialized=true;send({type:'ready',version:[3,12,0],sympyVersion:'1.13.3'});return;}${body}});`;
  await fs.writeFile(executable,'#!'+process.execPath+'\n'+program,{mode:0o700});
  const run=pythonChecker({executable,paths:[]});t.after(()=>run.close());return run;
}
test('one checker process serves multiple calls and retains author/runtime distinctions',async t=>{
  const run=await processFor(t,`if(message.request.fail)send({id:message.id,ok:false,errorDetail:{kind:'author',message:'Bad checker'}});
    else send({id:message.id,ok:true,result:{valid:true,score:.5,status:'partial',pid:process.pid}});`);
  assert.deepEqual(await run.identity(),{version:[3,12,0],sympyVersion:'1.13.3'});
  const first=await run({});await assert.rejects(run({fail:true}),{kind:'author',message:'Bad checker'});
  const second=await run({});assert.equal(first.pid,second.pid);assert.equal(second.score,.5);
});
test('malformed, stale and oversized replies retire without replay',async t=>{
  for(const body of ['process.stdout.write("not JSON\\n")','send(null)',
    'process.stdout.write("x".repeat(2*1024*1024+1))',
    'send({id:message.id+1,ok:true,result:{}})']){
    const run=await processFor(t,body);await assert.rejects(run({}),{kind:'runtime'});
    await assert.rejects(run({}),{kind:'runtime'});
  }
  const run=pythonChecker({executable:'/no-such-ctm-python',paths:[]});
  await assert.rejects(run({}),{kind:'runtime'});await run.close();
});
test('a runaway checker is killed at the fixed deadline without replay',async t=>{
  const run=await processFor(t,'while(true){}');const started=Date.now();
  await assert.rejects(run({}),{kind:'runtime',code:'python-checker-timeout'});
  assert.ok(Date.now()-started>=9900&&Date.now()-started<20000);
  await assert.rejects(run({}),{kind:'runtime'});
});
