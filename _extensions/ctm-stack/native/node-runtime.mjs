// SPDX-License-Identifier: AGPL-3.0-or-later
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {startup} from './startup.mjs';
import {isMainThread} from 'node:worker_threads';
import './direct-runtime.js';

export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
export function relativePath(name) {
  if (typeof name !== 'string' || !name || name.includes('\\') || name.split('/').some(p => !p || p === '.' || p === '..') || path.isAbsolute(name)) {
    throw new Error('Unsafe native runtime path');
  }
  return name;
}
async function checkedFile(root, record) {
  const name = relativePath(record.path), filename = path.join(root, name);
  const real = await fs.realpath(filename), realRoot = await fs.realpath(root);
  if (!real.startsWith(realRoot + path.sep)) throw new Error('Native runtime file escapes its package');
  const bytes = await fs.readFile(filename);
  if (bytes.length !== record.bytes || sha256(bytes) !== record.sha256) throw new Error('Native runtime hash mismatch: ' + name);
  return new Uint8Array(bytes);
}

export async function loadPackage(root) {
  const filename = path.join(root, 'package.json');
  const descriptor = await fs.readFile(filename);
  const spec = JSON.parse(descriptor);
  if (spec.schema !== 1 || spec.runtimeTag !== 'runtime-v3' || !Array.isArray(spec.runtimeAssets) || !Array.isArray(spec.stackFiles)) {
    throw new Error('Invalid native runtime package');
  }
  const pin = JSON.parse(await fs.readFile(new URL('./release.json', import.meta.url)));
  const releaseBytes = await fs.readFile(path.join(root, pin.record));
  if (sha256(releaseBytes) !== pin.recordSha256) throw new Error('Release record differs from the v3 pin');
  const release = JSON.parse(releaseBytes);
  const manifestBytes = await fs.readFile(path.join(root, 'release-manifest.json'));
  if (sha256(manifestBytes) !== release.runtimeManifestSha256) throw new Error('Release manifest differs from the v3 record');
  const runtime = JSON.parse(manifestBytes);
  const stackIndex = JSON.parse(await fs.readFile(new URL('./stack-files.json', import.meta.url)));
  const classified = await fs.readFile(new URL('./classified-errcatch.lisp', import.meta.url), 'utf8');
  if (JSON.stringify(spec.runtimeAssets) !== JSON.stringify(runtime.runtimeAssets)
      || JSON.stringify(spec.stackFiles) !== JSON.stringify(stackIndex.files)
      || spec.manifest.stackRevision !== stackIndex.revision || String(spec.manifest.stackLibraryVersion) !== '2026101500'
      || JSON.stringify(spec.manifest.runtimeAssets) !== JSON.stringify(runtime.runtimeAssets)
      || spec.startup !== startup(runtime.startupAdapter.content, classified)
      || spec.releaseRecordSha256 !== pin.recordSha256 || spec.runtimeManifestSha256 !== release.runtimeManifestSha256) {
    throw new Error('Native package configuration differs from its pinned sources');
  }
  const bytes = new Map();
  for (const record of spec.runtimeAssets) {
    if (bytes.has(record.path)) throw new Error('Duplicate runtime asset');
    bytes.set(record.path, await checkedFile(path.join(root, 'runtime'), record));
  }
  const stackFiles = [], seen = new Set();
  for (const record of spec.stackFiles) {
    if (seen.has(record.path)) throw new Error('Duplicate STACK source');
    seen.add(record.path);
    stackFiles.push({path: record.path, bytes: await checkedFile(path.join(root, 'stack'), record)});
  }
  return {spec, bytes, stackFiles, packageHash: sha256(descriptor)};
}

let opened = false;
export async function openNode(root, {onOutput} = {}) {
  if (isMainThread || opened) throw new Error('Each Maxima runtime requires a fresh dedicated Node worker');
  opened = true;
  const loaded = await loadPackage(root);
  const {spec, bytes, stackFiles} = loaded;
  const coreHash = sha256(await fs.readFile(new URL('./direct-runtime.js', import.meta.url)));
  // A worker is the lifetime/deadline boundary. A vm context is not a sandbox
  // for trusted author code and adds costly crossings at Emscripten imports.
  const context = globalThis;
  Object.assign(context, {
    // The upstream loader's Node branch needs only readFileSync. Every read is
    // served from the verified inventory, including dynamic module reads.
    __dirname: '/', __filename: '/maxima.js', module: {exports: {}},
    require(name) {
      if (name !== 'fs') throw new Error('Unexpected runtime import: ' + name);
      return {readFileSync(filename, encoding) {
        const key = String(filename).replace(/^\//, '');
        const value = bytes.get(key);
        if (!value) throw new Error('Runtime read outside verified inventory: ' + key);
        return encoding ? new TextDecoder().decode(value) : value;
      }};
    }});
  context.self = context;
  context.location = {origin: '', href: '/maxima.js'};
  const execute = name => {
    if (!['maxima_thread.js', 'maxima.js', 'share_files.js'].includes(name) || !bytes.has(name)) throw new Error('Unexpected runtime script: ' + name);
    vm.runInThisContext(new TextDecoder().decode(bytes.get(name)), {filename: name});
  };
  const session = await globalThis.CTMMaximaDirect.open({scope: context, execute, bytes,
    manifest: spec.manifest, stackFiles, startup: spec.startup, onOutput});
  session.packageHash = loaded.packageHash;
  session.adapterHash = coreHash;
  session.heapBytes = () => context.HEAPU8.buffer.byteLength;
  return session;
}

// No CLI and no Lisp endpoint. The supervised runner is the process boundary.
