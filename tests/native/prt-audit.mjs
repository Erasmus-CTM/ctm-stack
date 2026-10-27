// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {NodeMaximaSession} from '../../_extensions/ctm-stack/native/node-session.mjs';
const [root,input,output]=process.argv.slice(2);
const rows=JSON.parse(await fs.readFile(input));
const session=new NodeMaximaSession(root),report={schema:1,cases:[],passed:false};
try {
  report.identity=await session.start();
  for(const row of rows) {
    const actual=await session.evaluate(row.expression),expected=row.expected;
    try {
      assert.equal(actual.length,5,row.id);
      assert.ok(Math.abs(actual[1]-expected.score)<1e-12,'Score '+row.id+': '+actual[1]+' vs '+expected.score);
      assert.ok(Math.abs(actual[2]-expected.penalty)<1e-12,'Penalty '+row.id);
      assert.deepEqual(actual[4],expected.notes,'Notes '+row.id);
      assert.deepEqual(actual[0].map(p=>p[2]),expected.visited,'Visited path '+row.id);
      report.cases.push({id:row.id,matched:true});
    } catch(error) {report.cases.push({id:row.id,matched:false,expected,actual,message:error.message});}
  }
  report.passed=report.cases.every(c=>c.matched);
  assert.ok(report.passed,'Independent PRT audit found '+report.cases.filter(c=>!c.matched).length+' mismatch(es)');
} finally {
  await session.stop();await fs.mkdir(path.dirname(output),{recursive:true});
  await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');
}
