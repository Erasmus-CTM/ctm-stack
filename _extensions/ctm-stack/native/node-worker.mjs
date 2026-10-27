// SPDX-License-Identifier: AGPL-3.0-or-later
import {parentPort, workerData} from 'node:worker_threads';
import {openNode} from './node-runtime.mjs';

let session, tail = '';
function failure(error) {
  return {kind: error.kind || 'runtime', code: error.code || 'maxima-runtime', message: String(error.message || error)};
}
try {
  session = await openNode(workerData.root, {gcFreeSpaceDivisor: workerData.gcFreeSpaceDivisor,
    onOutput(text) { tail = (tail + text).slice(-4000); }});
  parentPort.postMessage({type: 'ready', packageHash: session.packageHash,
    adapterHash: session.adapterHash, maximaVersion: session.maximaVersion, manifest: session.manifest});
} catch (error) {
  parentPort.postMessage({type: 'failed', error: failure(error), tail}); parentPort.close();
}
if (session) parentPort.on('message', message => {
  try {
    if (message.type !== 'evaluate') throw new Error('Unknown trusted build operation');
    const result = session.evaluate(message.expression);
    parentPort.postMessage({id: message.id, ok: true, result, heapBytes: session.heapBytes()});
  } catch (error) {
    parentPort.postMessage({id: message.id, ok: false, error: failure(error), poisoned: session.poisoned});
  }
});
