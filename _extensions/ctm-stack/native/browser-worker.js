// SPDX-License-Identifier: AGPL-3.0-or-later
// Internal transport qualification; deliberately not registered as a card
// adapter. Only a trusted plan compiler may produce its programs.
'use strict';
importScripts('stack-pin.js','direct-runtime.js');
const send = self.postMessage.bind(self);
const hex = buffer => Array.from(new Uint8Array(buffer), x => x.toString(16).padStart(2, '0')).join('');
const digest = async bytes => hex(await crypto.subtle.digest('SHA-256', bytes));
let session, configured = false, queue = Promise.resolve(), urls = [];
function safePath(path) {
  if (typeof path !== 'string' || !path || path.includes('\\') || path.split('/').some(p => !p || p === '.' || p === '..') || path.startsWith('/')) throw new Error('Unsafe native runtime path');
  return path;
}
async function fetchBytes(url, record) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('Native runtime HTTP ' + response.status);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length !== record.bytes || await digest(bytes) !== record.sha256) throw new Error('Native runtime hash mismatch');
  return bytes;
}
async function init(message) {
  if (configured) throw new Error('Native worker configuration is immutable');
  configured = true;
  const base = new URL(message.baseURL, self.location.href);
  if (base.origin !== self.location.origin || !base.pathname.endsWith('/')) throw new Error('Native runtime must be a same-origin package directory');
  if (!/^[a-f0-9]{64}$/.test(message.packageHash || '')) throw new Error('Native package needs an expected SHA-256');
  const response = await fetch(new URL('package.json', base));
  if (!response.ok) throw new Error('Native package HTTP ' + response.status);
  const encoded = await response.arrayBuffer();
  if (encoded.byteLength > 1024 * 1024 || await digest(encoded) !== message.packageHash) throw new Error('Native package hash mismatch');
  const spec = JSON.parse(new TextDecoder().decode(encoded));
  if (spec.schema !== 1 || spec.runtimeTag !== 'runtime-v3' || spec.manifest.stackRevision !== self.CTMStackRevision) throw new Error('Wrong native runtime package');
  const bytes = new Map(), stackFiles = [], assets = new Map();
  for (const item of spec.runtimeAssets) {
    safePath(item.path);
    if (bytes.has(item.path)) throw new Error('Duplicate runtime asset');
    bytes.set(item.path, await fetchBytes(new URL('runtime/' + item.path, base), item));
  }
  for (const item of spec.stackFiles) {
    safePath(item.path);
    if (stackFiles.some(file => file.path === item.path)) throw new Error('Duplicate STACK source');
    stackFiles.push({path: item.path, bytes: await fetchBytes(new URL('stack/' + item.path, base), item)});
  }
  for (const [name, body] of bytes) {
    const url = URL.createObjectURL(new Blob([body], {type: name.endsWith('.js') ? 'text/javascript' : 'application/wasm'}));
    urls.push(url); assets.set(name, url);
  }
  const originalImport = importScripts.bind(self);
  session = await CTMMaximaDirect.open({scope: self, bytes, manifest: spec.manifest, stackFiles, startup: spec.startup,
    execute(name) {
      if (!['maxima_thread.js', 'maxima.js', 'share_files.js'].includes(name) || !assets.has(name)) throw new Error('Unexpected runtime script');
      originalImport(assets.get(name));
    },
    locateFile(name) { if (!assets.has(name)) throw new Error('Unknown runtime asset'); return assets.get(name); }});
  self.onmessage = receive;
  return {packageHash: message.packageHash, maximaVersion: session.maximaVersion};
}
async function handle(message) {
  try {
    let result;
    if (message.type === 'init') result = await init(message);
    else if (message.type === 'evaluate' && session) result = session.evaluate(message.expression);
    else throw new Error('Unknown trusted native operation');
    send({id: message.id, ok: true, result});
  } catch (error) {
    send({id: message.id, ok: false, error: {kind: error.kind || 'runtime', code: error.code || 'maxima-runtime', message: String(error.message || error)}, poisoned: session?.poisoned ?? true});
  }
}
function receive({data}) { queue = queue.then(() => handle(data)); }
self.onmessage = receive;
