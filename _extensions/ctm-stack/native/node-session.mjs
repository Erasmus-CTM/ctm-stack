// SPDX-License-Identifier: AGPL-3.0-or-later
// A real worker owns the synchronous Wasm calls. Deadlines run in its parent.
import {Worker} from 'node:worker_threads';

function fault(message, code = 'maxima-runtime') {
  return Object.assign(new Error(message), {kind: 'runtime', code});
}
export class NodeMaximaSession {
  constructor(root, {loadTimeout = 180000, callTimeout = 30000, WorkerClass = Worker} = {}) {
    this.root = root; this.loadTimeout = loadTimeout; this.callTimeout = callTimeout;
    this.WorkerClass = WorkerClass; this.sequence = 0; this.epoch = 0; this.pending = new Map();
  }
  async start() {
    if (this.ready) return this.ready;
    const requested = this.epoch;
    if (this.retiring) await this.retiring;
    if (this.ready) return this.ready;
    if (requested !== this.epoch) throw fault('Maxima startup superseded');
    const epoch = ++this.epoch;
    const child = this.child = new this.WorkerClass(new URL('./node-worker.mjs', import.meta.url), {
      workerData: {root: this.root}, execArgv: process.execArgv.filter(value => !value.startsWith('--input-type'))});
    this.ready = new Promise((resolve, reject) => {
      const timer = setTimeout(() => this.stop('Maxima loading timed out', 'maxima-load-timeout'), this.loadTimeout);
      this.starting = {reject, timer};
      child.on('message', message => {
        if (epoch !== this.epoch) return;
        if (message.type === 'ready') {
          clearTimeout(timer); this.starting = null; this.identity = message; resolve(message); return;
        }
        if (message.type === 'failed') {
          this.stop(message.error.message); reject(Object.assign(new Error(message.error.message), message.error)); return;
        }
        const pending = this.pending.get(message.id);
        if (!pending) { this.stop('Unexpected Maxima response'); return; }
        clearTimeout(pending.timer); this.pending.delete(message.id);
        if (message.ok) pending.resolve(message.result);
        else {
          pending.reject(Object.assign(new Error(message.error.message), message.error));
          if (message.poisoned) this.stop('Maxima session failed');
        }
      });
      child.on('error', error => { if (epoch === this.epoch) this.stop(error.message); });
      child.on('exit', code => { if (epoch === this.epoch) this.stop('Maxima worker exited: ' + code); });
    });
    // stop() owns state invalidation; a late failure cannot clear a new start.
    return this.ready;
  }
  async evaluate(expression) {
    const identity = await this.start();
    if (!this.child || this.identity !== identity) throw fault('Maxima session stopped');
    // Callers serialize programs. Reject concurrent use instead of consuming
    // a queued program's time budget while another computation runs.
    if (this.pending.size) throw fault('Concurrent trusted Maxima calls are not supported');
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      const timer = setTimeout(() => this.stop('Maxima calculation timed out', 'maxima-call-timeout'), this.callTimeout);
      this.pending.set(id, {resolve, reject, timer});
      this.child.postMessage({id, type: 'evaluate', expression});
    });
  }
  async stop(reason = 'Maxima stopped', code) {
    ++this.epoch;
    const child = this.child; this.child = null; this.ready = null; this.identity = null;
    if (this.starting) {
      clearTimeout(this.starting.timer); this.starting.reject(fault(reason, code)); this.starting = null;
    }
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(fault(reason, code)); }
    this.pending.clear();
    const retired = child ? Promise.resolve(child.terminate()) : this.retiring;
    if (retired) {
      this.retiring = retired;
      await retired;
      if (this.retiring === retired) this.retiring = null;
    }
    return {restarted: false};
  }
  async restart(reason) { await this.stop(reason); return this.start(); }
}
