// SPDX-License-Identifier: AGPL-3.0-or-later
// Qualify the new ECL call boundary while collection occurs during calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {NodeMaximaSession} from '../../_extensions/ctm-stack/native/node-session.mjs';

const [root, input, output] = process.argv.slice(2);
const request = JSON.parse(await fs.readFile(input));
const targets = request.programs.filter(row => row.expression.includes('_ctm_s:eval_string("[1,1]")')
  && row.expression.includes('_ctm_t:eval_string("[2,2]")') && row.expression.includes(',startx,ans]'));
assert.equal(targets.length, 8);
assert.equal(request.programs.length, 327);
const session = new NodeMaximaSession(root, {gcFreeSpaceDivisor: 1000});
const report = {schema: 1, divisor: 1000, repetitions: 400, targets: targets.length,
  replayPrograms: request.programs.length, completedTargets: 0, completedReplay: 0, deviations: [], passed: false};
const started = performance.now();
async function checkpoint() {
  report.elapsedMs = performance.now() - started;
  await fs.mkdir(path.dirname(output), {recursive: true});
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({elapsedMs: report.elapsedMs, completedTargets: report.completedTargets,
    completedReplay: report.completedReplay, passed: report.passed}));
}
try {
  report.identity = await session.start();
  report.readyMs = performance.now() - started;
  report.before = await session.evaluate('ctm_gc_stats()');
  await checkpoint();
  for (let round = 0; round < 400; round++) {
    for (const row of targets) {
      assert.deepEqual(await session.evaluate(row.expression), row.expected, 'GC target result changed at round ' + round);
      report.completedTargets++;
    }
    if ((round + 1) % 10 === 0) await checkpoint();
  }
  for (const [index, row] of request.programs.entries()) {
    assert.deepEqual(await session.evaluate(row.expression), row.expected, 'GC replay result changed at program ' + index);
    report.completedReplay++;
    if ((index + 1) % 32 === 0) await checkpoint();
  }
  report.after = await session.evaluate('ctm_gc_stats()');
  report.collectionsDuringCalls = report.after[1] - report.before[1];
  assert.ok(report.collectionsDuringCalls > 0, 'Collection must actually occur during the measured calls');
  report.passed = true;
} catch (error) {
  report.deviations.push(error.message); throw error;
} finally {
  await session.stop(); await checkpoint();
}
