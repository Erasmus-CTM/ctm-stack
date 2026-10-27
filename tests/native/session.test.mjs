// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import test from 'node:test';
import {NodeMaximaSession} from '../../_extensions/ctm-stack/native/node-session.mjs';
import {programs} from '../../_extensions/ctm-stack/native/build-runner.mjs';

class FakeWorker extends EventEmitter {
  static instances = [];
  constructor() { super(); FakeWorker.instances.push(this); }
  postMessage(value) { this.last = value; }
  async terminate() { this.terminated = true; this.emit('exit', 1); }
}
const next = () => new Promise(resolve => setImmediate(resolve));
function session(options = {}) { return new NodeMaximaSession('/unused', {WorkerClass: FakeWorker, loadTimeout: 100, callTimeout: 30, ...options}); }

test('startup failure rejects, retires worker and permits a new generation', async () => {
  const s = session();
  const first = s.start(); const child = s.child;
  child.emit('error', new Error('module failure'));
  await assert.rejects(first, /module failure/);
  assert.equal(child.terminated, true);
  const second = s.start(); s.child.emit('message', {type: 'ready'});
  await second;
  child.emit('message', {id: 1, ok: true, result: 'stale'});
  assert.notEqual(s.child, null);
  await s.stop();
});

test('ordinary CAS error keeps session; internal error retires it without retry', async () => {
  const s = session(); const ready = s.start(); const child = s.child;
  child.emit('message', {type: 'ready'}); await ready;
  const first = s.evaluate('bad'); await next();
  child.emit('message', {id: child.last.id, ok: false, error: {kind: 'cas', message: 'domain'}, poisoned: false});
  await assert.rejects(first, /domain/); assert.equal(s.child, child);
  const second = s.evaluate('fault'); await next();
  child.emit('message', {id: child.last.id, ok: false, error: {kind: 'runtime', message: 'internal'}, poisoned: true});
  await assert.rejects(second, /internal/);
  assert.equal(child.terminated, true); assert.equal(s.child, null);
});

test('a synchronous runaway is bounded by the parent, with no replay', async () => {
  const s = session(); const ready = s.start(); const child = s.child;
  child.emit('message', {type: 'ready'}); await ready;
  await assert.rejects(s.evaluate('runaway'), error => error.code === 'maxima-call-timeout');
  assert.equal(child.terminated, true); assert.equal(s.child, null);
});

test('Stop during loading rejects the old startup and ignores late readiness', async () => {
  const s = session(); const old = s.start(); const child = s.child;
  const rejected = assert.rejects(old, /stopped/);
  await s.stop(); await rejected;
  child.emit('message', {type: 'ready'});
  assert.equal(s.ready, null); assert.equal(s.child, null);
});

test('load watchdog is independent of computation watchdog', async () => {
  const s = session({loadTimeout: 10}); const childReady = s.start(), child = s.child;
  await assert.rejects(childReady, error => error.code === 'maxima-load-timeout');
  assert.equal(child.terminated, true);
});

test('Stop cancels startup queued behind worker retirement', async () => {
  let finish;
  class SlowWorker extends FakeWorker {
    terminate() { this.terminated = true; return new Promise(resolve => { finish = resolve; }); }
  }
  const s = session({WorkerClass: SlowWorker});
  const first = s.start(); s.child.emit('message', {type: 'ready'}); await first;
  const stopping = s.stop();
  const queued = s.start();
  const rejected = assert.rejects(queued, /superseded/);
  const again = s.stop();
  finish(0); await stopping; await again; await rejected;
  assert.equal(s.child, null);
});

test('build programs reject missing, oversized and NUL-containing code', () => {
  for (const value of [null, {schema:1,programs:[]}, {schema:1,programs:[{expression:'\0'}]}, {schema:1,programs:[{expression:'x'.repeat(300001)}]}]) {
    assert.throws(() => programs(value));
  }
});
