// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {pythonChecker} from '../../_extensions/ctm-stack/native/python-checker.mjs';

// Fake only the subprocess protocol, retaining the real supervisor, pipes,
// process retirement and fixed deadline. Actual H1 execution is integration-tested.
async function processFor(t,body){
  const folder=await fs.mkdtemp(path.join(os.tmpdir(),'native-python-protocol-'));
  t.after(()=>fs.rm(folder,{recursive:true,force:true}));
  const executable=path.join(folder,'checker');
  await fs.writeFile(executable,'#!'+process.execPath+'\n'+body,{mode:0o700});
  return pythonChecker({executable,paths:[]});
}
test('checker protocol keeps normalized results and author errors distinct',async t=>{
  const success=await processFor(t,'process.stdout.write(JSON.stringify({ok:true,result:{valid:true,score:.5,status:"partial"}}))');
  assert.deepEqual(await success({}),{valid:true,score:.5,status:'partial'});
  const failure=await processFor(t,'process.stdout.write(JSON.stringify({ok:false,errorDetail:{kind:"author",code:"custom-checker",message:"Bad checker"}}))');
  await assert.rejects(failure({}),{kind:'author',code:'custom-checker',message:'Bad checker'});
});
test('malformed replies, oversized output and failed startup are runtime errors',async t=>{
  for(const body of ['process.stdout.write("not JSON")','process.stdout.write("null")',
    'process.stdout.write("x".repeat(2*1024*1024+1))']){
    const run=await processFor(t,body);
    await assert.rejects(run({}),{kind:'runtime'});
  }
  await assert.rejects(pythonChecker({executable:'/no-such-ctm-python',paths:[]})({}),{kind:'runtime'});
});
test('a runaway checker is killed at the fixed deadline without replay',async t=>{
  const run=await processFor(t,'setInterval(()=>{},1000)');
  const started=Date.now();
  await assert.rejects(run({}),{kind:'runtime',code:'python-checker-timeout'});
  assert.ok(Date.now()-started>=9900&&Date.now()-started<20000);
});
