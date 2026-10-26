// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {NodeMaximaSession} from '../../_extensions/ctm-stack/native/node-session.mjs';
import {build} from '../../_extensions/ctm-stack/native/build-runner.mjs';
import {loadPackage} from '../../_extensions/ctm-stack/native/node-runtime.mjs';

const [root, replayFile, reportFile] = process.argv.slice(2);
if (!root || !replayFile || !reportFile) throw new Error('integration.mjs RUNTIME ACCEPTED-PROGRAMS REPORT');
const request = JSON.parse(await fs.readFile(replayFile));
assert.equal(request.programs.length, 327, '11 preparation + 316 controller programs are required');
const report = {schema: 1, node: process.versions.node, programs: [], lifecycle: {}};
const session = new NodeMaximaSession(root);
const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'ctm-native-'));
try {
  report.identity = await session.start();
  for (const [index, row] of request.programs.entries()) {
    const actual = await session.evaluate(row.expression);
    assert.deepEqual(actual, row.expected, 'Exact replay mismatch at program ' + index);
    report.programs.push({index, exact: true});
  }
  assert.equal(await session.evaluate('"æøå−π😀"'), 'æøå−π😀');
  await assert.rejects(session.evaluate('error("intentional domain error")'), error => error.kind === 'cas');
  assert.equal(await session.evaluate('6*7'), 42);
  report.lifecycle.casErrorRecovery = true;
  await assert.rejects(session.evaluate('?error("intentional internal condition")'), error => error.kind === 'runtime');
  await session.start(); assert.equal(await session.evaluate('6*7'), 42);
  report.lifecycle.internalFaultReplacement = true;
  await session.evaluate('ctm_private_sentinel:73');
  const originalChild = session.child;
  await session.restart('Isolation test');
  assert.notEqual(session.child, originalChild);
  assert.equal(await session.evaluate("is(ctm_private_sentinel='ctm_private_sentinel)"), true);
  report.lifecycle.freshHeapIsolation = true;
  // A long synchronous call cannot service postMessage. The parent must
  // terminate it, acknowledge termination, and start a fresh worker.
  session.callTimeout = 100;
  await assert.rejects(session.evaluate('block([],while true do 1)'), error => error.code === 'maxima-call-timeout');
  session.callTimeout = 30000;
  await session.start(); assert.equal(await session.evaluate('6*7'), 42);
  report.lifecycle.timeoutReplacement = true;
  await session.stop();
  const batch = {schema: 1, programs: [{expression: '6*7'}]};
  const first = await build(root, batch, {cache: temporary});
  const second = await build(root, batch, {cache: temporary});
  assert.equal(first.cacheHit, false); assert.equal(second.cacheHit, true);
  assert.deepEqual(first.results, second.results);
  const changed = await build(root, {schema: 1, programs: [{expression: '6*8'}]}, {cache: temporary});
  assert.equal(changed.cacheHit, false); assert.notEqual(changed.key, first.key);
  report.lifecycle.cache = {hit: true, changedRequestMiss: true};
  const copy = path.join(temporary, 'altered-package');
  await fs.cp(root, copy, {recursive: true});
  const descriptor = path.join(copy, 'package.json'), original = await fs.readFile(descriptor);
  // Test a coherent forged source inventory, not just a changed payload byte.
  try {
    const value = JSON.parse(original); value.stackFiles[0].sha256 = '0'.repeat(64);
    await fs.writeFile(descriptor, JSON.stringify(value));
    await assert.rejects(loadPackage(copy), /pinned sources/);
  } finally { await fs.writeFile(descriptor, original); }
  report.lifecycle.forgedSourceIndexRejected = true;
  report.passed = true;
} finally {
  await session.stop(); await fs.rm(temporary, {recursive: true, force: true});
  await fs.mkdir(path.dirname(reportFile), {recursive: true});
  await fs.writeFile(reportFile, JSON.stringify(report, null, 2) + '\n');
}
