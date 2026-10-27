// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {NodeMaximaSession} from '../../_extensions/ctm-stack/native/node-session.mjs';
const {quote}=createRequire(import.meta.url)('../../_extensions/ctm-stack/native/question-engine.js');
const [root,input,output]=process.argv.slice(2),fixture=JSON.parse(await fs.readFile(input));
const session=new NodeMaximaSession(root),report={schema:1,passed:false,cases:[]};
try{
  report.identity=await session.start();
  for(const row of fixture.rows){
    const compiled=row.compiled;
    const yes=row.verdicts.flatMap((v,n)=>v?[n]:[]).join(',');
    const program=call=>'block([ans:1,fpprintprec:12,ctm_verdicts:{'+yes+'}],local(ATAlgEquiv,ctm_prt_audit),'+
      'ATAlgEquiv(s,t):=[true,member(s,ctm_verdicts),string(s),""],'+compiled.def+','+call+')';
    let raw=await session.evaluate(program(compiled.sig)),calls=0;const seen=new Set();
    while(raw[0]==='CTM_PYTHON'){
      assert.ok(row.pythonNodes.includes(raw[1]));assert.equal(raw[3],row.expectedTans);
      assert.ok(!raw[2].includes(row.expectedTans),'Feedback variables must be re-evaluated, never restored from display text');
      assert.ok(!seen.has(raw[1]),'A suspended node must run once');seen.add(raw[1]);calls++;
      assert.ok(calls<=row.pythonNodes.length);
      const call='ctm_prt_audit(ans,'+quote(raw[2])+',['+String(row.verdicts[Number(raw[1])])+',""])';
      raw=await session.evaluate(program(call));
    }
    assert.equal(calls,row.expected.visited.filter(n=>row.pythonNodes.includes(n)).length,'Skipped Python nodes must not be called');
    assert.equal(raw[1],row.expected.score);assert.equal(raw[2],row.expected.penalty);
    assert.deepEqual(raw[4],row.expected.notes);
    report.cases.push({id:row.id,passed:true,callbacks:calls});
  }
  report.passed=true;
}finally{await session.stop();await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({passed:report.passed,cases:report.cases.length}));
