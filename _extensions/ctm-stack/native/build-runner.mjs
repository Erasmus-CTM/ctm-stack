// SPDX-License-Identifier: AGPL-3.0-or-later
// Internal author-build interface. Never accepts raw learner answers.
import fs from 'node:fs/promises';
import path from 'node:path';
import {loadPackage, sha256} from './node-runtime.mjs';
import {NodeMaximaSession} from './node-session.mjs';

export function programs(request) {
  if (!request || request.schema !== 1 || !Array.isArray(request.programs) || !request.programs.length || request.programs.length > 1000) {
    throw new Error('Expected a schema-1 batch of 1–1000 trusted build programs');
  }
  return request.programs.map((item, index) => {
    if (!item || typeof item.expression !== 'string' || !item.expression.trim() || item.expression.includes('\0') || item.expression.length > 300000) {
      throw new Error('Invalid trusted build program at ' + index);
    }
    return {id: item.id ?? index, expression: item.expression};
  });
}
export async function adapterHash() {
  const names = ['direct-runtime.js', 'startup.mjs', 'node-runtime.mjs', 'node-worker.mjs', 'node-session.mjs', 'build-runner.mjs'];
  const records = [];
  for (const name of names) records.push([name, sha256(await fs.readFile(new URL(name, import.meta.url)))]);
  return sha256(JSON.stringify(records));
}
export async function build(root, request, {cache, callTimeout, loadTimeout} = {}) {
  const batch = programs(request);
  const loaded = await loadPackage(root); // Verify the source inventory even on a cache hit.
  const identity = {schema: 1, packageHash: loaded.packageHash, adapterHash: await adapterHash(), node: process.versions.node,
    requestHash: sha256(JSON.stringify(batch))};
  const key = sha256(JSON.stringify(identity));
  const filename = cache && path.join(cache, key + '.json');
  if (filename) {
    try {
      const hit = JSON.parse(await fs.readFile(filename));
      if (hit.key === key && JSON.stringify(hit.identity) === JSON.stringify(identity)
          && Array.isArray(hit.results) && hit.results.length === batch.length
          && hit.resultHash === sha256(JSON.stringify(hit.results))) {
        return {...hit, cacheHit: true};
      }
    } catch (error) { if (error.code !== 'ENOENT' && !(error instanceof SyntaxError)) throw error; }
  }
  const session = new NodeMaximaSession(root, {callTimeout, loadTimeout});
  const results = [];
  try {
    await session.start();
    for (const item of batch) results.push({id: item.id, result: await session.evaluate(item.expression)});
  } finally { await session.stop(); }
  const result = {key, identity, results, resultHash: sha256(JSON.stringify(results))};
  if (filename) {
    await fs.mkdir(cache, {recursive: true});
    const temporary = filename + '.' + process.pid + '.tmp';
    try {
      await fs.writeFile(temporary, JSON.stringify(result) + '\n', {flag: 'wx'});
      await fs.rename(temporary, filename);
    } finally { await fs.rm(temporary, {force: true}); }
  }
  return {...result, cacheHit: false};
}
