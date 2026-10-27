// SPDX-License-Identifier: AGPL-3.0-or-later
import fs from 'node:fs/promises';
import {NodeMaximaSession} from '../../../_extensions/ctm-stack/native/node-session.mjs';
const [root, inputFile, compiledFile, outputFile] = process.argv.slice(2);
const input = JSON.parse(await fs.readFile(inputFile));
const upstream = JSON.parse(await fs.readFile(compiledFile));
const report = {schema: 1, cases: [], replacements: [], passed: false};
const session = new NodeMaximaSession(root);
try {
  report.identity = await session.start();
  for (const row of upstream.castext) {
    if (row.error) {report.replacements.push(row); continue;}
    const value = await session.evaluate(row.expression);
    report.replacements.push({id: row.id, value, map: row.map});
  }
  const compiled = new Map(upstream.graphs.map(g => [g.id, g.compiled]));
  for (const row of input.cases) {
    const program = compiled.get(row.graph);
    const members = row.verdicts.flatMap((v, n) => v ? [n] : []).join(',');
    // Stub only the mathematical truth of the test. Graph traversal, scoring,
    // clipping, penalty, path and notes all execute upstream-generated code.
    const expression = 'block([ctm_verdicts:{'+members+'}],local(ATAlgEquiv,prt_audit),'+
      'ATAlgEquiv(s,t):=[true,member(s,ctm_verdicts),string(s),""],'+
      program.def+','+program.sig+')';
    try {
      const actual = await session.evaluate(expression);
      const expected = row.expected;
      const visited = actual[0].map(p => p[2]);
      const matched = Math.abs(actual[1]-expected.score) < 1e-12 &&
        Math.abs(actual[2]-expected.penalty) < 1e-12 &&
        JSON.stringify(actual[4]) === JSON.stringify(expected.notes) &&
        JSON.stringify(visited) === JSON.stringify(expected.visited);
      report.cases.push({id: row.id, matched, ...(matched ? {} : {actual, expected})});
    } catch(error) {report.cases.push({id: row.id, matched: false, error: error.message});}
    if (report.cases.length % 256 === 0) console.error('Upstream PRT audit '+report.cases.length+'/'+input.cases.length);
  }
  report.passed = report.cases.every(c => c.matched);
} finally {
  await session.stop();
  await fs.writeFile(outputFile, JSON.stringify(report, null, 2)+'\n');
}
console.log(JSON.stringify({cases: report.cases.length,
  mismatches: report.cases.filter(c => !c.matched).length, passed: report.passed}));
